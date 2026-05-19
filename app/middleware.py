# app/middleware.py
# Auth middleware — protects all routes, extracted from main.py for clean SoC.

import hashlib
from starlette.responses import RedirectResponse as StarletteRedirect
from itsdangerous import URLSafeSerializer

from app.config import SECRET_KEY

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
    if path.startswith("/print-barcode/") or path.startswith("/print-receipt/") or path.startswith("/api/print-barcode-pdf/"):
        token = request.query_params.get("print_token", "")
        if token == PRINT_TOKEN:
            is_public = True

    if not is_public:
        try:
            s = URLSafeSerializer(SECRET_KEY)
            cookie = request.cookies.get("nexlab_session")
            if not cookie:
                return StarletteRedirect(url="/login", status_code=303)
            data = s.loads(cookie)
            user_id = data.get("user_id")
            if not user_id:
                return StarletteRedirect(url="/login", status_code=303)
            request.state.user_id = user_id
        except Exception:
            return StarletteRedirect(url="/login", status_code=303)

    response = await call_next(request)
    return response
