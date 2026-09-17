# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Más adelante, cuando tengamos los controladores, importaremos el enrutador principal:
# from app.api.routes.router import api_router

# Equivale a FpApplication.java + SwaggerConfig.java
app = FastAPI(
    title="EasyFarma API",
    description="Migración del backend farmacia-ko2 a FastAPI (Totalmente Async)",
    version="1.0.0",
    # FastAPI genera automáticamente la documentación en /docs y /openapi.json
)

# Equivale a la configuración CORS de tu SecurityConfig.java
#
# INCORRECTO (lo que había antes): allow_origins=["*"] junto a allow_credentials=True.
# La especificación CORS prohíbe esa combinación, y Starlette la resuelve reflejando
# el origen que pregunte — o sea, CUALQUIER web podía llamar a la API con credenciales.
# El SecurityConfig.java nunca permitió "*": tiene esta lista blanca de 6 orígenes.
#
# TODO (paso 2): mover la lista a core/config.py para tener orígenes distintos
# en desarrollo y en producción sin tocar código.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "https://farmacia-ko2.up.railway.app",
        "https://pharma.ko2-oreilly.com",
        "https://pharma-b.ko2-oreilly.com",
        "https://farmacia-ko2-frontend.vercel.app",
        "https://farmacia-ko2-back-production.up.railway.app",
    ],
    allow_credentials=True,
    # Los mismos que setAllowedMethods del Java (con "*" se colaba también HEAD)
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # setAllowedHeaders(List.of("*")) en el Java
)

# Aquí registraremos todos los "Controladores" más adelante
# app.include_router(api_router)

# Un endpoint de prueba para comprobar que el servidor arranca bien
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "EasyFarma API migrada a FastAPI funcionando"}
