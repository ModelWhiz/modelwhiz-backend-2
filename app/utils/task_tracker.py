"""
Task progress tracking and management utilities for ModelWhiz.
Provides real-time progress updates, task management, and result caching.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from celery.result import AsyncResult

from app.workers.celery_app import celery_app
from app.utils.logger import get_logger
from app.utils.error_monitor import track_error, ErrorTypes
from app.cache.redis_client import cache_client

logger = get_logger()

class TaskTracker:
    """Task progress tracking and management system"""
    
    def __init__(self):
        self.progress_cache_prefix = "task:progress:"
        self.result_cache_prefix = "task:result:"
        self.cache_ttl = 3600  # 1 hour TTL for task results
    
    async def update_task_progress(self, task_id: str, progress: Dict[str, Any]):
        """
        Update task progress in Redis cache for real-time access.
        """
        try:
            if cache_client.client:
                progress_data = {
                    "task_id": task_id,
                    "progress": progress.get("current", 0),
                    "total": progress.get("total", 100),
                    "status": progress.get("status", ""),
                    "message": progress.get("message", ""),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                cache_key = f"{self.progress_cache_prefix}{task_id}"
                await cache_client.client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(progress_data)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to update task progress for {task_id}: {e}")
            track_error(ErrorTypes.CACHE, f"Task progress update failed: {e}")
        
        return False
    
    async def get_task_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task progress from Redis cache.
        """
        try:
            if cache_client.client:
                cache_key = f"{self.progress_cache_prefix}{task_id}"
                progress_data = await cache_client.client.get(cache_key)
                if progress_data:
                    return json.loads(progress_data)
        except Exception as e:
            logger.error(f"Failed to get task progress for {task_id}: {e}")
        
        return None
    
    async def cache_task_result(self, task_id: str, result: Any):
        """
        Cache task result for fast retrieval.
        """
        try:
            if cache_client.client:
                result_data = {
                    "task_id": task_id,
                    "result": result,
                    "cached_at": datetime.utcnow().isoformat(),
                    "expires_at": (datetime.utcnow() + timedelta(seconds=self.cache_ttl)).isoformat()
                }
                
                cache_key = f"{self.result_cache_prefix}{task_id}"
                await cache_client.client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(result_data, default=str)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to cache task result for {task_id}: {e}")
            track_error(ErrorTypes.CACHE, f"Task result caching failed: {e}")
        
        return False
    
    async def get_cached_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached task result.
        """
        try:
            if cache_client.client:
                cache_key = f"{self.result_cache_prefix}{task_id}"
                result_data = await cache_client.client.get(cache_key)
                if result_data:
                    return json.loads(result_data)
        except Exception as e:
            logger.error(f"Failed to get cached result for {task_id}: {e}")
        
        return None
    
    async def cleanup_expired_tasks(self):
        """
        Clean up expired task progress and result entries.
        """
        try:
            if cache_client.client:
                # Clean progress cache
                progress_keys = []
                async for key in cache_client.client.scan_iter(match=f"{self.progress_cache_prefix}*"):
                    progress_keys.append(key)
                
                for key in progress_keys:
                    ttl = await cache_client.client.ttl(key)
                    if ttl < 300:  # Less than 5 minutes left
                        await cache_client.client.delete(key)
                
                # Clean result cache
                result_keys = []
                async for key in cache_client.client.scan_iter(match=f"{self.result_cache_prefix}*"):
                    result_keys.append(key)
                
                for key in result_keys:
                    ttl = await cache_client.client.ttl(key)
                    if ttl < 300:  # Less than 5 minutes left
                        await cache_client.client.delete(key)
                
                logger.info(f"Cleaned up {len(progress_keys) + len(result_keys)} expired task entries")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired tasks: {e}")
            track_error(ErrorTypes.CACHE, f"Task cleanup failed: {e}")
        
        return False
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get comprehensive task status including progress and result.
        """
        task_result = AsyncResult(task_id, app=celery_app)
        
        status_info = {
            "task_id": task_id,
            "status": task_result.status,
            "ready": task_result.ready(),
            "successful": task_result.successful(),
            "failed": task_result.failed(),
            "state": task_result.state,
            "info": task_result.info if task_result.info else {}
        }
        
        # Add progress information if available
        if task_result.info and isinstance(task_result.info, dict):
            status_info.update({
                "progress": task_result.info.get("current", 0),
                "total": task_result.info.get("total", 100),
                "message": task_result.info.get("status", "")
            })
        
        return status_info
    
    async def retry_task_with_backoff(self, task, exc, max_retries: int = 3, base_delay: int = 30):
        """
        Retry task with exponential backoff strategy.
        """
        try:
            retry_count = getattr(task.request, "retries", 0) + 1
            
            if retry_count > max_retries:
                logger.error(f"Task {task.request.id} failed after {max_retries} retries")
                track_error(ErrorTypes.TASK, f"Task {task.request.id} failed after maximum retries")
                return False
            
            # Exponential backoff: 30s, 60s, 120s, etc.
            delay = base_delay * (2 ** (retry_count - 1))
            
            logger.warning(f"Retrying task {task.request.id} (attempt {retry_count}/{max_retries}) in {delay}s")
            
            task.retry(exc=exc, countdown=delay, max_retries=max_retries)
            return True
            
        except Exception as e:
            logger.error(f"Failed to retry task {task.request.id}: {e}")
            track_error(ErrorTypes.TASK, f"Task retry failed: {e}")
            return False

# Global task tracker instance
task_tracker = TaskTracker()

# Convenience functions
async def update_progress(task_id: str, progress: Dict[str, Any]):
    """Update task progress"""
    return await task_tracker.update_task_progress(task_id, progress)

async def get_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task progress"""
    return await task_tracker.get_task_progress(task_id)

async def cache_result(task_id: str, result: Any):
    """Cache task result"""
    return await task_tracker.cache_task_result(task_id, result)

async def get_cached_result(task_id: str) -> Optional[Dict[str, Any]]:
    """Get cached task result"""
    return await task_tracker.get_cached_result(task_id)

def get_status(task_id: str) -> Dict[str, Any]:
    """Get task status"""
    return task_tracker.get_task_status(task_id)

async def cleanup_tasks():
    """Clean up expired tasks"""
    return await task_tracker.cleanup_expired_tasks()
