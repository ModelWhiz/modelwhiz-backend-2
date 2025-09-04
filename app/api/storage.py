from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
import os
import asyncio
from typing import Dict, Any, Optional
from ..utils.file_cleanup import (
    cleanup_old_files, 
    get_storage_usage, 
    emergency_cleanup,
    cleanup_model_files,
    cleanup_failed_evaluations,
    validate_file_size,
    validate_file_type
)
from ..utils.storage_monitor import StorageMonitor

router = APIRouter()

# Initialize storage monitor
storage_monitor = StorageMonitor()

@router.get("/usage")
async def get_storage_usage_endpoint():
    """
    Get current storage usage statistics.
    
    Returns:
        JSON response with storage usage information including:
        - total_size_mb: Total storage capacity in MB
        - used_size_mb: Currently used storage in MB
        - free_size_mb: Free storage space in MB
        - alert_level: Storage status (normal, warning, critical)
        - usage_percentage: Percentage of storage used
    """
    try:
        usage_info = get_storage_usage()
        return JSONResponse(content=usage_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get storage usage: {str(e)}")

@router.post("/cleanup/old-files")
async def cleanup_old_files_endpoint(
    days_old: int = Query(7, description="Number of days to consider files as old", ge=1),
    background_tasks: BackgroundTasks = None
):
    """
    Trigger cleanup of files older than specified days.
    
    Args:
        days_old: Number of days to consider files as old (default: 7)
        background_tasks: Background tasks manager for async execution
    
    Returns:
        Cleanup results with count of removed files and any errors
    """
    try:
        if background_tasks:
            # Run cleanup in background for better performance
            background_tasks.add_task(cleanup_old_files, days_old)
            return {
                "message": f"Cleanup scheduled for files older than {days_old} days",
                "scheduled": True,
                "days_old": days_old
            }
        else:
            # Run cleanup synchronously and return detailed results
            result = await cleanup_old_files(days_old)
            return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

@router.post("/emergency-cleanup")
async def emergency_cleanup_endpoint():
    """
    Trigger emergency cleanup when storage is critical.
    
    This endpoint performs aggressive cleanup to free up space quickly.
    It cleans files older than 1 day first, then 3 days if still critical.
    
    Returns:
        Emergency cleanup results with storage status
    """
    try:
        result = await emergency_cleanup()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emergency cleanup failed: {str(e)}")

@router.get("/status")
async def get_storage_status(detailed: bool = Query(False, description="Include detailed analysis")):
    """
    Get detailed storage status with monitoring and trend analysis.
    
    Args:
        detailed: Whether to include detailed file analysis
    
    Returns:
        Comprehensive storage status with trend information
    """
    try:
        status = await storage_monitor.check_storage_status()
        if detailed:
            detailed_analysis = await storage_monitor._analyze_storage_usage()
            status["detailed_analysis"] = detailed_analysis
        return JSONResponse(content=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get storage status: {str(e)}")

@router.get("/report")
async def generate_storage_report(detailed: bool = Query(True, description="Include detailed file analysis")):
    """
    Generate comprehensive storage report with analysis and recommendations.
    
    Args:
        detailed: Whether to include detailed file analysis
    
    Returns:
        Complete storage report with history, trends, and recommendations
    """
    try:
        report = await storage_monitor.generate_storage_report(detailed=detailed)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate storage report: {str(e)}")

@router.delete("/model/{model_id}")
async def cleanup_model_files_endpoint(model_id: int):
    """
    Remove all files associated with a specific model.
    
    Args:
        model_id: ID of the model to clean up
    
    Returns:
        Cleanup results for the specified model
    """
    try:
        result = cleanup_model_files(model_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clean up model files: {str(e)}")

@router.post("/cleanup/failed-evaluations")
async def cleanup_failed_evaluations_endpoint():
    """
    Clean up files from failed evaluation jobs.
    
    This endpoint removes directories from evaluations that failed
    or were incomplete, helping to reclaim wasted storage space.
    
    Returns:
        Cleanup results for failed evaluations
    """
    try:
        result = cleanup_failed_evaluations()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clean up failed evaluations: {str(e)}")

@router.get("/trend")
async def get_storage_trend(hours: int = Query(24, description="Number of hours to analyze", ge=1, le=168)):
    """
    Get storage usage trend over specified time period.
    
    Args:
        hours: Number of hours to analyze (1-168, default: 24)
    
    Returns:
        Storage usage trend analysis over the specified period
    """
    try:
        trend = await storage_monitor.get_usage_trend(hours)
        return JSONResponse(content=trend)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get storage trend: {str(e)}")

@router.post("/validate/file")
async def validate_file_endpoint(
    file_path: str = Query(..., description="Path to the file to validate"),
    max_size_mb: int = Query(100, description="Maximum allowed file size in MB", ge=1),
    allowed_extensions: Optional[str] = Query(None, description="Comma-separated list of allowed extensions")
):
    """
    Validate a file for size and type constraints.
    
    Args:
        file_path: Path to the file to validate
        max_size_mb: Maximum allowed file size in MB
        allowed_extensions: Optional comma-separated list of allowed extensions
    
    Returns:
        Validation results with detailed information
    """
    try:
        # Parse allowed extensions if provided
        extensions_list = None
        if allowed_extensions:
            extensions_list = [ext.strip().lower() for ext in allowed_extensions.split(',')]
        
        # Validate file size
        size_valid = validate_file_size(file_path, max_size_mb)
        
        # Validate file type if extensions provided
        type_valid = True
        if extensions_list:
            type_valid = validate_file_type(file_path, extensions_list)
        
        return {
            "file_path": file_path,
            "size_validation": {
                "valid": size_valid,
                "max_size_mb": max_size_mb,
                "actual_size_mb": os.path.getsize(file_path) / (1024 * 1024) if os.path.exists(file_path) else 0
            },
            "type_validation": {
                "valid": type_valid,
                "allowed_extensions": extensions_list,
                "actual_extension": os.path.splitext(file_path)[1].lower() if os.path.exists(file_path) else ""
            },
            "overall_valid": size_valid and type_valid,
            "timestamp": asyncio.get_event_loop().time()
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File validation failed: {str(e)}")

@router.get("/health")
async def storage_health_check():
    """
    Health check endpoint for storage system.
    
    Returns:
        Health status of the storage management system
    """
    try:
        # Test basic functionality
        usage = get_storage_usage()
        status = await storage_monitor.check_storage_status()
        
        return {
            "status": "healthy",
            "storage_accessible": True,
            "monitor_working": True,
            "current_usage": usage,
            "monitor_status": status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "storage_accessible": False,
            "monitor_working": False,
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time()
        }