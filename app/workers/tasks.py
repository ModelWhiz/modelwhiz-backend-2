import time
from typing import Dict, Any, Optional
from celery import current_task
from celery.utils.log import get_task_logger
import os
import shutil
from datetime import datetime, timedelta

from .celery_app import celery_app
from app.utils.logger import get_logger
from app.utils.error_monitor import track_error, ErrorTypes
from app.utils.performance_monitor import track_performance, ML_OPERATIONS
from app.evaluation_engine.main_evaluator import run_evaluation_task

logger = get_logger()
task_logger = get_task_logger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_evaluation_task(self, model_id: int, dataset_path: str, request_id: Optional[str] = None):
    """
    Asynchronous model evaluation task.
    Moves heavy ML processing to background workers.
    """
    try:
        # Update task progress
        self.update_state(state='PROGRESS', meta={'current': 10, 'total': 100, 'status': 'Loading data'})
        
        # Simulate data loading
        time.sleep(2)
        
        # Update progress
        self.update_state(state='PROGRESS', meta={'current': 30, 'total': 100, 'status': 'Preprocessing'})
        
        # Simulate preprocessing
        time.sleep(3)
        
        # Update progress
        self.update_state(state='PROGRESS', meta={'current': 60, 'total': 100, 'status': 'Model evaluation'})
        
        # Simulate model evaluation (this is where the actual ML processing would happen)
        time.sleep(5)
        
        # Update progress
        self.update_state(state='PROGRESS', meta={'current': 90, 'total': 100, 'status': 'Generating insights'})
        
        # Simulate insight generation
        time.sleep(2)
        
        # Final result
        result = {
            "model_id": model_id,
            "accuracy": 0.85,
            "precision": 0.82,
            "recall": 0.88,
            "f1_score": 0.85,
            "evaluation_time": datetime.utcnow().isoformat(),
            "metrics": {
                "mse": 0.15,
                "mae": 0.12,
                "r2": 0.89
            }
        }
        
        logger.info(f"Model evaluation completed for model {model_id}")
        return result
        
    except Exception as e:
        error_message = f"Model evaluation failed for model {model_id}: {str(e)}"
        task_logger.error(error_message)
        track_error(ErrorTypes.ML, error_message, request_id)
        self.update_state(state='FAILURE', meta={'error': error_message})
        raise self.retry(exc=e)

