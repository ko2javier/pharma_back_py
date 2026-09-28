# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

from app.api.routes.router import api_router
from app.exceptions.handlers import register_exception_handlers

settings = get_settings()

# Equivale a FpApplication.java + SwaggerConfig.java
app = FastAPI(
    title="EasyFarma API",
    description="Migración del backend farmacia-ko2 a FastAPI (Totalmente Async)",
    version="1.0.0",
    # FastAPI genera automáticamente la documentación en /docs y /openapi.json
)

# Equivale a la configuración CORS de tu SecurityConfig.java
#
#
# HECHO (era el "TODO (paso 2)"): la lista estaba escrita a mano aquí dentro,
#     allow_origins=[
#         "http://localhost:4200",
#         "https://farmacia-ko2.up.railway.app",
#         ... los seis
#     ],
# y a la vez en Settings.cors_origins. Dos copias de lo mismo: al añadir un
# dominio nuevo se cambia una y se olvida la otra. Ahora la única fuente es
# Settings, y se puede tener una lista distinta por entorno sin tocar código.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # Los mismos que setAllowedMethods del Java (con "*" se colaba también HEAD)
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # setAllowedHeaders(List.of("*")) en el Java
)

app.include_router(api_router)

# Equivale a que GlobalExceptionHandler.java sea un @RestControllerAdvice: sin
# esto, cada excepción propia (ver app/exceptions/) reventaría como un 500 sin
# formato en vez del código HTTP que le corresponde.
register_exception_handlers(app)


# Un endpoint de prueba para comprobar que el servidor arranca bien
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "EasyFarma API migrada a FastAPI funcionando"}


# ── Arranque en local ─────────────────────────────────────────────────────
#
# Equivale al main() de FpApplication.java: permite arrancar con
# "python -m app.main" (o con el botón de PyCharm apuntando a este fichero) en
# vez de recordar la línea de uvicorn con sus parámetros.
#
# El loop= es lo importante, y NO es un parche de Windows:
#
# uvicorn 0.36+ elige el bucle de eventos con una factoría, y en Windows la de
# por defecto es ProactorEventLoop. Ese bucle no sabe hacer el paso a TLS a
# mitad de conexión que exige el protocolo MySQL (aiomysql duplica el socket y
# lo reengancha al bucle ya cifrado), y la conexión a Aiven muere con un
#     OperationalError (2003) / OSError [WinError 87] El parámetro no es correcto
# que no dice absolutamente nada del problema real.
#
# "asyncio:SelectorEventLoop" es una ruta de importación que uvicorn acepta en
# --loop. Sirve en las dos plataformas sin comprobar sys.platform, porque
# SelectorEventLoop existe también en Linux: allí ES el bucle por defecto
# (epoll), así que en el VPS esta línea no cambia nada.
#
# Truco para depurar: si vuelves a ver un WinError 87 en un handshake, repite la
# prueba con el selector. El Proactor oculta la causa real (en su día tapó un
# CERTIFICATE_VERIFY_FAILED, que era el problema de verdad).
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",  # en el contenedor será 0.0.0.0, desde el CMD del Dockerfile
        port=settings.port,
        reload=settings.environment == "dev",
        loop="asyncio:SelectorEventLoop",
    )
