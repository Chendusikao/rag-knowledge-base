"""Request validation and defensive response headers for the local enterprise API."""
from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings


class RequestSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/v1"):
            origin = request.headers.get("origin")
            frontend_origins = set(settings.cors_allow_origins)
            backend_origins = {
                f"http://localhost:{settings.port}",
                f"http://127.0.0.1:{settings.port}",
            }
            if origin and origin not in frontend_origins | backend_origins:
                return JSONResponse(status_code=403, content={"detail": "请求来源不受信任"})
            if origin in frontend_origins and request.headers.get("x-requested-with") != "EnterpriseKnowledgeBase":
                return JSONResponse(status_code=403, content={"detail": "缺少请求校验标记"})

        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith(("/api/v1/auth", "/api/v1/audit")):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
