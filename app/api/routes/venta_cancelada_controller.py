# app/api/routes/venta_cancelada_controller.py
# ← VentaCanceladaController.java
#
# El original lleva un @CrossOrigin(origins = "*") de clase que no se replica: el
# CORS en FastAPI es global (CORSMiddleware en main.py con cors_origins de
# Settings), no una anotación por controlador. Y "*" en un endpoint autenticado
# es más abierto de lo que hace falta.
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.venta_cancelada_schema import VentaCanceladaCreate, VentaCanceladaOut
from app.services.venta_cancelada_service import VentaCanceladaService

# Sin dependencies=[...]: el gate vive en router.py.
router = APIRouter(prefix="/cancelaciones", tags=["Cancelaciones"])


# ─────────────────────────────────────────────────────────────────────────────
# LAS RUTAS SON "" (cadena vacía), NO "/".
#
# El Java es @GetMapping sin path sobre @RequestMapping("/cancelaciones"), o sea
# exactamente /cancelaciones. En FastAPI, con prefix="/cancelaciones":
#
#   @router.get("")   -> /cancelaciones    <- esto es lo que queremos
#   @router.get("/")  -> /cancelaciones/   <- otra ruta distinta
#
# Y el frontend llama a `${environment.apiUrl}/cancelaciones` sin barra
# (ventas-canceladas.service.ts:12). Con "/" la petición acabaría en un redirect
# 307 en vez de responder, que no es lo que hace el backend Java.
# ─────────────────────────────────────────────────────────────────────────────


# GET /cancelaciones — historial completo.
#
# Aquí NO hay 204, al contrario que en /ventas. El Java devuelve la List pelada
# (VentaCanceladaController.java:20), sin ResponseEntity, así que una lista vacía
# sale como 200 []. Importa porque la gráfica de estadísticas del Angular recorre
# el array (estadisticas.component.ts:119) y con un 204 recibiría undefined.
@router.get("", response_model=list[VentaCanceladaOut])
async def listar_cancelaciones(session: AsyncSession = Depends(get_db)):
    """Equivalente a List<VentaCancelada> listarCancelaciones()"""
    return await VentaCanceladaService.obtener_todas(session)


# POST /cancelaciones — añade una cancelación al historial a mano.
#
# NO LO LLAMA NADIE. VentasCanceladasService.registrarCancelacion existe en el
# Angular (ventas-canceladas.service.ts:31) y ningún componente la invoca: el
# camino real de una cancelación es DELETE /ventas/cancelar/{id}, que escribe esta
# misma tabla desde VentaService. Se replica por contrato.
#
# Y aquí va la única desviación del fichero: el Java recibe la ENTIDAD
# VentaCancelada entera desde el @RequestBody, con su id incluido, así que un
# cliente podía mandar {"id": 5, ...} y hacer que Hibernate actualizara la fila 5
# en vez de insertar una nueva. VentaCanceladaCreate no tiene campo id, de modo
# que no hay forma de que llegue uno.
@router.post("", response_model=VentaCanceladaOut)
async def guardar_cancelacion(
        datos: VentaCanceladaCreate,
        session: AsyncSession = Depends(get_db),
):
    """Equivalente a VentaCancelada guardarCancelacion(VentaCancelada)"""
    return await VentaCanceladaService.registrar_cancelacion(session, datos)
