import os
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

def validate_file_size(file_path: str, max_size_mb: int = 100) -> bool:
    """
    Validate the size of the file against maximum allowed size.
    
    Args:
        file_path: Path to the file to validate
        max_size_mb: Maximum allowed file size in MB (default: 100MB)
    
    Returns:
        bool: True if file size is within limits, False otherwise
    """
    try:
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
        if file_size > max_size_mb:
            logger.error(f"File {file_path} exceeds size limit of {max_size_mb}MB. Size: {file_size:.2f}MB")
            return False
        logger.info(f"File {file_path} size validation passed: {file_size:.2f}MB")
        return True
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return False
    except Exception as e:
        logger.error(f"Error validating file size for {file_path}: {e}")
        return False

def validate_file_type(file_path: str, allowed_extensions: List[str] = None) -> bool:
    """
    Validate the file type based on extension.
    
    Args:
        file_path: Path to the file to validate
        allowed_extensions: List of allowed file extensions (default: ['.csv', '.zip'])
    
    Returns:
        bool: True if file type is allowed, False otherwise
    """
    if allowed_extensions is None:
        allowed_extensions = ['.csv', '.zip']
    
    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in allowed_extensions:
        logger.error(f"File type not allowed: {file_extension}. Allowed: {allowed_extensions}")
        return False
    logger.info(f"File type validation passed: {file_extension}")
    return True

async def cleanup_old_files(days_old: int = 7) -> Dict[str, Any]:
    """
    Remove files older than a specified number of days.
    
    Args:
        days_old: Number of days to consider files as old (default: 7)
    
    Returns:
        Dict with cleanup results
    """
    cutoff_date = datetime.now() - timedelta(days=days_old)
    uploads_dir = "uploads/eval_jobs/"
    removed_files = []
    errors = []
    
    if not os.path.exists(uploads_dir):
        logger.warning(f"Uploads directory not found: {uploads_dir}")
        return {"removed": 0, "errors": 0, "message": "No uploads directory found"}
    
    for root, dirs, files in os.walk(uploads_dir):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mod_time < cutoff_date:
                    os.remove(file_path)
                    removed_files.append(file_path)
                    logger.info(f"Removed old file: {file_path}")
            except Exception as e:
                errors.append(f"Error removing {file_path}: {e}")
                logger.error(f"Error removing file {file_path}: {e}")
    
    result = {
        "removed": len(removed_files),
        "errors": len(errors),
        "cutoff_date": cutoff_date.isoformat(),
        "message": f"Cleaned up {len(removed_files)} files older than {days_old} days"
    }
    
    if errors:
        result["error_details"] = errors
    
    return result

def cleanup_model_files(model_id: int) -> Dict[str, Any]:
    """
    Remove all files associated with a deleted model.
    
    Args:
        model_id: ID of the model to clean up
    
    Returns:
        Dict with cleanup results
    """
    model_dir = f"uploads/eval_jobs/{model_id}/"
    result = {"model_id": model_id, "removed": False, "error": None}
    
    if os.path.exists(model_dir):
        try:
            shutil.rmtree(model_dir)
            result["removed"] = True
            logger.info(f"Removed model directory: {model_dir}")
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error removing model directory {model_dir}: {e}")
    else:
        logger.info(f"Model directory not found: {model_dir}")
    
    return result

async def emergency_cleanup() -> Dict[str, Any]:
    """
    Perform emergency cleanup to free up space when storage is critical.
    
    Returns:
        Dict with emergency cleanup results
    """
    logger.warning("🚨 Performing emergency cleanup due to critical storage situation")
    
    # Clean up files older than 1 day first
    result1 = await cleanup_old_files(days_old=1)
    
    # If still critical, clean up files older than 3 days
    storage_info = get_storage_usage()
    if storage_info.get("alert_level") == "critical":
        result2 = await cleanup_old_files(days_old=3)
        result1["emergency_phase2"] = result2
    
    logger.info("Emergency cleanup completed")
    return {
        "emergency_cleanup": result1,
        "storage_status": storage_info,
        "timestamp": datetime.utcnow().isoformat()
    }

def get_storage_usage(base_path: str = "uploads/") -> Dict[str, Any]:
    """
    Get current storage usage statistics.
    
    Args:
        base_path: Base path to check storage usage
    
    Returns:
        Dict with storage usage information
    """
    try:
        total, used, free = shutil.disk_usage(base_path)
        total_mb = total // (1024 * 1024)
        used_mb = used // (1024 * 1024)
        free_mb = free // (1024 * 1024)
        
        # Determine alert level
        alert_level = "normal"
        if free_mb < 5120:  # Less than 5GB free
            alert_level = "warning"
        if free_mb < 1024:   # Less than 1GB free
            alert_level = "critical"
        
        return {
            "total_size_mb": total_mb,
            "used_size_mb": used_mb,
            "free_size_mb": free_mb,
            "alert_level": alert_level,
            "usage_percentage": (used_mb / total_mb * 100) if total_mb > 0 else 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting storage usage: {e}")
        return {
            "error": str(e),
            "alert_level": "error",
            "timestamp": datetime.utcnow().isoformat()
        }

def cleanup_failed_evaluations() -> Dict[str, Any]:
    """
    Clean up files from failed evaluation jobs.
    
    Returns:
        Dict with cleanup results
    """
    # This would typically interface with the database to find failed jobs
    # For now, we'll clean up empty or incomplete directories
    uploads_dir = "uploads/eval_jobs/"
    cleaned_dirs = []
    errors = []
    
    if not os.path.exists(uploads_dir):
        return {"cleaned": 0, "errors": 0}
    
    for job_dir in os.listdir(uploads_dir):
        job_path = os.path.join(uploads_dir, job_dir)
        if os.path.isdir(job_path):
            # Check if directory is empty or contains only partial files
            try:
                files = os.listdir(job_path)
                if not files or all(file.endswith('.tmp') for file in files):
                    shutil.rmtree(job_path)
                    cleaned_dirs.append(job_dir)
                    logger.info(f"Cleaned failed evaluation directory: {job_dir}")
            except Exception as e:
                errors.append(f"Error cleaning {job_dir}: {e}")
    
    return {
        "cleaned_directories": cleaned_dirs,
        "errors": errors,
        "total_cleaned": len(cleaned_dirs)
    }
