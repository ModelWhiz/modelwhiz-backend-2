"""
Global error handling middleware for ModelWhiz backend
Provides consistent error handling and structured error responses
"""

import logging
import traceback
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import uuid
import os

from app.utils.logger import log_error
from app.utils.error_monitor import track_error, ErrorTypes

class ModelWhizError(Exception):
    """Base exception class for ModelWhiz application errors"""
    
    def __init__(self, 
                 code: str, 
                 message: str, 
                 status_code: int = 500,
                 details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

# Specific error classes
class DatabaseError(ModelWhizError):
    """Database operation errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("DATABASE_ERROR", message, 500, details)

class FileOperationError(ModelWhizError):
    """File operation errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("FILE_OPERATION_ERROR", message, 500, details)

class MLProcessingError(ModelWhizError):
    """ML processing errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ML_PROCESSING_ERROR", message, 500, details)

class AuthenticationError(ModelWhizError):
    """Authentication errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("AUTHENTICATION_ERROR", message, 401, details)

class AuthorizationError(ModelWhizError):
    """Authorization errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("AUTHORIZATION_ERROR", message, 403, details)

class ValidationError(ModelWhizError):
    """Validation errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("VALIDATION_ERROR", message, 400, details)

class ResourceNotFoundError(ModelWhizError):
    """Resource not found errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("RESOURCE_NOT_FOUND", message, 404, details)

def create_error_response(
    code: str, 
    message: str, 
    status_code: int,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create standardized error response"""
    return {
        "error": {
            "code": code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "details": details or {}
        }
    }

async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for all uncaught exceptions"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    # Log the error with full stack trace
    error_type = exc.__class__.__name__
    error_message = str(exc)
    log_error(request_id, error_type, error_message, exc_info=True)
    
    # Track error for monitoring and alerting
    await track_error(error_type, error_message, request_id)
    
    # Return generic server error response
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
            status_code=500,
            request_id=request_id
        )
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler for HTTP exceptions"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    log_error(request_id, "HTTPException", f"{exc.status_code}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            code=f"HTTP_{exc.status_code}",
            message=exc.detail,
            status_code=exc.status_code,
            request_id=request_id
        )
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handler for request validation errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    # Extract validation errors
    validation_errors = []
    for error in exc.errors():
        validation_errors.append({
            "loc": error["loc"],
            "msg": error["msg"],
            "type": error["type"]
        })
    
    log_error(request_id, "ValidationError", f"Request validation failed: {validation_errors}")
    
    return JSONResponse(
        status_code=422,
        content=create_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            status_code=422,
            request_id=request_id,
            details={"validation_errors": validation_errors}
        )
    )

async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    """Handler for SQLAlchemy database errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = str(exc)
    log_error(request_id, "DatabaseError", error_message, exc_info=True)
    
    # Track database error for monitoring
    await track_error(ErrorTypes.DATABASE, error_message, request_id)
    
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            code="DATABASE_ERROR",
            message="Database operation failed",
            status_code=500,
            request_id=request_id,
            details={"original_error": error_message}
        )
    )

async def modelwhiz_error_handler(request: Request, exc: ModelWhizError):
    """Handler for ModelWhiz custom errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    log_error(request_id, exc.code, exc.message, exc_info=False)
    
    # Track custom errors for monitoring
    error_type = exc.code.lower()
    await track_error(error_type, exc.message, request_id)
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
            details=exc.details
        )
    )

async def file_not_found_error_handler(request: Request, exc: FileNotFoundError):
    """Handler for file not found errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"File not found: {str(exc)}"
    log_error(request_id, "FileNotFoundError", error_message, exc_info=True)
    
    # Track file operation error for monitoring
    await track_error(ErrorTypes.FILE, error_message, request_id)
    
    return JSONResponse(
        status_code=404,
        content=create_error_response(
            code="FILE_NOT_FOUND",
            message="The requested file was not found",
            status_code=404,
            request_id=request_id,
            details={"original_error": str(exc)}
        )
    )

async def permission_error_handler(request: Request, exc: PermissionError):
    """Handler for permission errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Permission denied: {str(exc)}"
    log_error(request_id, "PermissionError", error_message, exc_info=True)
    
    # Track permission error for monitoring
    await track_error(ErrorTypes.PERMISSION, error_message, request_id)
    
    return JSONResponse(
        status_code=403,
        content=create_error_response(
            code="PERMISSION_DENIED",
            message="Permission denied for the requested operation",
            status_code=403,
            request_id=request_id,
            details={"original_error": str(exc)}
        )
    )

