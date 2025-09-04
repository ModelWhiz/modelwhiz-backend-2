"""
Task queue utilities for ModelWhiz background workers.
Provides helpers for task management, retries, and monitoring.
"""

from celery.result import AsyncResult
from app.workers.celery_app import celery_app

def get_task_status(task_id: str):
    """
    Get the current status and progress of a Celery task.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    status = task_result.status
    info = task_result.info if task_result.info else {}
    progress = info.get('current', 0)
    total = info.get('total', 100)
    message = info.get('status', '')
    return {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "total": total,
        "message": message
    }

def revoke_task(task_id: str, terminate: bool = False):
    """
    Revoke a running or pending task.
    If terminate=True, attempts to terminate the task.
    """
    celery_app.control.revoke(task_id, terminate=terminate)

def retry_task(task, exc, countdown=30, max_retries=3):
    """
    Retry a task with exponential backoff.
    """
    try:
        task.retry(exc=exc, countdown=countdown, max_retries=max_retries)
    except Exception as e:
        # Log retry failure
        from app.utils.logger import get_logger
        logger = get_logger()
        logger.error(f"Failed to retry task {task.request.id}: {e}")
        raise
