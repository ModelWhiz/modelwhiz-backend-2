from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import gzip
import json
from typing import Callable

class CompressionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, minimum_size: int = 1024, compression_level: int = 6):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Skip compression for certain content types
        content_type = response.headers.get("content-type", "")
        if not self._should_compress(content_type):
            return response
            
        # Get response body
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
            
        # Only compress if body is large enough
        if len(response_body) < self.minimum_size:
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.media_type
            )
            
        # Check if client accepts gzip
        accept_encoding = request.headers.get("accept-encoding", "")
        if "gzip" not in accept_encoding.lower():
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.media_type
            )
            
        # Compress the response
        compressed_body = gzip.compress(response_body, compresslevel=self.compression_level)
        
        # Update headers
        new_headers = dict(response.headers)
        new_headers["content-encoding"] = "gzip"
        new_headers["content-length"] = str(len(compressed_body))
        
        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=new_headers,
            media_type=response.media_type
        )
        
    def _should_compress(self, content_type: str) -> bool:
        """Determine if content should be compressed based on content type"""
        compressible_types = [
            "application/json",
            "text/html",
            "text/css",
            "text/javascript",
            "application/javascript",
            "text/plain"
        ]
        return any(ct in content_type.lower() for ct in compressible_types)
