# app/api/routes/router.py
from fastapi import APIRouter

# TU VERSIÓN: from app.api.routes import user_controller
# Importaba el MÓDULO, no el APIRouter que hay dentro. include_router() espera
# un APIRouter y un módulo no lo es: revienta al arrancar (ver abajo).
from app.api.routes.auth_controller import router as auth_router
from app.api.routes.articulo_controller import router as articulo_router
from app.api.routes.user_controller import router as user_router

api_router = APIRouter()
api_router.include_router(auth_router)
# Sin esta línea los siete endpoints de /articulos no existen, aunque el
# fichero esté escrito: es el equivalente a que Spring no escanee el
# @RestController. Un 404 de FastAPI y ninguna pista de por qué.
api_router.include_router(articulo_router)
# TU VERSIÓN: api_router.include_router(user_controller)  <- el módulo
api_router.include_router(user_router)
