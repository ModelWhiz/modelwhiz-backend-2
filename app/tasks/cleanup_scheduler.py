import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from ..utils.file_cleanup import cleanup_old_files, get_storage_usage, emergency_cleanup
from ..utils.storage_monitor import StorageMonitor

logger = logging.getLogger(__name__)

class CleanupScheduler:
    def __init__(self):
        self.storage_monitor = StorageMonitor()
        self.is_running = False
        
    async def daily_cleanup_task(self):
        """Run daily cleanup of old files"""
        try:
            logger.info("Starting daily cleanup task...")
            
            # Clean up files older than 7 days
            result = await cleanup_old_files(days_old=7)
            
            # Check storage status
            storage_status = await self.storage_monitor.check_storage_status()
            
            logger.info(f"Daily cleanup completed: {result}")
            logger.info(f"Storage status: {storage_status.get('status', 'unknown')}")
            
            return {
                "cleanup_result": result,
                "storage_status": storage_status,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Daily cleanup task failed: {str(e)}")
            raise
    
    async def hourly_monitoring_task(self):
        """Run hourly storage monitoring"""
        try:
            logger.info("Starting hourly storage monitoring...")
            
            # Get storage usage (this is a sync function, don't await it)
            usage_info = get_storage_usage()
            
            # Check if emergency cleanup is needed
            if usage_info.get("alert_level") == "critical":
                logger.warning("Storage critical - triggering emergency cleanup")
                emergency_result = await emergency_cleanup()
                usage_info["emergency_cleanup"] = emergency_result
            
            # Generate detailed report
            report = await self.storage_monitor.generate_storage_report()
            
            logger.info(f"Hourly monitoring completed. Usage: {usage_info.get('used_mb', 0)}MB")
            
            return {
                "usage_info": usage_info,
                "report": report,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Hourly monitoring task failed: {str(e)}")
            raise
    
    async def start_scheduler(self):
        """Start the cleanup scheduler"""
        if self.is_running:
            logger.warning("Cleanup scheduler is already running")
            return
        
        self.is_running = True
        logger.info("Starting cleanup scheduler...")
        
        try:
            # Run initial cleanup
            await self.daily_cleanup_task()
            
            # Set up periodic tasks
            while self.is_running:
                try:
                    # Run hourly monitoring
                    await self.hourly_monitoring_task()
                    
                    # Check if it's time for daily cleanup (run at 2 AM)
                    now = datetime.now()
                    if now.hour == 2 and now.minute < 5:  # Run between 2:00-2:04 AM
                        await self.daily_cleanup_task()
                    
                    # Wait for 1 hour
                    await asyncio.sleep(3600)
                    
                except Exception as e:
                    logger.error(f"Scheduler task error: {str(e)}")
                    await asyncio.sleep(300)  # Wait 5 minutes before retrying
                    
        except Exception as e:
            logger.error(f"Cleanup scheduler failed: {str(e)}")
            self.is_running = False
            raise
    
    async def stop_scheduler(self):
        """Stop the cleanup scheduler"""
        self.is_running = False
        logger.info("Cleanup scheduler stopped")

# Global scheduler instance
cleanup_scheduler = CleanupScheduler()

async def startup_storage_management():
    """Start storage management on application startup"""
    try:
        # Initialize storage monitoring
        storage_monitor = StorageMonitor()
        initial_status = await storage_monitor.check_storage_status()
        
        logger.info(f"Storage status on startup: {initial_status.get('status', 'unknown')} - "
                   f"{initial_status.get('used_mb', 0):.2f}MB used")
        
        # Start cleanup scheduler in background
        asyncio.create_task(cleanup_scheduler.start_scheduler())
        
        logger.info("Storage management initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize storage management: {str(e)}")
        raise

async def shutdown_storage_management():
    """Stop storage management on application shutdown"""
    try:
        await cleanup_scheduler.stop_scheduler()
        logger.info("Storage management shutdown completed")
    except Exception as e:
        logger.error(f"Error during storage management shutdown: {str(e)}")
