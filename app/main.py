# app/main.py
# NexLab LIS — FastAPI Application Entry Point
# Slim entry point: registers routers, lifecycle, middleware, error handling.

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from sqlmodel import Session, select
from contextlib import asynccontextmanager
import os
import logging

from app.config import SECRET_KEY, pwd_context
from app.database import create_db_and_tables, engine
from app.models import User
from app.middleware import auth_middleware

# Import routers (from original routes/ directory — they still work via bridges)
from routes.auth import router as auth_router
from routes.departments import router as departments_router
from routes.tests import router as tests_router
from routes.geography import router as geography_router
from routes.patients import router as patients_router
from routes.printing import router as printing_router
from routes.api import router as api_router
from routes.results import router as results_router
from routes.double_auth import router as double_auth_router
from routes.call_centre import router as call_centre_router
from routes.history import router as history_router
from routes.patient_status import router as patient_status_router
from routes.users import router as users_router
from routes.attachments import router as attachments_router
from routes.expenses import router as expenses_router
from routes.reports import router as reports_router
from routes.messages import router as messages_router
from routes.websockets import router as websockets_router
from routes.supplies import router as supplies_router
from routes.inventory import router as inventory_router
from routes.cal_control import router as cal_control_router


# ===========================
# APP LIFESPAN (Startup/Shutdown)
# ===========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    create_db_and_tables()

    # Ensure required directories exist
    for d in ["tmp", "uploads", "uploads/attachments", "uploads/chat_media"]:
        os.makedirs(d, exist_ok=True)

    # Seed admin user if none exists
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == "admin")).first()
        if not existing:
            admin = User(
                username="admin",
                full_name="Administrator",
                role="admin",
                hashed_password=pwd_context.hash("admin123"),
                is_active=True
            )
            session.add(admin)
            session.commit()
            print("WARNING: Default admin user created with password 'admin123'. Change this immediately in production!")
        else:
            print("[OK] Admin user already exists")

    yield


app = FastAPI(title="NexLab LIS", lifespan=lifespan)


# ===========================
# GLOBAL ERROR HANDLERS — Crash-proof
# ===========================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions so the server NEVER crashes."""
    logging.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)}
        )
    return HTMLResponse(
        content=f"<h2>System Error</h2><p>An internal error occurred. The system is still running.</p><p><a href='/dashboard'>Return to Dashboard</a></p>",
        status_code=500
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return HTMLResponse(
        content=f"<h2>Page Not Found</h2><p>The page you requested does not exist.</p><p><a href='/dashboard'>Return to Dashboard</a></p>",
        status_code=404
    )


# ===========================
# AUTH MIDDLEWARE
# ===========================
@app.middleware("http")
async def _auth_middleware(request, call_next):
    return await auth_middleware(request, call_next)


# ===========================
# STATIC FILES
# ===========================
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/tmp", StaticFiles(directory="tmp"), name="tmp")


# ===========================
# INCLUDE ROUTERS
# ===========================
app.include_router(auth_router)
app.include_router(departments_router)
app.include_router(tests_router)
app.include_router(geography_router)
app.include_router(patients_router)
app.include_router(printing_router)
app.include_router(api_router)
app.include_router(results_router)
app.include_router(double_auth_router)
app.include_router(call_centre_router)
app.include_router(history_router)
app.include_router(patient_status_router)
app.include_router(users_router)
app.include_router(attachments_router)
app.include_router(expenses_router)
app.include_router(reports_router)
app.include_router(messages_router)
app.include_router(websockets_router)
app.include_router(supplies_router)
app.include_router(inventory_router)
app.include_router(cal_control_router)
