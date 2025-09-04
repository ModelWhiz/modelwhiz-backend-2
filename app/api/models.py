# app/api/models.py

from fastapi import APIRouter, HTTPException, Depends, status, Query
import os
import logging
from typing import Optional, List

from app.cache import (
    cache_result,
    invalidate_cache,
    generate_model_list_key,
    generate_model_detail_key,
    generate_model_invalidation_patterns,
    generate_user_invalidation_patterns,
    MODEL_LIST_TTL,
    MODEL_DETAIL_TTL
)

from app.db.async_database import get_async_db
from app.models.model import MLModel
from app.schemas.model import ModelDashboardOut, ModelCreate, ModelUpdate, ModelPaginatedResponse # Ensure ModelPaginatedResponse is imported
from sqlalchemy.orm import noload, selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.evaluation_engine.insight_generator import generate_insights
from app.cache.redis_client import cache_client
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_current_user_id() -> str:
    return "user_123"

@router.get("/", response_model=ModelPaginatedResponse)
async def get_all_models(
    user_id: Optional[str] = Query(None, description="User ID to filter models"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (ISO timestamp)"),
    limit: int = Query(20, ge=1, le=1000, description="Number of records to return"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all models with optimized cursor-based pagination and eager loading.
    """
    try:
        # Count total models (cached for better performance)
        count_query = select(func.count(MLModel.id))
        if user_id:
            count_query = count_query.where(MLModel.user_id == user_id)
        
        total_count_result = await db.execute(count_query)
        total = total_count_result.scalar_one()

        # Build main query with cursor-based pagination
        query = select(MLModel).options(
            selectinload(MLModel.evaluation_jobs),  # Eager load evaluation_jobs to avoid N+1 queries
            noload(MLModel.metrics)  # Metrics are large, load separately if needed
        )
        
        if user_id:
            query = query.where(MLModel.user_id == user_id)
        
        # Cursor-based pagination for better performance on large datasets
        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
                query = query.where(MLModel.upload_time < cursor_time)
            except ValueError:
                logger.warning(f"Invalid cursor format: {cursor}, ignoring cursor")
        
        query = query.order_by(MLModel.upload_time.desc()).limit(limit)
        
        result = await db.execute(query)
        models_from_db = result.scalars().all()
        
        logger.info(f"Retrieved {len(models_from_db)} models for user {user_id} (total: {total})")
        
        # Convert to Pydantic models efficiently
        items_as_pydantic = [ModelDashboardOut.model_validate(model).model_dump() for model in models_from_db]
        
        # Calculate pagination metadata
        has_next = len(models_from_db) == limit and len(models_from_db) > 0
        next_cursor = models_from_db[-1].upload_time.isoformat() if has_next else None
        
        return ModelPaginatedResponse(
            items=items_as_pydantic,
            total=total,
            page=1,  # Cursor pagination doesn't use page numbers
            pages=(total + limit - 1) // limit if total > 0 else 1,
            has_next=has_next,
            next_cursor=next_cursor
        )
    
    except Exception as e:
        logger.error(f"Error fetching models: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An error occurred while fetching models: {str(e)}"
        )

# ... (The rest of your models.py file is correct and does not need changes) ...
# I am omitting the rest for brevity, but you should keep it as is in your file.
        
@router.get("/{model_id}", response_model=ModelDashboardOut)
@cache_result(ttl=MODEL_DETAIL_TTL, key_generator=generate_model_detail_key)
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    try:
        result = await db.execute(select(MLModel).where(MLModel.id == model_id))
        model = result.scalar_one_or_none()
        
        if not model:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model with ID {model_id} not found")
        
        logger.debug(f"Retrieved model {model_id}")
        
        # Convert SQLAlchemy object to Pydantic model using model_validate and then to dict
        return ModelDashboardOut.model_validate(model).model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching model {model_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the model."
        )

@router.get("/{model_id}/insights")
async def get_model_insights(
    model_id: int,
    force_refresh: bool = Query(False, description="Force refresh of insights"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Fetches insights for a specific model based on its metrics.
    Insights can be cached but also refreshed on demand.
    
    Args:
        model_id: ID of the model
        force_refresh: Whether to bypass cache and regenerate insights
        db: Database session
    
    Returns:
        Dictionary containing model insights
    """
    try:
        # Check cache first (unless force refresh)
        insights_cache_key = f"model:insights:{model_id}"
        
        if not force_refresh:
            cached_insights = await cache_client.get(insights_cache_key)
            if cached_insights:
                logger.debug(f"Retrieved cached insights for model {model_id}")
                return cached_insights
        
        # Fetch model from database
        result = await db.execute(
            select(MLModel).where(MLModel.id == model_id)
        )
        model = result.scalar_one_or_none()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Model with ID {model_id} not found"
            )
        
        # Generate insights
        metrics = model.latest_metrics
        if not metrics:
            return {"insights": [], "message": "No metrics available for insights generation"}
        
        insights = generate_insights(metrics)
        response = {"insights": insights, "model_id": model_id}
        
        # Cache insights for 15 minutes
        await cache_client.set(insights_cache_key, response, ttl=900)
        
        logger.info(f"Generated and cached insights for model {model_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating insights for model {model_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating model insights."
        )

@router.post("/", response_model=ModelDashboardOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    model_data: ModelCreate,
    user_id: Optional[str] = Query(None, description="User ID (will be extracted from auth in production)"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Creates a new ML Model in the database asynchronously.
    Invalidates related caches.
    
    Args:
        model_data: Model creation data
        user_id: User ID (in production, extract from authentication)
        db: Database session
    
    Returns:
        Created ModelDashboardOut object
    """
    try:
        # In production, get user_id from authenticated user
        effective_user_id = user_id or get_current_user_id()
        
        # Create new model
        model_dict = model_data.model_dump()
        model_dict['user_id'] = effective_user_id
        new_model = MLModel(**model_dict)
        
        db.add(new_model)
        await db.commit()
        await db.refresh(new_model)
        
        logger.info(f"Created new model {new_model.id} for user {effective_user_id}")

        # Invalidate user's model list cache
        user_model_list_key = f"models:list:user:{effective_user_id}"
        await cache_client.delete(user_model_list_key)
        
        # Convert SQLAlchemy object to Pydantic model and then to dict
        return ModelDashboardOut.model_validate(new_model).model_dump()
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the model."
        )

@router.put("/{model_id}", response_model=ModelDashboardOut)
async def update_model(
    model_id: int,
    model_data: ModelUpdate,
    user_id: Optional[str] = Query(None, description="User ID for authorization"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Updates an existing ML Model asynchronously.
    Invalidates related caches.
    
    Args:
        model_id: ID of the model to update
        model_data: Model update data
        user_id: User ID for authorization check
        db: Database session
    
    Returns:
        Updated ModelDashboardOut object
    """
    try:
        # Fetch existing model
        result = await db.execute(
            select(MLModel).where(MLModel.id == model_id)
        )
        model = result.scalar_one_or_none()
        
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Model with ID {model_id} not found"
            )
        
        # Authorization check
        effective_user_id = user_id or get_current_user_id()
        if model.user_id != effective_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Not authorized to update this model"
            )
        
        # Update model fields
        update_data = model_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(model, field):
                setattr(model, field, value)
        
        await db.commit()
        await db.refresh(model)
        
        # Also invalidate insights cache
        insights_cache_key = f"model:insights:{model_id}"
        await cache_client.delete(insights_cache_key)
        
        # Invalidate user's model list cache
        user_model_list_key = f"models:list:user:{effective_user_id}"
        await cache_client.delete(user_model_list_key)
        
        logger.info(f"Updated model {model_id} and invalidated cache for user {effective_user_id}")
        
        # Convert SQLAlchemy object to Pydantic model and then to dict
        return ModelDashboardOut.model_validate(model).model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating model {model_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the model."
        )

@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: int,
    user_id: Optional[str] = Query(None, description="User ID for authorization"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deletes an ML Model from the database asynchronously.
    Invalidates related caches.
    
    Args:
        model_id: ID of the model to delete
        user_id: User ID for authorization check
        db: Database session
    """
    try:
        # Fetch model to delete
        result = await db.execute(
            select(MLModel).where(MLModel.id == model_id)
        )
        model = result.scalar_one_or_none()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Model with ID {model_id} not found"
            )
        
        # Authorization check
        effective_user_id = user_id or get_current_user_id()
        if model.user_id != effective_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Not authorized to delete this model"
            )
        
        await db.delete(model)
        await db.commit()
        
        # Clean up insights cache
        insights_cache_key = f"model:insights:{model_id}"
        await cache_client.delete(insights_cache_key)
        
        # Invalidate user's model list cache
        user_model_list_key = f"models:list:user:{effective_user_id}"
        await cache_client.delete(user_model_list_key)
        
        logger.info(f"Deleted model {model_id} and invalidated cache for user {effective_user_id}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting model {model_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the model."
        )

@router.get("/stats/cache")
async def get_cache_stats():
    """
    Get cache statistics and health information.
    Useful for monitoring and debugging.
    """
    try:
        is_healthy = await cache_client.client.ping() if cache_client.client else False
        
        # Get some basic cache info
        cache_info = {
            "redis_healthy": is_healthy,
            "cache_client_initialized": cache_client._initialized,
        }
        
        if is_healthy:
            info = await cache_client.client.info()
            cache_info.update({
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed")
            })
        
        return cache_info
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {"error": "Could not retrieve cache statistics"}

# Health check endpoint
@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """
    Health check endpoint that verifies database and cache connectivity.
    """
    try:
        # Check database
        await db.execute(select(func.count(MLModel.id)))
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_healthy = False
    
    # Check cache
    try:
        cache_healthy = await cache_client.client.ping() if cache_client.client else False
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        cache_healthy = False
    
    status_code = status.HTTP_200_OK if (db_healthy and cache_healthy) else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "healthy" if (db_healthy and cache_healthy) else "unhealthy",
        "database": "healthy" if db_healthy else "unhealthy", 
        "cache": "healthy" if cache_healthy else "unhealthy"
    }