"""
Structured logging system for ModelWhiz backend
Provides professional logging with different configurations for development and production
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler
import uuid

class StructuredLogger:
    """Professional structured logging system"""
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self._configure_logging()
    
    def _configure_logging(self):
        """Configure logging based on environment"""
        # Clear existing handlers
        logging.getLogger().handlers.clear()
        
        # Create root logger
        self.logger = logging.getLogger("modelwhiz")
        self.logger.setLevel(getattr(logging, self.log_level, logging.INFO))
        
        if self.environment == "production":
            self._configure_production_logging()
        else:
            self._configure_development_logging()
    
    def _configure_production_logging(self):
        """Configure JSON logging for production"""
        # Console handler with JSON formatting
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(console_handler)
        
        # File handler with rotation - ensure logs directory exists
        try:
            os.makedirs("logs", exist_ok=True)
            file_handler = RotatingFileHandler(
                filename="logs/app.log",
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(file_handler)
        except Exception as e:
            self.logger.error(f"Failed to create file handler: {e}")
    
    def _configure_development_logging(self):
        """Configure human-readable logging for development"""
        # Console handler with detailed formatting
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]"
            )
        )
        self.logger.addHandler(console_handler)
    
    def log_request(self, request_id: str, method: str, path: str, user_id: Optional[str] = None):
        """Log API request details"""
        extra = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "user_id": user_id,
            "type": "request"
        }
        self.logger.info(f"Request: {method} {path}", extra=extra)
    
    def log_response(self, request_id: str, status_code: int, duration_ms: float, response_size: int):
        """Log API response details"""
        extra = {
            "request_id": request_id,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "response_size": response_size,
            "type": "response"
        }
        self.logger.info(f"Response: {status_code} ({duration_ms:.2f}ms)", extra=extra)
    
    def log_error(self, request_id: str, error_type: str, error_message: str, exc_info: bool = False):
        """Log error with structured context"""
        extra = {
            "request_id": request_id,
            "error_type": error_type,
            "type": "error"
        }
        self.logger.error(f"{error_type}: {error_message}", extra=extra, exc_info=exc_info)
    
    def log_performance(self, operation: str, duration_ms: float, details: Optional[Dict[str, Any]] = None):
        """Log performance metrics"""
        extra = {
            "operation": operation,
            "duration_ms": duration_ms,
            "details": details or {},
            "type": "performance"
        }
        self.logger.info(f"Performance: {operation} took {duration_ms:.2f}ms", extra=extra)
    
    def log_database_query(self, query: str, duration_ms: float, row_count: Optional[int] = None):
        """Log database query performance"""
        extra = {
            "operation": "database_query",
            "query": query[:100] + "..." if len(query) > 100 else query,
            "duration_ms": duration_ms,
            "row_count": row_count,
            "type": "database"
        }
        self.logger.debug(f"Database query: {duration_ms:.2f}ms", extra=extra)
    
    def log_cache_operation(self, operation: str, key: str, hit: Optional[bool] = None, duration_ms: Optional[float] = None):
        """Log cache operations"""
        extra = {
            "operation": operation,
            "key": key,
            "hit": hit,
            "duration_ms": duration_ms,
            "type": "cache"
        }
        if hit is not None:
            status = "HIT" if hit else "MISS"
            self.logger.debug(f"Cache {operation}: {key} -> {status} ({duration_ms:.2f}ms)", extra=extra)
        else:
            self.logger.debug(f"Cache {operation}: {key}", extra=extra)

    # Standard logging methods for compatibility
    def info(self, message: str, *args, **kwargs):
        """Log an info message"""
        self.logger.info(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """Log an error message"""
        self.logger.error(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """Log a warning message"""
        self.logger.warning(message, *args, **kwargs)

    def debug(self, message: str, *args, **kwargs):
        """Log a debug message"""
        self.logger.debug(message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """Log a critical message"""
        self.logger.critical(message, *args, **kwargs)


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging with proper extra field handling"""
    
    def format(self, record):
        # Create base log record with standard fields
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.threadName,
        }
        
        # Add all extra fields from record.__dict__ (excluding internal logging attributes)
        internal_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'levelname', 'levelno', 'lineno', 'message', 'module', 'msecs',
            'msg', 'name', 'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'thread', 'threadName', 'taskName'
        }
        
        for key, value in record.__dict__.items():
            if key not in internal_attrs and not key.startswith('_'):
                # Handle complex objects by converting to string if not JSON serializable
                try:
                    # Test if value is JSON serializable
                    json.dumps(value)
                    log_record[key] = value
                except (TypeError, ValueError):
                    # Convert to string representation
                    try:
                        log_record[key] = str(value)
                    except Exception:
                        log_record[key] = "Unserializable object"
        
        # Add exception info if present with better formatting
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            if exc_type and exc_value:
                log_record["exception"] = {
                    "type": exc_type.__name__,
                    "message": str(exc_value),
                    "traceback": self.formatException(record.exc_info)
                }
        
        # Handle any remaining serialization issues
        try:
            return json.dumps(log_record, ensure_ascii=False, default=self._json_default)
        except (TypeError, ValueError) as e:
            # Fallback: create a minimal log record
            fallback_record = {
                "timestamp": log_record["timestamp"],
                "level": log_record["level"],
                "message": f"Log serialization failed: {str(e)} - Original: {log_record.get('message', '')}",
                "serialization_error": True
            }
            return json.dumps(fallback_record, ensure_ascii=False)
    
    def _json_default(self, obj):
        """Default JSON serializer for complex objects"""
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        elif hasattr(obj, '__str__'):
            return str(obj)
        else:
            return repr(obj)


# Global logger instance
logger = StructuredLogger()

# Convenience functions for easy access
def get_logger():
    """Get the global structured logger"""
    return logger

def log_request(request_id: str, method: str, path: str, user_id: Optional[str] = None):
    """Convenience function to log requests"""
    logger.log_request(request_id, method, path, user_id)

def log_response(request_id: str, status_code: int, duration_ms: float, response_size: int):
    """Convenience function to log responses"""
    logger.log_response(request_id, status_code, duration_ms, response_size)

def log_error(request_id: str, error_type: str, error_message: str, exc_info: bool = False):
    """Convenience function to log errors"""
    logger.log_error(request_id, error_type, error_message, exc_info)

def log_performance(operation: str, duration_ms: float, details: Optional[Dict[str, Any]] = None):
    """Convenience function to log performance"""
    logger.log_performance(operation, duration_ms, details)

def log_database_query(query: str, duration_ms: float, row_count: Optional[int] = None):
    """Convenience function to log database queries"""
    logger.log_database_query(query, duration_ms, row_count)

def log_cache_operation(operation: str, key: str, hit: Optional[bool] = None, duration_ms: Optional[float] = None):
    """Convenience function to log cache operations"""
    logger.log_cache_operation(operation, key, hit, duration_ms)
