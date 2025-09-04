# app/middleware/cache_middleware.py

import hashlib
import json
import logging
import os
from typing import Dict, Optional, Set
from datetime import datetime, timezone
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse, StreamingResponse
from ..cache import cache_client

logger = logging.getLogger(__name__)

class CacheMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cache_enabled: Optional[bool] = None):
        super().__init__(app)
        self.cache_enabled = cache_enabled if cache_enabled is not None else (
            os.getenv("ENVIRONMENT", "development").lower() in ("production", "staging")
        )
        self.max_cache_size = int(os.getenv("MAX_CACHE_SIZE", 1024 * 1024))
        self.cache_config = {
            "/": {"ttl": 3600, "public": True, "vary": []},
            "/docs": {"ttl": 3600, "public": True, "vary": []},
            "/openapi.json": {"ttl": 3600, "public": True, "vary": []},
            "/health": {"ttl": 60, "public": True, "vary": []},
            "/api/models/health": {"ttl": 60, "public": True, "vary": []},
            "/api/models/stats/cache": {"ttl": 30, "public": False, "vary": ["authorization"]},
            "/api/models": {"ttl": 300, "public": False, "vary": ["authorization"]},
            "/static": {"ttl": 86400, "public": True, "vary": []},
            "/uploads": {"ttl": 3600, "public": False, "vary": ["authorization"]},
        }
        self.no_cache_routes: Set[str] = {
            "/api/auth/login", "/api/auth/logout", "/api/auth/refresh",
            "/api/auth/register", "/api/evaluations",
        }
        self.no_cache_methods: Set[str] = {"POST", "PUT", "DELETE", "PATCH"}
        self.cacheable_content_types: Set[str] = {
            "application/json", "text/html", "text/plain", "text/css",
            "text/javascript", "application/javascript", "image/png",
            "image/jpeg", "image/svg+xml"
        }

    # ... (keep all helper methods: _should_cache_request, _should_cache_response, etc. as they are) ...
    def _should_cache_request(self, request: Request) -> bool:
        if not self.cache_enabled: return False
        if request.method not in {"GET", "HEAD"}: return False
        path = request.url.path
        if any(path.startswith(route) for route in self.no_cache_routes): return False
        if "no-cache" in request.headers.get("cache-control", "").lower(): return False
        return True

    def _should_cache_response(self, response: Response) -> bool:
        if response.status_code not in {200, 203, 300, 301, 302, 404, 410}: return False
        content_type = response.headers.get("content-type", "").split(";")[0]
        if content_type not in self.cacheable_content_types: return False
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.max_cache_size: return False
        if "no-store" in response.headers.get("cache-control", "").lower(): return False
        return True

    def _generate_cache_key(self, request: Request, config: Dict) -> str:
        key_components = [
            request.method, request.url.path, str(sorted(request.query_params.items())),
        ]
        vary_headers = config.get("vary", [])
        for header in vary_headers:
            header_value = request.headers.get(header.lower(), "")
            if header_value:
                if header.lower() == "authorization":
                    header_value = hashlib.md5(header_value.encode()).hexdigest()[:16]
                key_components.append(f"{header}:{header_value}")
        key_string = "|".join(key_components)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()
        return f"http_cache:{request.method}:{key_hash}"

    def _get_cache_config(self, path: str) -> Dict[str, any]:
        if path in self.cache_config: return self.cache_config[path]
        best_match, best_config = "", {"ttl": 300, "public": False, "vary": ["authorization"]}
        for route_pattern, config in self.cache_config.items():
            if path.startswith(route_pattern) and len(route_pattern) > len(best_match):
                best_match, best_config = route_pattern, config
        return best_config

    def _add_cache_headers(self, response: Response, config: Dict, cache_key: str, is_cached: bool = False):
        ttl = config.get("ttl", 300)
        is_public = config.get("public", False)
        vary_headers = config.get("vary", [])
        if hasattr(response, 'body') and response.body:
            etag_content = response.body if isinstance(response.body, bytes) else str(response.body).encode()
            etag = hashlib.md5(etag_content).hexdigest()[:16]
            response.headers["ETag"] = f'"{etag}"'
        response.headers["Last-Modified"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        cache_directives = ["public" if is_public else "private", f"max-age={ttl}"]
        if is_public: cache_directives.append(f"s-maxage={ttl}")
        response.headers["Cache-Control"] = ", ".join(cache_directives)
        if vary_headers: response.headers["Vary"] = ", ".join(vary_headers)
        response.headers["X-Cache"] = "HIT" if is_cached else "MISS"
        response.headers["X-Cache-Key"] = cache_key[:32]

    def _check_conditional_request(self, request: Request, cached_response: dict) -> Optional[Response]:
        if_none_match = request.headers.get("if-none-match")
        cached_etag = cached_response.get("headers", {}).get("etag")
        if if_none_match and cached_etag and if_none_match.strip('"') == cached_etag.strip('"'):
            response = Response(status_code=304); response.headers["ETag"] = cached_etag
            return response
        if_modified_since = request.headers.get("if-modified-since")
        cached_last_modified = cached_response.get("headers", {}).get("last-modified")
        if if_modified_since and cached_last_modified:
            try:
                request_time = datetime.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S GMT")
                cached_time = datetime.strptime(cached_last_modified, "%a, %d %b %Y %H:%M:%S GMT")
                if cached_time <= request_time:
                    response = Response(status_code=304); response.headers["Last-Modified"] = cached_last_modified
                    return response
            except ValueError:
                logger.debug("Date parsing error for If-Modified-Since")
        return None

    async def _extract_response_body(self, response: Response) -> Optional[bytes]:
        try:
            if isinstance(response, StreamingResponse):
                logger.debug("Skipping caching for StreamingResponse"); return None
            if hasattr(response, 'body'):
                return response.body if isinstance(response.body, bytes) else response.body.encode()
            return None
        except Exception as e:
            logger.error(f"Error extracting response body: {e}"); return None

    async def dispatch(self, request: Request, call_next):
        if not self._should_cache_request(request):
            response = await call_next(request)
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["X-Cache"] = "BYPASS"
            return response

        config = self._get_cache_config(request.url.path)
        cache_key = self._generate_cache_key(request, config)

        try:
            cached_data = await cache_client.get(cache_key)
            if cached_data:
                conditional_response = self._check_conditional_request(request, cached_data)
                if conditional_response:
                    return conditional_response
                logger.info(f"Cache HIT for {request.url.path}")
                
                # Return a JSONResponse to maintain FastAPI response validation compatibility
                headers = cached_data.get("headers", {})
                headers["X-Cache"] = "HIT"
                return JSONResponse(
                    content=cached_data["content"],
                    status_code=cached_data.get("status_code", 200),
                    headers=headers
                )

        except Exception as e:
            logger.error(f"Cache retrieval error: {e}")

        logger.info(f"Cache MISS for {request.url.path}")
        response = await call_next(request)

        if self._should_cache_response(response):
            try:
                response_body = await self._extract_response_body(response)
                if response_body and len(response_body) <= self.max_cache_size:
                    try:
                        content = json.loads(response_body.decode()) if response_body else None
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        content = response_body.decode() if response_body else None
                    
                    # Ensure we're storing dictionaries, not Pydantic model instances
                    if hasattr(content, 'model_dump'):
                        content = content.model_dump()
                    elif isinstance(content, list) and content and hasattr(content[0], 'model_dump'):
                        content = [item.model_dump() if hasattr(item, 'model_dump') else item for item in content]
                    if content is not None:
                        cache_data = {
                            "content": content,
                            "status_code": response.status_code,
                            "headers": {k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "transfer-encoding", "x-cache"}},
                            "cached_at": datetime.now(timezone.utc).isoformat()
                        }
                        await cache_client.set(cache_key, cache_data, config["ttl"])
            except Exception as e:
                logger.error(f"Cache storage error: {e}")

        self._add_cache_headers(response, config, cache_key, is_cached=False)
        return response


