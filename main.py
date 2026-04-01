# main.py
# Lab System - FastAPI Application Entry Point
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from contextlib import asynccontextmanager
import os

from database import create_db_and_tables, get_session
from models import User
from routes.helpers import SECRET_KEY, pwd_context

# Import routers
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
# ✅ NEW: Import the history router
from routes.history import router as history_router
from routes.users import router as users_router
from routes.attachments import router as attachments_router
from routes.expenses import router as expenses_router
from routes.reports import router as reports_router

# ===========================
# APP LIFESPAN (Startup/Shutdown)
# ===========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_db_and_tables()
    
    # Create tmp dir if not exists
    if not os.path.exists("tmp"):
        os.makedirs("tmp")
    
    # Create uploads dir if not exists
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    if not os.path.exists("uploads/attachments"):
        os.makedirs("uploads/attachments")
    
    # Seed admin user if none exists
    from database import engine
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
            print("✅ Admin user created (admin / admin123)")
        else:
            print("✅ Admin user already exists")
    
    yield

app = FastAPI(title="NexLab LIS", lifespan=lifespan)

# ===========================
# AUTH MIDDLEWARE - Protect all routes (raw ASGI to avoid body-consumption issues)
# ===========================
from starlette.responses import RedirectResponse as StarletteRedirect

@app.middleware("http")
async def auth_middleware(request, call_next):
    path = request.url.path
    # Exclude /uploads/ from public_paths so attachments are secure
    public_paths = ["/login", "/static/", "/tmp/", "/favicon.ico"]
    is_public = any(path.startswith(p) for p in public_paths)
    
    if not is_public:
        try:
            from itsdangerous import URLSafeSerializer
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

# ===========================
# STATIC FILES
# ===========================
# FIXED: Pointed directory="static" so it finds your new tailwind.min.css file!
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount secure uploads folder
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
# ✅ NEW: Register the history router
app.include_router(history_router)
app.include_router(users_router)
app.include_router(attachments_router)
app.include_router(expenses_router)
app.include_router(reports_router)
