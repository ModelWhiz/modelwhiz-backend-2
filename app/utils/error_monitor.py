"""
Error monitoring and alerting system for ModelWhiz backend
Tracks error rates, patterns, and triggers alerts for critical errors
"""

import asyncio
import time
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import json
import os
from .logger import get_logger

# Try to import Redis for persistent error tracking
try:
    from app.cache.redis_client import cache_client
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    cache_client = None

logger = get_logger()

class ErrorMonitor:
    """Monitors error rates and patterns for alerting with Redis persistence"""
    
    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_timestamps = defaultdict(list)
        self.alert_thresholds = {
            "critical": int(os.getenv("ERROR_ALERT_CRITICAL", "10")),  # 10 errors per minute
            "warning": int(os.getenv("ERROR_ALERT_WARNING", "5")),     # 5 errors per minute
            "normal": int(os.getenv("ERROR_ALERT_NORMAL", "1"))        # 1 error per minute
        }
        self.alert_cooldown = int(os.getenv("ERROR_ALERT_COOLDOWN", "300"))  # 5 minutes
        self.last_alert_time = {}
        self.error_patterns = defaultdict(set)
        self.redis_enabled = REDIS_AVAILABLE
        
    async def track_error(self, error_type: str, error_message: str, request_id: Optional[str] = None):
        """Track an error occurrence with Redis persistence"""
        current_time = time.time()
        
        # Update in-memory counters
        self.error_counts[error_type] += 1
        self.error_timestamps[error_type].append(current_time)
        
        # Clean up old timestamps (keep last hour)
        cutoff = current_time - 3600
        self.error_timestamps[error_type] = [
            ts for ts in self.error_timestamps[error_type] if ts > cutoff
        ]
        
        # Track error patterns
        if error_message:
            pattern_key = error_message[:200]  # First 200 chars for better pattern matching
            self.error_patterns[error_type].add(pattern_key)
        
        # Persist to Redis if available
        if self.redis_enabled:
            await self._persist_to_redis(error_type, current_time, error_message, request_id)
        
        # Check if alert should be triggered
        await self._check_alert_conditions(error_type)
        
        # Log the error
        logger.log_error(
            request_id or "system",
            error_type,
            error_message,
            exc_info=False
        )
    
    async def _persist_to_redis(self, error_type: str, timestamp: float, 
                               error_message: str, request_id: Optional[str] = None):
        """Persist error data to Redis for long-term storage and analysis"""
        try:
            error_data = {
                "type": error_type,
                "timestamp": timestamp,
                "message": error_message[:500],  # Limit message length
                "request_id": request_id,
                "environment": os.getenv("ENVIRONMENT", "development")
            }
            
            # Store individual error record
            error_key = f"error:{error_type}:{int(timestamp * 1000)}"
            await cache_client.set(error_key, error_data, ttl=86400)  # 24 hours
            
            # Update error counters in Redis
            counter_key = f"error_stats:{error_type}"
            await cache_client.client.hincrby(counter_key, "total_count", 1)
            await cache_client.client.hincrby(counter_key, "minute_count", 1)
            
            # Set TTL for minute counter (reset after 60 seconds)
            await cache_client.client.expire(f"error_stats:{error_type}:minute", 60)
            
        except Exception as e:
            logger.log_error("system", "redis_persistence_error", 
                           f"Failed to persist error to Redis: {e}", exc_info=True)
    
    async def _check_alert_conditions(self, error_type: str):
        """Check if error rate exceeds thresholds and trigger alerts"""
        current_time = time.time()
        
        # Get error rate from Redis if available, otherwise use in-memory
        if self.redis_enabled:
            recent_errors = await self._get_redis_error_rate(error_type)
        else:
            timestamps = self.error_timestamps[error_type]
            minute_ago = current_time - 60
            recent_errors = len([ts for ts in timestamps if ts > minute_ago])
        
        # Check thresholds
        alert_level = None
        if recent_errors >= self.alert_thresholds["critical"]:
            alert_level = "critical"
        elif recent_errors >= self.alert_thresholds["warning"]:
            alert_level = "warning"
        
        # Check cooldown
        last_alert = self.last_alert_time.get(error_type, 0)
        if alert_level and (current_time - last_alert) > self.alert_cooldown:
            await self._trigger_alert(error_type, alert_level, recent_errors)
            self.last_alert_time[error_type] = current_time
    
    async def _get_redis_error_rate(self, error_type: str) -> int:
        """Get error rate from Redis"""
        try:
            count = await cache_client.client.hget(f"error_stats:{error_type}", "minute_count")
            return int(count) if count else 0
        except Exception:
            return 0
    
    async def _trigger_alert(self, error_type: str, level: str, count: int):
        """Trigger an error alert with external integrations"""
        patterns = list(self.error_patterns[error_type])[:10]  # Top 10 patterns
        
        alert_data = {
            "level": level,
            "error_type": error_type,
            "count": count,
            "patterns": patterns,
            "timestamp": datetime.utcnow().isoformat(),
            "environment": os.getenv("ENVIRONMENT", "development")
        }
        
        alert_message = (
            f"🚨 {level.upper()} ALERT: {error_type} errors detected\n"
            f"Count: {count} errors in last minute\n"
            f"Patterns: {patterns}\n"
            f"Time: {datetime.utcnow().isoformat()}\n"
            f"Environment: {os.getenv('ENVIRONMENT', 'development')}"
        )
        
        # Log the alert
        logger.log_error(
            "system",
            f"alert_{level}",
            alert_message,
            exc_info=False
        )
        
        # Send to external alerting services
        await self._send_external_alerts(alert_data)
        
        print(f"ALERT: {alert_message}")
    
    async def _send_external_alerts(self, alert_data: Dict[str, Any]):
        """Send alerts to external services (Slack, Email, etc.)"""
        # Slack integration
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_webhook:
            await self._send_slack_alert(alert_data, slack_webhook)
        
        # Email integration
        email_config = os.getenv("ALERT_EMAILS")
        if email_config:
            await self._send_email_alert(alert_data, email_config.split(','))
    
    async def _send_slack_alert(self, alert_data: Dict[str, Any], webhook_url: str):
        """Send alert to Slack"""
        try:
            import aiohttp
            
            message = {
                "text": f"🚨 {alert_data['level'].upper()} Alert: {alert_data['error_type']}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🚨 {alert_data['level'].upper()} ALERT*: `{alert_data['error_type']}`"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Count:*\n{alert_data['count']} errors/min"},
                            {"type": "mrkdwn", "text": f"*Environment:*\n{alert_data['environment']}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Time:* {alert_data['timestamp']}"
                        }
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message):
                    pass
                    
        except Exception as e:
            logger.log_error("system", "slack_alert_error", 
                           f"Failed to send Slack alert: {e}", exc_info=True)
    
    async def _send_email_alert(self, alert_data: Dict[str, Any], emails: List[str]):
        """Send alert via email (placeholder - integrate with your email service)"""
        # This is a placeholder - integrate with your preferred email service
        # (SendGrid, AWS SES, SMTP, etc.)
        logger.info(f"Would send email alert to {emails} for {alert_data['error_type']}")
    
    def get_error_stats(self, time_window_minutes: int = 60) -> Dict[str, Dict]:
        """Get error statistics for the given time window"""
        cutoff = time.time() - (time_window_minutes * 60)
        stats = {}
        
        for error_type, timestamps in self.error_timestamps.items():
            recent_timestamps = [ts for ts in timestamps if ts > cutoff]
            stats[error_type] = {
                "total_count": len(recent_timestamps),
                "rate_per_minute": len(recent_timestamps) / time_window_minutes,
                "last_occurrence": max(recent_timestamps) if recent_timestamps else None,
                "patterns": list(self.error_patterns[error_type])[:10],
                "redis_enabled": self.redis_enabled
            }
        
        return stats
    
    async def get_redis_error_stats(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive error statistics from Redis"""
        if not self.redis_enabled:
            return {"redis_available": False}
        
        try:
            # Get all error keys from Redis
            error_keys = []
            async for key in cache_client.client.scan_iter(match="error:*:*"):
                error_keys.append(key)
            
            stats = {
                "total_errors": len(error_keys),
                "error_types": defaultdict(int),
                "recent_errors": []
            }
            
            # Get recent errors
            recent_cutoff = time.time() - (time_window_hours * 3600)
            for key in error_keys[-100:]:  # Last 100 errors
                error_data = await cache_client.get(key)
                if error_data and error_data.get("timestamp", 0) > recent_cutoff:
                    stats["error_types"][error_data["type"]] += 1
                    stats["recent_errors"].append(error_data)
            
            return stats
            
        except Exception as e:
            logger.log_error("system", "redis_stats_error", 
                           f"Failed to get Redis stats: {e}", exc_info=True)
            return {"error": str(e)}
    
    def get_error_rate(self, error_type: str, window_minutes: int = 1) -> float:
        """Get error rate for specific error type"""
        cutoff = time.time() - (window_minutes * 60)
        timestamps = self.error_timestamps[error_type]
        recent_errors = len([ts for ts in timestamps if ts > cutoff])
        return recent_errors / window_minutes
    
    async def reset_error_counters(self):
        """Reset all error counters (for testing or maintenance)"""
        self.error_counts.clear()
        self.error_timestamps.clear()
        self.error_patterns.clear()
        self.last_alert_time.clear()
        
        # Also reset Redis counters if available
        if self.redis_enabled:
            try:
                # Delete all error keys
                async for key in cache_client.client.scan_iter(match="error:*"):
                    await cache_client.client.delete(key)
                async for key in cache_client.client.scan_iter(match="error_stats:*"):
                    await cache_client.client.delete(key)
            except Exception as e:
                logger.log_error("system", "redis_reset_error", 
                               f"Failed to reset Redis counters: {e}", exc_info=True)

# Global error monitor instance
error_monitor = ErrorMonitor()

# Convenience functions
async def track_error(error_type: str, error_message: str, request_id: Optional[str] = None):
    """Track an error occurrence"""
    await error_monitor.track_error(error_type, error_message, request_id)

def get_error_stats(time_window_minutes: int = 60) -> Dict[str, Dict]:
    """Get error statistics"""
    return error_monitor.get_error_stats(time_window_minutes)

async def get_redis_error_stats(time_window_hours: int = 24) -> Dict[str, Any]:
    """Get comprehensive error statistics from Redis"""
    return await error_monitor.get_redis_error_stats(time_window_hours)

def get_error_rate(error_type: str, window_minutes: int = 1) -> float:
    """Get error rate for specific type"""
    return error_monitor.get_error_rate(error_type, window_minutes)

async def reset_error_counters():
    """Reset error counters"""
    await error_monitor.reset_error_counters()

# Common error types for consistent tracking
class ErrorTypes:
    DATABASE = "database_error"
    VALIDATION = "validation_error"
    AUTH = "authentication_error"
    PERMISSION = "permission_error"
    FILE = "file_operation_error"
    NETWORK = "network_error"
    CACHE = "cache_error"
    ML = "ml_processing_error"
    UNKNOWN = "unknown_error"
    RATE_LIMIT = "rate_limit_exceeded"
    CONFIG = "configuration_error"
    EXTERNAL = "external_service_error"
    TIMEOUT = "timeout_error"
    MEMORY = "memory_error"
    CPU = "cpu_utilization_error"
