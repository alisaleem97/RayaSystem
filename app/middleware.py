# app/middleware.py
# Auth middleware — protects all routes, extracted from main.py for clean SoC.
# SEC-08: Uses print_token for headless PDF bypass (not User-Agent sniffing).
# SEC-12: Adds security headers to all responses.

import hashlib
from starlette.responses import RedirectResponse as StarletteRedirect

from app.config import SECRET_KEY
from sqlmodel import Session
from app.database import engine
from app.services.auth_service import get_current_user

# Pre-compute the print token once at import time (not per-request)
PRINT_TOKEN = hashlib.sha256(SECRET_KEY.encode()).hexdigest()[:16]

# Paths that don't require authentication
PUBLIC_PATHS = ["/login", "/static/", "/tmp/", "/favicon.ico"]

# Paths that can bypass auth when a valid print_token is provided.
# This covers both the NexPrint client AND local Headless Chrome PDF generation.
PRINT_TOKEN_PATHS = [
    "/print-barcode/", "/print-receipt/",
    "/api/print-barcode-pdf/", "/api/print-barcode-image/",
    "/print-results/render/", "/api/lab-info",
]


async def auth_middleware(request, call_next):
    """HTTP middleware that enforces authentication on all non-public routes."""
    path = request.url.path
    is_public = any(path.startswith(p) for p in PUBLIC_PATHS)

    # SEC-08 FIX: Replaced insecure HeadlessChrome User-Agent sniffing with
    # print_token validation. Any path in PRINT_TOKEN_PATHS can bypass auth
    # if a valid print_token query param is provided (used by NexPrint client
    # and Headless Chrome PDF generation).
    if not is_public:
        token = request.query_params.get("print_token", "")
        if token == PRINT_TOKEN:
            for prefix in PRINT_TOKEN_PATHS:
                if path.startswith(prefix):
                    is_public = True
                    break

    if not is_public:
        with Session(engine) as session:
            user = get_current_user(request, session)
            if not user:
                response = StarletteRedirect(url="/login", status_code=303)
                response.delete_cookie("nexlab_session")
                return response
            request.state.user_id = user.id

    response = await call_next(request)

    # SEC-12: Add security headers to all responses
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response