# ✅ Utility functions for cache control
def add_no_cache_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def add_public_cache_headers(response: Response, max_age: int = 3600) -> Response:
    response.headers["Cache-Control"] = f"public, max-age={max_age}, s-maxage={max_age}"
    response.headers["Last-Modified"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return response

def add_private_cache_headers(response: Response, max_age: int = 300) -> Response:
    response.headers["Cache-Control"] = f"private, max-age={max_age}"
    response.headers["Last-Modified"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return response


# # ✅ CacheConfig builder
# class CacheConfig:
#     @staticmethod
#     def no_cache() -> Dict[str, any]:
#         return {"ttl": 0, "public": False, "vary": []}

#     @staticmethod
#     def short_cache(ttl: int = 60, public: bool = False) -> Dict[str, any]:
#         return {"ttl": ttl, "public": public, "vary": [] if public else ["authorization"]}

#     @staticmethod
#     def medium_cache(ttl: int = 300, public: bool = False) -> Dict[str, any]:
#         return {"ttl": ttl, "public": public, "vary": [] if public else ["authorization"]}

#     @staticmethod
#     def long_cache(ttl: int = 3600, public: bool = True) -> Dict[str, any]:
#         return {"ttl": ttl, "public": public, "vary": []}

#     @staticmethod
#     def user_specific_cache(ttl: int = 300) -> Dict[str, any]:
#         return {"ttl": ttl, "public": False, "vary": ["authorization", "user-agent"]}


# # ✅ Middleware factory
# def create_cache_middleware(environment: str = "production"):
#     cache_enabled = environment.lower() in ("production", "staging")
#     return CacheMiddleware(cache_enabled=cache_enabled)