async def timeout_error_handler(request: Request, exc: TimeoutError):
    """Handler for timeout errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Operation timed out: {str(exc)}"
    log_error(request_id, "TimeoutError", error_message, exc_info=True)
    
    # Track timeout error for monitoring
    await track_error(ErrorTypes.TIMEOUT, error_message, request_id)
    
    return JSONResponse(
        status_code=408,
        content=create_error_response(
            code="REQUEST_TIMEOUT",
            message="The operation timed out",
            status_code=408,
            request_id=request_id,
            details={"original_error": str(exc)}
        )
    )

async def connection_error_handler(request: Request, exc: ConnectionError):
    """Handler for connection errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Connection error: {str(exc)}"
    log_error(request_id, "ConnectionError", error_message, exc_info=True)
    
    # Track network error for monitoring
    await track_error(ErrorTypes.NETWORK, error_message, request_id)
    
    return JSONResponse(
        status_code=503,
        content=create_error_response(
            code="SERVICE_UNAVAILABLE",
            message="Service temporarily unavailable",
            status_code=503,
            request_id=request_id,
            details={"original_error": str(exc)}
        )
    )

async def memory_error_handler(request: Request, exc: MemoryError):
    """Handler for memory errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Memory error: {str(exc)}"
    log_error(request_id, "MemoryError", error_message, exc_info=True)
    
    # Track memory error for monitoring
    await track_error(ErrorTypes.MEMORY, error_message, request_id)
    
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            code="MEMORY_ERROR",
            message="Insufficient memory to complete the operation",
            status_code=500,
            request_id=request_id,
            details={"original_error": str(exc)}
        )
    )

async def rate_limit_error_handler(request: Request, exc: Exception):
    """Handler for rate limiting errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Rate limit exceeded: {str(exc)}"
    log_error(request_id, "RateLimitError", error_message, exc_info=False)
    
    # Track rate limit error for monitoring
    await track_error(ErrorTypes.RATE_LIMIT, error_message, request_id)
    
    return JSONResponse(
        status_code=429,
        content=create_error_response(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests, please try again later",
            status_code=429,
            request_id=request_id,
            details={
                "retry_after": 60,
                "original_error": str(exc)
            }
        ),
        headers={"Retry-After": "60"}
    )

# Rate limiting middleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handler for rate limiting exceeded errors"""
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    error_message = f"Rate limit exceeded for {get_remote_address(request)}"
    log_error(request_id, "RateLimitExceeded", error_message, exc_info=False)
    
    # Track rate limit error for monitoring
    await track_error(ErrorTypes.RATE_LIMIT, error_message, request_id)
    
    return JSONResponse(
        status_code=429,
        content=create_error_response(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests, please try again later",
            status_code=429,
            request_id=request_id,
            details={
                "retry_after": exc.retry_after,
                "limit": exc.detail
            }
        ),
        headers={"Retry-After": str(exc.retry_after)}
    )

def register_error_handlers(app: FastAPI):
    """Register all error handlers with the FastAPI application"""
    
    # Register handlers in order of specificity
    app.add_exception_handler(ModelWhizError, modelwhiz_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(FileNotFoundError, file_not_found_error_handler)
    app.add_exception_handler(PermissionError, permission_error_handler)
    app.add_exception_handler(TimeoutError, timeout_error_handler)
    app.add_exception_handler(ConnectionError, connection_error_handler)
    app.add_exception_handler(MemoryError, memory_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    
    # Initialize rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    logging.info("Error handlers registered successfully")

# Request ID middleware
async def request_id_middleware(request: Request, call_next):
    """Middleware to generate and attach request ID to all requests"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    # Add request ID to response headers for tracing
    response.headers["X-Request-ID"] = request_id
    
    return response

# Request logging middleware
async def request_logging_middleware(request: Request, call_next):
    """Middleware to log all incoming requests and responses"""
    from app.utils.logger import log_request, log_response
    import time
    
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    # Log the incoming request
    user_id = None  # Extract from auth if available
    log_request(request_id, request.method, str(request.url), user_id)
    
    # Process the request and measure time
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        
        # Log the response
        response_size = int(response.headers.get("content-length", 0))
        log_response(request_id, response.status_code, duration_ms, response_size)
        
        return response
        
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        # Error will be handled by exception handlers, but we log the failed attempt
        log_response(request_id, 500, duration_ms, 0)
        raise