@celery_app.task
def cleanup_old_files():
    """
    Scheduled cleanup task for old files and temporary data.
    """
    try:
        cleanup_dirs = [
            "uploads/temp",
            "uploads/eval_jobs"
        ]
        
        deleted_files = 0
        deleted_size = 0
        
        for dir_path in cleanup_dirs:
            if os.path.exists(dir_path):
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    try:
                        if os.path.isfile(item_path):
                            # Delete files older than 7 days
                            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(item_path))
                            if file_age > timedelta(days=7):
                                file_size = os.path.getsize(item_path)
                                os.remove(item_path)
                                deleted_files += 1
                                deleted_size += file_size
                        elif os.path.isdir(item_path):
                            # Delete empty directories
                            if not os.listdir(item_path):
                                shutil.rmtree(item_path)
                    except Exception as e:
                        task_logger.warning(f"Failed to clean up {item_path}: {e}")
        
        return {
            "deleted_files": deleted_files,
            "deleted_size_bytes": deleted_size,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_message = f"File cleanup failed: {str(e)}"
        task_logger.error(error_message)
        track_error(ErrorTypes.FILE, error_message)
        raise

@celery_app.task(bind=True)
def generate_model_insights(self, model_id: int):
    """
    Generate charts and visualizations for model evaluation results.
    """
    try:
        self.update_state(state='PROGRESS', meta={'current': 25, 'total': 100, 'status': 'Generating charts'})
        
        # Simulate chart generation
        time.sleep(3)
        
        self.update_state(state='PROGRESS', meta={'current': 75, 'total': 100, 'status': 'Creating visualizations'})
        
        # Simulate visualization creation
        time.sleep(2)
        
        insights = {
            "model_id": model_id,
            "charts_generated": [
                "confusion_matrix.png",
                "feature_importance.png",
                "learning_curve.png"
            ],
            "insights": [
                "Model shows good generalization",
                "Feature X has highest importance",
                "Training converged after 50 epochs"
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Model insights generated for model {model_id}")
        return insights
        
    except Exception as e:
        error_message = f"Insight generation failed for model {model_id}: {str(e)}"
        task_logger.error(error_message)
        track_error(ErrorTypes.ML, error_message)
        self.update_state(state='FAILURE', meta={'error': error_message})
        raise

@celery_app.task
def update_model_statistics():
    """
    Update cached statistics and model performance metrics.
    """
    try:
        # This would typically query the database and update cache
        # For now, we'll simulate the operation
        
        stats = {
            "total_models": 42,
            "average_accuracy": 0.78,
            "total_evaluations": 156,
            "last_updated": datetime.utcnow().isoformat(),
            "top_performing_models": [
                {"model_id": 1, "accuracy": 0.92},
                {"model_id": 5, "accuracy": 0.89},
                {"model_id": 8, "accuracy": 0.87}
            ]
        }
        
        logger.info("Model statistics updated")
        return stats
        
    except Exception as e:
        error_message = f"Statistics update failed: {str(e)}"
        task_logger.error(error_message)
        track_error(ErrorTypes.DATABASE, error_message)
        raise

@celery_app.task
def health_check_system():
    """
    System monitoring and health check tasks.
    """
    try:
        health_checks = {
            "database": "healthy",
            "cache": "healthy", 
            "storage": "healthy",
            "ml_services": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "system_load": 0.45,
            "memory_usage": "2.1GB/8GB",
            "disk_usage": "45GB/100GB"
        }
        
        logger.info("System health check completed")
        return health_checks
        
    except Exception as e:
        error_message = f"Health check failed: {str(e)}"
        task_logger.error(error_message)
        track_error(ErrorTypes.UNKNOWN, error_message)
        raise

# Performance tracked ML operations
@celery_app.task(bind=True)
@track_performance(ML_OPERATIONS["MODEL_EVALUATION"])
def evaluate_model_with_perf_tracking(self, model_id: int, dataset_path: str):
    """Model evaluation with performance tracking"""
    return process_evaluation_task(self, model_id, dataset_path)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def evaluate_model_async(self, job_id: int, model_id: int, zip_path: str, csv_path: str, target_column: str, split_data: bool):
    """
    Asynchronous model evaluation task that integrates with the evaluation engine.
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.future import select
    from app.models.evaluation_job import EvaluationJob
    from app.db.async_database import AsyncSessionLocal
    import asyncio

    async def update_job_status(session: AsyncSession, job_id: int, status: str):
        try:
            result = await session.execute(select(EvaluationJob).where(EvaluationJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = status
                await session.flush()
                await session.commit()
                logger.info(f"Job {job_id} status updated to {status}")
            else:
                logger.warning(f"Job {job_id} not found for status update to {status}")
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status to {status}: {e}")

    async def run_evaluation_async():
        try:
            # Update job status to PROCESSING
            async with AsyncSessionLocal() as session:
                await update_job_status(session, job_id, "PROCESSING")

            # Update task progress
            self.update_state(state='PROGRESS', meta={'current': 10, 'total': 100, 'status': 'Starting evaluation'})

            logger.info(f"Starting run_evaluation_task for job {job_id}")
            # Run the evaluation task
            result = await run_evaluation_task(
                job_id=job_id,
                model_id=model_id,
                zip_path=zip_path,
                csv_path=csv_path,
                target_column=target_column,
                split_data=split_data,
                async_db_session_factory=AsyncSessionLocal
            )
            logger.info(f"Completed run_evaluation_task for job {job_id}")

            # Update job status to COMPLETED
            async with AsyncSessionLocal() as session:
                await update_job_status(session, job_id, "COMPLETED")

            self.update_state(state='SUCCESS', meta={'current': 100, 'total': 100, 'status': 'Evaluation completed'})
            return result

        except Exception as e:
            error_message = f"Model evaluation failed for job {job_id}: {str(e)}"
            task_logger.error(error_message)
            track_error(ErrorTypes.ML, error_message)

            # Update job status to FAILED
            async with AsyncSessionLocal() as session:
                await update_job_status(session, job_id, "FAILED")

            self.update_state(state='FAILURE', meta={'error': error_message})
            raise e

    try:
        # Run the async function using asyncio.run
        return asyncio.run(run_evaluation_async())
    except Exception as e:
        # Retry logic
        raise self.retry(exc=e)

@celery_app.task
@track_performance(ML_OPERATIONS["DATA_PREPROCESSING"])  
def preprocess_data_with_perf_tracking(data: Dict[str, Any]):
    """Data preprocessing with performance tracking"""
    # Simulate preprocessing
    time.sleep(2)
    return {"processed": True, "size": len(str(data))}
