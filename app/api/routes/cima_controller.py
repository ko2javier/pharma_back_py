# app/api/routes/cima_controller.py
# ← CimaController.java
import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_http_client
from app.core.database import get_db
from app.models.user_model import Users
from app.services.activity_log_service import ActivityLogService
from app.services.articulo_service import ArticuloService
from app.services.cima_service import CimaService
from app.services.ia_service import IaService

# Sin dependencies=[...]: el gate de /api/cima/** vive en router.py, como el
# resto de prefijos. En el Java es .anyRequest().authenticated(), sin rol.
router = APIRouter(prefix="/api/cima", tags=["CIMA / IA"])


# GET /api/cima/medicamento?nregistro= — ficha completa de AEMPS (proxy).
#
# Se reenvía el texto de AEMPS sin parsear, como el ResponseEntity<String> del
# Java. Si el nregistro no existe, AEMPS da 204 vacío y aquí sale 200 vacío —
# lo mismo que el Java (getForObject devuelve null y lo mete en un ok()).
# Llamado por articulo-detalle-modal.component.ts:80 y almacen.component.ts:326.
@router.get("/medicamento")
async def obtener_medicamento(
        nregistro: str,
        client: httpx.AsyncClient = Depends(get_http_client),
):
    """Equivalente a ResponseEntity<String> obtenerMedicamento(String)"""
    texto = await CimaService.obtener_medicamento(client, nregistro)
    # Response y no return texto: devolviendo un str, FastAPI lo serializaría
    # OTRA VEZ como JSON y el Angular recibiría "\"{\\\"nregistro\\\"...\"" —
    # un string con el JSON dentro, no el objeto.
    return Response(content=texto, media_type="application/json")


# GET /api/cima/buscar?nombre=&pagina=1 — búsqueda en AEMPS (proxy).
#
# NO se declara tamanioPagina aunque el Angular lo mande (cima.service.ts:18):
# el Java tampoco lo declara y Spring lo descarta. FastAPI hace lo mismo con
# un query param no declarado. No "arreglarlo": cambiaría el catálogo.
# Llamado por catalogo-externo.component.ts:35 y articulo-detalle-modal:99.
@router.get("/buscar")
async def buscar_medicamentos(
        nombre: str,
        pagina: int = 1,
        client: httpx.AsyncClient = Depends(get_http_client),
):
    """Equivalente a ResponseEntity<String> buscarMedicamentos(String, int)"""
    texto = await CimaService.buscar(client, nombre, pagina)
    return Response(content=texto, media_type="application/json")


# GET /api/cima/validar?nombre= — el flujo más largo de los 25 endpoints.
# Llamado por almacen.component.ts:291 (insertArticulo).
#
#   1. Ya en inventario            → 409 {"mensaje": ...}
#   2. AEMPS caído                 → 502 (lo lanza CimaService)
#   3. AEMPS sin resultados        → 404 {"mensaje": ...}
#   4. IA caída / api-key mala     → 500 (sube sin capturar, ver ia_service.py)
#   5. Todo bien                   → log IA_MATCH + 200 con la respuesta de la IA
#
# El 409 y el 404 llevan la clave "mensaje" y no "error": en el Java son
# ResponseEntity escritos a mano (CimaController.java:74-75 y :100-101), no
# pasan por el GlobalExceptionHandler. Por eso aquí son JSONResponse a mano y
# no excepciones propias, cuyos handlers emiten {"error": ...}. Al Angular le
# da igual (sólo mira err.status), pero el contrato es éste.
#
# Por esto se borró AempsNotFoundException en el paso 12: el paso 8 la creó
# para este 404, y al llegar aquí resultó que el Java no la puede usar.
@router.get("/validar")
async def validar_medicamento(
        request: Request,
        nombre: str,
        session: AsyncSession = Depends(get_db),
        client: httpx.AsyncClient = Depends(get_http_client),
        current_user: Users = Depends(get_current_user),
):
    """Equivalente a ResponseEntity<?> validarMedicamento(String)"""
    # 1. Si ya existe en inventario, no se pregunta ni a AEMPS ni a la IA.
    if await ArticuloService.search_by_keyword(session, nombre):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"mensaje": "El producto ya existe en el inventario"},
        )

    # 2 y 3. AEMPS → lista limpia {id, nombre}. Si AEMPS falla, 502 desde aquí.
    lista_medicamentos = await CimaService.buscar_para_ia(client, nombre)

    # 4. Sin resultados → el medicamento no existe en AEMPS.
    if not lista_medicamentos:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"mensaje": "No se encontraron resultados en AEMPS"},
        )

    # 5. La IA elige la mejor coincidencia. Sin try: si falla → 500.
    resultado_ia = await IaService.llamar_microservicio_ia(client, nombre, lista_medicamentos)

    # 6. Sólo se registra si la IA respondió bien, como en el Java. El detail
    # es el término buscado, no el resultado.
    ip_address = request.client.host if request.client else "unknown"
    await ActivityLogService.log(
        session, current_user.username, "IA_MATCH", nombre, ip_address
    )

    # 7. La respuesta de la IA tal cual, sin envolver.
    return resultado_ia
