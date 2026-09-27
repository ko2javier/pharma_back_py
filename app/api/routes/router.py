# app/api/routes/router.py
from fastapi import APIRouter

from app.api.routes.auth_controller import router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router)
