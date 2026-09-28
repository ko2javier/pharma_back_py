# app/exceptions/handlers.py
#
# Equivalente a GlobalExceptionHandler.java, pero sin @RestControllerAdvice
# (no existe en FastAPI): cada handler se registra a mano en main.py con
# app.add_exception_handler(), agrupado aquí en register_exception_handlers().
#
# Del Java sólo se replican los dos handlers que allí se disparaban de
# verdad — ExternalServiceException y OptimisticLockException (ver abajo) —
# más el genérico. Los otros dos del Java (ResourceNotFoundException e
# IllegalArgumentException) estaban declarados pero nunca se lanzaban desde
# ningún controlador ni servicio.

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.exceptions.custom import (
    AempsNotFoundException,
    DuplicateResourceException,
    ExternalServiceException,
    InsufficientStockException,
    ResourceNotFoundException,
)

logger = logging.getLogger(__name__)


async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundException
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": str(exc)})


async def aemps_not_found_handler(
    request: Request, exc: AempsNotFoundException
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": str(exc)})


async def duplicate_resource_handler(
    request: Request, exc: DuplicateResourceException
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": str(exc)})


async def insufficient_stock_handler(
    request: Request, exc: InsufficientStockException
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": str(exc)})


async def stale_data_handler(request: Request, exc: StaleDataError) -> JSONResponse:
    # Equivalente async al OptimisticLockException de Hibernate: SQLAlchemy la
    # lanza en el flush/commit cuando la fila ya no tiene el version_id_col
    # que se leyó al principio de la transacción (otra petición la modificó
    # entre medias). carritocomponent.ts:189, en el front, mira exactamente
    # este 409 al actualizar stock en lote.
    return JSONResponse(
        status_code=409,
        content={"error": "El artículo fue modificado por otro usuario. Inténtalo de nuevo."},
    )


async def external_service_handler(
    request: Request, exc: ExternalServiceException
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": str(exc)})


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Como el @ExceptionHandler(Exception.class) del Java: red de seguridad
    # para lo que se escape (bugs, no casos de negocio esperados). No se
    # filtra el traceback al cliente, sólo al log.
    logger.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ResourceNotFoundException, resource_not_found_handler)
    app.add_exception_handler(AempsNotFoundException, aemps_not_found_handler)
    app.add_exception_handler(DuplicateResourceException, duplicate_resource_handler)
    app.add_exception_handler(InsufficientStockException, insufficient_stock_handler)
    app.add_exception_handler(StaleDataError, stale_data_handler)
    app.add_exception_handler(ExternalServiceException, external_service_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
