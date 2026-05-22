# app/middleware.py
# Auth middleware — protects all routes, extracted from main.py for clean SoC.

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


async def auth_middleware(request, call_next):
    """HTTP middleware that enforces authentication on all non-public routes."""
    path = request.url.path
    is_public = any(path.startswith(p) for p in PUBLIC_PATHS)

    # Allow local Headless Chrome to load assets for PDF generation
    user_agent = request.headers.get("user-agent", "")
    if "HeadlessChrome" in user_agent and request.client.host == "127.0.0.1":
        is_public = True

    # NexPrint token bypass for barcode/receipt printing
    if path.startswith("/print-barcode/") or path.startswith("/print-receipt/") or path.startswith("/api/print-barcode-pdf/") or path.startswith("/api/print-barcode-image/"):
        token = request.query_params.get("print_token", "")
        if token == PRINT_TOKEN:
            is_public = True

    if not is_public:
        with Session(engine) as session:
            user = get_current_user(request, session)
            if not user:
                response = StarletteRedirect(url="/login", status_code=303)
                response.delete_cookie("nexlab_session")
                return response
            request.state.user_id = user.id

    response = await call_next(request)
    return response
