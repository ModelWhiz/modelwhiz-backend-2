import os
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

class StorageMonitor:
    def __init__(self, base_path: str = "uploads/"):
        self.base_path = base_path
        self.last_check = None
        self.history = []
        self.max_history_size = 100  # Keep last 100 checks
    
    async def check_storage_status(self) -> Dict[str, Any]:
        """
        Check the current storage status with detailed analysis.
        
        Returns:
            Dict with comprehensive storage status information
        """
        try:
            total, used, free = shutil.disk_usage(self.base_path)
            
            # Convert to MB for readability
            total_mb = total // (1024 * 1024)
            used_mb = used // (1024 * 1024)
            free_mb = free // (1024 * 1024)
            
            # Determine alert level with multiple thresholds
            alert_level = "normal"
            if free_mb < 5120:  # Less than 5GB free
                alert_level = "warning"
            if free_mb < 2048:  # Less than 2GB free
                alert_level = "high_warning"
            if free_mb < 1024:   # Less than 1GB free
                alert_level = "critical"
            
            # Calculate usage percentages
            usage_percentage = (used_mb / total_mb * 100) if total_mb > 0 else 0
            
            # Update history
            status_data = {
                "status": alert_level,
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "usage_percentage": round(usage_percentage, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "trend": self._calculate_trend(usage_percentage)
            }
            
            self.last_check = status_data
            self.history.append(status_data)
            
            # Keep history size manageable
            if len(self.history) > self.max_history_size:
                self.history = self.history[-self.max_history_size:]
            
            return status_data
            
        except Exception as e:
            error_data = {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.error(f"Error checking storage status: {e}")
            return error_data
    
    def _calculate_trend(self, current_usage: float) -> str:
        """
        Calculate storage usage trend based on history.
        
        Args:
            current_usage: Current storage usage percentage
            
        Returns:
            Trend indicator: 'increasing', 'decreasing', or 'stable'
        """
        if len(self.history) < 2:
            return "unknown"
        
        # Get last few data points for trend analysis
        recent_data = self.history[-5:] if len(self.history) >= 5 else self.history
        
        usage_values = [data.get("usage_percentage", 0) for data in recent_data]
        
        if len(usage_values) < 2:
            return "unknown"
        
        # Simple trend calculation
        first = usage_values[0]
        last = usage_values[-1]
        
        if last > first + 5:  # More than 5% increase
            return "increasing"
        elif last < first - 5:  # More than 5% decrease
            return "decreasing"
        else:
            return "stable"
    
    async def generate_storage_report(self, detailed: bool = True) -> Dict[str, Any]:
        """
        Generate a comprehensive storage report with analysis.
        
        Args:
            detailed: Whether to include detailed file analysis
            
        Returns:
            Comprehensive storage report
        """
        storage_status = await self.check_storage_status()
        
        report = {
            **storage_status,
            "report_generated_at": datetime.utcnow().isoformat(),
            "recommendations": self._generate_recommendations(storage_status),
            "history_summary": self._get_history_summary()
        }
        
        if detailed:
            detailed_analysis = await self._analyze_storage_usage()
            report.update(detailed_analysis)
        
        return report
    
    async def _analyze_storage_usage(self) -> Dict[str, Any]:
        """
        Analyze storage usage by directory and file types.
        
        Returns:
            Detailed storage analysis
        """
        eval_jobs_dir = os.path.join(self.base_path, "eval_jobs")
        analysis = {
            "total_jobs": 0,
            "total_files": 0,
            "total_storage_used_mb": 0,
            "file_type_breakdown": {},
            "largest_files": [],
            "oldest_files": []
        }
        
        if not os.path.exists(eval_jobs_dir):
            return analysis
        
        try:
            # Walk through all evaluation job directories
            for job_dir in os.listdir(eval_jobs_dir):
                job_path = os.path.join(eval_jobs_dir, job_dir)
                if os.path.isdir(job_path):
                    analysis["total_jobs"] += 1
                    
                    for root, dirs, files in os.walk(job_path):
                        analysis["total_files"] += len(files)
                        
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                file_size = os.path.getsize(file_path) // (1024 * 1024)  # MB
                                file_extension = os.path.splitext(file)[1].lower()
                                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                                
                                analysis["total_storage_used_mb"] += file_size
                                
                                # Update file type breakdown
                                analysis["file_type_breakdown"][file_extension] = \
                                    analysis["file_type_breakdown"].get(file_extension, 0) + file_size
                                
                                # Track largest files
                                analysis["largest_files"].append({
                                    "path": file_path,
                                    "size_mb": file_size,
                                    "modified": file_mtime.isoformat()
                                })
                                
                                # Track oldest files
                                analysis["oldest_files"].append({
                                    "path": file_path,
                                    "modified": file_mtime.isoformat(),
                                    "age_days": (datetime.now() - file_mtime).days
                                })
                                
                            except Exception as e:
                                logger.warning(f"Error analyzing file {file_path}: {e}")
            
            # Sort and limit largest/oldest files lists
            analysis["largest_files"].sort(key=lambda x: x["size_mb"], reverse=True)
            analysis["largest_files"] = analysis["largest_files"][:10]  # Top 10 largest
            
            analysis["oldest_files"].sort(key=lambda x: x["age_days"], reverse=True)
            analysis["oldest_files"] = analysis["oldest_files"][:10]  # Top 10 oldest
            
        except Exception as e:
            logger.error(f"Error during storage analysis: {e}")
            analysis["analysis_error"] = str(e)
        
        return analysis
    
    def _get_history_summary(self) -> Dict[str, Any]:
        """
        Get summary of storage history.
        
        Returns:
            History summary statistics
        """
        if not self.history:
            return {"message": "No history data available"}
        
        recent_history = self.history[-24:]  # Last 24 checks (approx 1 day if hourly)
        
        usage_values = [data.get("usage_percentage", 0) for data in recent_history]
        status_counts = {}
        
        for data in recent_history:
            status = data.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "period_hours": len(recent_history),
            "average_usage": round(sum(usage_values) / len(usage_values), 2) if usage_values else 0,
            "max_usage": round(max(usage_values), 2) if usage_values else 0,
            "min_usage": round(min(usage_values), 2) if usage_values else 0,
            "status_distribution": status_counts,
            "trend": self._calculate_trend(usage_values[-1] if usage_values else 0)
        }
    
    def _generate_recommendations(self, status: Dict[str, Any]) -> List[str]:
        """
        Generate storage recommendations based on current status.
        
        Args:
            status: Current storage status data
            
        Returns:
            List of recommendations
        """
        recommendations = []
        alert_level = status.get("status", "normal")
        free_mb = status.get("free_mb", 0)
        
        if alert_level == "critical":
            recommendations.append("🚨 CRITICAL: Storage space critically low!")
            recommendations.append("🆘 Perform emergency cleanup immediately")
            recommendations.append("🗑️ Delete files older than 1 day")
            recommendations.append("📦 Archive completed evaluation jobs")
            recommendations.append("⚠️ Consider increasing storage capacity")
            
        elif alert_level == "high_warning":
            recommendations.append("⚠️ HIGH WARNING: Storage space very low")
            recommendations.append("🗑️ Clean up files older than 3 days")
            recommendations.append("📊 Monitor usage closely")
            recommendations.append("🔄 Schedule regular cleanup tasks")
            
        elif alert_level == "warning":
            recommendations.append("📢 WARNING: Storage space running low")
            recommendations.append("🗑️ Clean up files older than 7 days")
            recommendations.append("📈 Review storage growth trends")
            recommendations.append("🔍 Identify large files for cleanup")
            
        else:
            recommendations.append("✅ Storage status: Normal")
            recommendations.append("📊 Continue regular monitoring")
            recommendations.append("🔄 Schedule preventive maintenance")
            
        # Add general recommendations
        recommendations.append(f"💾 Free space: {free_mb}MB available")
        recommendations.append("📋 Use /api/storage/report for detailed analysis")
        
        return recommendations
    
    async def get_usage_trend(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get storage usage trend over specified hours.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Trend analysis
        """
        if not self.history:
            return {"message": "No history data available"}
        
        relevant_data = [data for data in self.history 
                        if datetime.fromisoformat(data["timestamp"]) > datetime.utcnow() - timedelta(hours=hours)]
        
        if not relevant_data:
            return {"message": f"No data for the last {hours} hours"}
        
        usage_values = [data.get("usage_percentage", 0) for data in relevant_data]
        
        return {
            "period_hours": hours,
            "data_points": len(relevant_data),
            "average_usage": round(sum(usage_values) / len(usage_values), 2),
            "trend": self._calculate_trend(usage_values[-1]),
            "timeline": relevant_data
        }
