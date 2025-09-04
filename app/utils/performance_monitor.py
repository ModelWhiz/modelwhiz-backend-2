"""
Performance monitoring utilities for ModelWhiz backend
Provides timing decorators and performance tracking for ML operations
"""

import time
import asyncio
from typing import Dict, Any, Optional, Callable
from functools import wraps
from datetime import datetime
from .logger import get_logger, log_performance

logger = get_logger()

class PerformanceMonitor:
    """Performance monitoring system for tracking ML operations and cache performance"""
    
    def __init__(self):
        self.operation_timings = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "total_operations": 0
        }
    
    def track_operation(self, operation_name: str):
        """Decorator to track execution time of synchronous functions"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Log the performance
                    log_performance(operation_name, duration_ms, {
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                        "success": True
                    })
                    
                    # Update internal tracking
                    self._update_operation_stats(operation_name, duration_ms, True)
                    
                    return result
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Log the failed operation
                    log_performance(operation_name, duration_ms, {
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                        "success": False,
                        "error": str(e)
                    })
                    
                    # Update internal tracking
                    self._update_operation_stats(operation_name, duration_ms, False)
                    raise
            
            return wrapper
        return decorator
    
    def track_async_operation(self, operation_name: str):
        """Decorator to track execution time of asynchronous functions"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Log the performance
                    log_performance(operation_name, duration_ms, {
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                        "success": True
                    })
                    
                    # Update internal tracking
                    self._update_operation_stats(operation_name, duration_ms, True)
                    
                    return result
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Log the failed operation
                    log_performance(operation_name, duration_ms, {
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                        "success": False,
                        "error": str(e)
                    })
                    
                    # Update internal tracking
                    self._update_operation_stats(operation_name, duration_ms, False)
                    raise
            
            return wrapper
        return decorator
    
    def _update_operation_stats(self, operation_name: str, duration_ms: float, success: bool):
        """Update internal operation statistics"""
        if operation_name not in self.operation_timings:
            self.operation_timings[operation_name] = {
                "count": 0,
                "total_time_ms": 0,
                "success_count": 0,
                "failure_count": 0,
                "min_time_ms": float('inf'),
                "max_time_ms": 0,
                "last_execution": datetime.utcnow().isoformat()
            }
        
        stats = self.operation_timings[operation_name]
        stats["count"] += 1
        stats["total_time_ms"] += duration_ms
        stats["min_time_ms"] = min(stats["min_time_ms"], duration_ms)
        stats["max_time_ms"] = max(stats["max_time_ms"], duration_ms)
        stats["last_execution"] = datetime.utcnow().isoformat()
        
        if success:
            stats["success_count"] += 1
        else:
            stats["failure_count"] += 1
    
    def track_cache_hit(self, key: str, duration_ms: Optional[float] = None):
        """Track a cache hit"""
        self.cache_stats["hits"] += 1
        self.cache_stats["total_operations"] += 1
        
        logger.log_cache_operation("hit", key, True, duration_ms)
    
    def track_cache_miss(self, key: str, duration_ms: Optional[float] = None):
        """Track a cache miss"""
        self.cache_stats["misses"] += 1
        self.cache_stats["total_operations"] += 1
        
        logger.log_cache_operation("miss", key, False, duration_ms)
    
    def track_cache_operation(self, operation: str, key: str, 
                            hit: Optional[bool] = None, duration_ms: Optional[float] = None):
        """Track a generic cache operation"""
        if hit is not None:
            if hit:
                self.track_cache_hit(key, duration_ms)
            else:
                self.track_cache_miss(key, duration_ms)
        else:
            self.cache_stats["total_operations"] += 1
            logger.log_cache_operation(operation, key, hit, duration_ms)
    
    def get_operation_stats(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Get performance statistics for operations"""
        if operation_name:
            return self.operation_timings.get(operation_name, {})
        
        # Return aggregate stats for all operations
        total_stats = {
            "total_operations": 0,
            "total_time_ms": 0,
            "success_count": 0,
            "failure_count": 0,
            "operations": {}
        }
        
        for op_name, stats in self.operation_timings.items():
            total_stats["total_operations"] += stats["count"]
            total_stats["total_time_ms"] += stats["total_time_ms"]
            total_stats["success_count"] += stats["success_count"]
            total_stats["failure_count"] += stats["failure_count"]
            total_stats["operations"][op_name] = stats
        
        if total_stats["total_operations"] > 0:
            total_stats["avg_time_ms"] = total_stats["total_time_ms"] / total_stats["total_operations"]
            total_stats["success_rate"] = (total_stats["success_count"] / total_stats["total_operations"]) * 100
        
        return total_stats
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        hits = self.cache_stats["hits"]
        misses = self.cache_stats["misses"]
        total = self.cache_stats["total_operations"]
        
        stats = self.cache_stats.copy()
        
        if total > 0:
            stats["hit_rate"] = (hits / total) * 100
            stats["miss_rate"] = (misses / total) * 100
        else:
            stats["hit_rate"] = 0
            stats["miss_rate"] = 0
        
        return stats
    
    def reset_stats(self):
        """Reset all performance statistics"""
        self.operation_timings.clear()
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "total_operations": 0
        }

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

# Convenience decorators
def track_performance(operation_name: str):
    """Decorator to track performance of synchronous functions"""
    return performance_monitor.track_operation(operation_name)

def track_async_performance(operation_name: str):
    """Decorator to track performance of asynchronous functions"""
    return performance_monitor.track_async_operation(operation_name)

# Convenience functions
def get_performance_stats(operation_name: Optional[str] = None) -> Dict[str, Any]:
    """Get performance statistics"""
    return performance_monitor.get_operation_stats(operation_name)

def get_cache_performance_stats() -> Dict[str, Any]:
    """Get cache performance statistics"""
    return performance_monitor.get_cache_stats()

def track_cache_hit(key: str, duration_ms: Optional[float] = None):
    """Track a cache hit"""
    performance_monitor.track_cache_hit(key, duration_ms)

def track_cache_miss(key: str, duration_ms: Optional[float] = None):
    """Track a cache miss"""
    performance_monitor.track_cache_miss(key, duration_ms)

def reset_performance_stats():
    """Reset performance statistics"""
    performance_monitor.reset_stats()

# ML-specific performance tracking
ML_OPERATIONS = {
    "MODEL_TRAINING": "model_training",
    "MODEL_PREDICTION": "model_prediction",
    "DATA_PREPROCESSING": "data_preprocessing",
    "FEATURE_EXTRACTION": "feature_extraction",
    "MODEL_EVALUATION": "model_evaluation",
    "HYPERPARAMETER_TUNING": "hyperparameter_tuning"
}

# Example usage:
# @track_performance(ML_OPERATIONS["MODEL_TRAINING"])
# def train_model(data):
#     # training logic
#     pass
