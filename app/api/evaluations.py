# modelwhiz-backend/app/api/evaluations.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from celery.result import AsyncResult
from ..db.async_database import get_async_db, AsyncSessionLocal
from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import os
import asyncio
import aiofiles
import zipfile
import uuid
import logging
from datetime import datetime
from typing import Optional, List
from ..models.evaluation_job import EvaluationJob
from ..evaluation_engine.main_evaluator import run_evaluation_task
from ..models.model import MLModel
from ..utils.file_cleanup import cleanup_model_files, validate_file_size, validate_file_type, get_storage_usage
from app.workers.tasks import evaluate_model_async
from app.workers.task_queue import get_task_status, revoke_task

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = "uploads/temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/start")
async def start_evaluation(
    model_file: UploadFile = File(...),
    dataset: UploadFile = File(...),
    target_column: str = Form(...),
    user_id: str = Form(...),
    model_name: str = Form(...),
    preprocessor_file: Optional[UploadFile] = File(None),
    split_data: bool = Form(...),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Initiates an evaluation task asynchronously using Celery background workers.
    Returns immediately with task ID for progress tracking.
    """
    # Check storage quota before processing
    storage_info = get_storage_usage()
    if storage_info.get("alert_level") == "critical":
        raise HTTPException(status_code=507, detail="Insufficient storage space")

    # Validate file size before processing
    # First save the file temporarily to check its size
    temp_model_path = os.path.join(UPLOAD_DIR, f"temp_{model_file.filename}")
    async with aiofiles.open(temp_model_path, "wb") as buffer:
        content = await model_file.read()
        await buffer.write(content)
    
    if not validate_file_size(temp_model_path, max_size_mb=100):
        os.remove(temp_model_path)
        raise HTTPException(status_code=413, detail="File too large")
    
    # Validate file type
    if not validate_file_type(temp_model_path, ['.pkl', '.joblib', '.zip']):
        os.remove(temp_model_path)
        raise HTTPException(status_code=400, detail="File type not allowed")
    
    # Reset file pointer for later processing
    await model_file.seek(0)

    # Generate unique filenames
    unique_id = str(uuid.uuid4())[:8]
    
    csv_filename = f"{user_id}_{unique_id}_{dataset.filename}"
    model_filename = f"{user_id}_{unique_id}_{model_file.filename}"
    preprocessor_filename = f"{user_id}_{unique_id}_{preprocessor_file.filename}" if preprocessor_file and preprocessor_file.filename else None
    
    csv_path = os.path.join(UPLOAD_DIR, csv_filename)
    model_file_path = os.path.join(UPLOAD_DIR, model_filename)
    preprocessor_file_path = os.path.join(UPLOAD_DIR, preprocessor_filename) if preprocessor_filename else None
    zip_path = os.path.join(UPLOAD_DIR, f"{user_id}_{unique_id}_package.zip")
    
    # Track files for cleanup (but NOT the zip if DB operations succeed)
    temp_files_for_cleanup = []
    
    try:
        # Save files asynchronously
        async with aiofiles.open(csv_path, "wb") as buffer:
            content = await dataset.read()
            await buffer.write(content)
            
        async with aiofiles.open(model_file_path, "wb") as buffer:
            content = await model_file.read()
            await buffer.write(content)
        temp_files_for_cleanup.extend([model_file_path])

        if preprocessor_file and preprocessor_file_path:
            async with aiofiles.open(preprocessor_file_path, "wb") as buffer:
                content = await preprocessor_file.read()
                await buffer.write(content)
            temp_files_for_cleanup.append(preprocessor_file_path)
        
        # Create zip file in thread pool
        def create_zip_sync():
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.write(model_file_path, arcname='model.pkl')
                if preprocessor_file_path:
                    zf.write(preprocessor_file_path, arcname='preprocessor.pkl')
            
            # Clean up temporary files after zipping
            for temp_file in temp_files_for_cleanup:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        await asyncio.to_thread(create_zip_sync)
        
        # Database operations
        count_query = select(func.count(MLModel.id)).where(
            MLModel.name == model_name, 
            MLModel.user_id == user_id
        )
        count_result = await db.execute(count_query)
        existing_versions_count = count_result.scalar() or 0

        version_str = f"v{existing_versions_count + 1}"
        ml_model = MLModel(
            name=model_name, 
            version=version_str, 
            filename=zip_path,
            user_id=user_id, 
            latest_metrics={}
        )
        
        db.add(ml_model)
        await db.commit()
        await db.refresh(ml_model)

        new_job = EvaluationJob(
            user_id=user_id, 
            model_name=model_name, 
            model_id=ml_model.id
        )
        db.add(new_job)
        await db.commit()
        await db.refresh(new_job)
        
        # Start Celery background task instead of FastAPI background task
        task = evaluate_model_async.delay(
            job_id=new_job.id,
            model_id=ml_model.id,
            zip_path=zip_path,
            csv_path=csv_path,
            target_column=target_column,
            split_data=split_data
        )
        
        # Store task ID in the job for later reference
        new_job.task_id = task.id
        await db.commit()

        return {
            "job_id": new_job.id,
            "task_id": task.id,
            "status": "processing",
            "message": "Evaluation started in background. Use task_id to track progress."
        }
        
    except Exception as e:
        # Rollback database if needed
        try:
            await db.rollback()
        except:
            pass
        
        # Clean up ALL files if anything goes wrong
        all_files_to_cleanup = [csv_path, zip_path] + temp_files_for_cleanup
        for path in all_files_to_cleanup:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
                    
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation setup failed: {str(e)}"
        )

@router.get("/")
async def get_all_evaluation_jobs(
    user_id: str, 
    status_filter: Optional[str] = None,
    limit: int = 100,
    cursor: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Fetches evaluation jobs for a given user with optimized filtering and pagination.
    """
    if not user_id: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID is required")
    
    # Build base query with eager loading
    query = select(EvaluationJob).options(joinedload(EvaluationJob.model))\
            .where(EvaluationJob.user_id == user_id)
    
    # Apply status filter if provided
    if status_filter:
        query = query.where(EvaluationJob.status == status_filter)
    
    # Apply cursor-based pagination
    if cursor:
        try:
            cursor_time = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
            query = query.where(EvaluationJob.created_at < cursor_time)
        except ValueError:
            logger.warning(f"Invalid cursor format: {cursor}, ignoring cursor")
    
    # Order and limit
    query = query.order_by(desc(EvaluationJob.created_at)).limit(limit)
    
    result = await db.execute(query)
    jobs = result.scalars().unique().all()
    
    # Batch load related models to avoid N+1 queries
    model_ids = [job.model_id for job in jobs]
    if model_ids:
        models_query = select(MLModel).where(MLModel.id.in_(model_ids))
        models_result = await db.execute(models_query)
        models = models_result.scalars().all()
        models_dict = {model.id: model for model in models}
        for job in jobs:
            job.model = models_dict.get(job.model_id)
    
    # Calculate pagination metadata
    has_next = len(jobs) == limit and len(jobs) > 0
    next_cursor = jobs[-1].created_at.isoformat() if has_next else None
    
    return {
        "jobs": jobs,
        "pagination": {
            "has_next": has_next,
            "next_cursor": next_cursor,
            "limit": limit
        }
    }

@router.get("/{job_id}/status")
async def get_job_status(job_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Fetches the status of a specific evaluation job asynchronously.
    """
    query = select(EvaluationJob).where(EvaluationJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    return {"job_id": job.id, "status": str(job.status.value)}

@router.get("/{job_id}/results")
async def get_job_results(job_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Fetches the full results of a specific evaluation job asynchronously.
    """
    query = select(EvaluationJob).where(EvaluationJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    return job

# Task status endpoints
@router.get("/task/{task_id}/status")
async def get_task_status_endpoint(task_id: str):
    """
    Get the current status and progress of a Celery task.
    """
    try:
        status_info = get_task_status(task_id)
        return status_info
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )

@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    Cancel a running or pending task.
    """
    try:
        revoke_task(task_id, terminate=True)
        return {"message": f"Task {task_id} cancellation requested", "task_id": task_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {str(e)}"
        )

@router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """
    Get the final result of a completed task.
    """
    try:
        task_result = AsyncResult(task_id)
        
        if task_result.status == 'SUCCESS':
            return {
                "task_id": task_id,
                "status": task_result.status,
                "result": task_result.result
            }
        elif task_result.status == 'FAILURE':
            return {
                "task_id": task_id,
                "status": task_result.status,
                "error": str(task_result.result) if task_result.result else "Unknown error"
            }
        else:
            return {
                "task_id": task_id,
                "status": task_result.status,
                "message": "Task is still processing or pending"
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task result: {str(e)}"
        )
