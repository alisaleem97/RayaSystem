# main.py
# Lab System - FastAPI Application Entry Point
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from contextlib import asynccontextmanager
import os

from database import create_db_and_tables, get_session
from models import User

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
    
    # Seed admin user if none exists
    from database import engine
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == "admin")).first()
        if not existing:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
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
# STATIC FILES
# ===========================
# FIXED: Pointed directory="static" so it finds your new tailwind.min.css file!
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