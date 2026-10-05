# app/api/routes/venta_controller.py
# ← VentaController.java
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user_model import Users
from app.schemas.venta_schema import VentaCreate, VentaOut
from app.services.activity_log_service import ActivityLogService
from app.services.venta_service import VentaService

# Sin dependencies=[...]: el gate de /ventas/** vive en el include_router() de
# router.py, igual que los otros cuatro prefijos. Aquí sólo se declaran rutas.
router = APIRouter(prefix="/ventas", tags=["Ventas"])


# ─────────────────────────────────────────────────────────────────────────────
# OJO CON EL ORDEN DE ESTOS DOS PRIMEROS ENDPOINTS.
#
# /ventas/all y /ventas/{username} son el mismo método (GET) sobre el mismo
# prefijo. FastAPI resuelve por ORDEN DE DECLARACIÓN, así que si /{username} se
# escribe antes, una petición a /ventas/all entra por él con username="all",
# devuelve 204 (ningún usuario se llama "all") y /ventas/all nunca se ejecuta.
#
# En Spring esto no pasaba: elegía la ruta literal por ser más específica. Es la
# misma colisión que hay en /users, y ahí ya se resolvió igual.
# ─────────────────────────────────────────────────────────────────────────────


# GET /ventas/all — todas las ventas del sistema.
#
# Aquí SÍ va el 204 que no lleva /activity-log/all. Comprobado en el original:
#   VentaController.java:34-36   if (ventas.isEmpty()) -> noContent()  -> 204
#   ActivityLogController.java:19  devuelve la List pelada             -> 200 []
@router.get("/all", response_model=list[VentaOut])
async def obtener_todas_las_ventas(session: AsyncSession = Depends(get_db)):
    """Equivalente a ResponseEntity<List<Ventas>> obtenerTodasLasVentas()"""
    ventas = await VentaService.get_all(session)
    if not ventas:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ventas


# GET /ventas/{username} — historial de un usuario concreto.
@router.get("/{username}", response_model=list[VentaOut])
async def obtener_ventas_por_usuario(username: str, session: AsyncSession = Depends(get_db)):
    """Equivalente a ResponseEntity<List<Ventas>> obtenerVentasPorUsuario(String)"""
    # No comprueba que el usuario exista: si no tiene ventas, da 204 igual que si
    # no existe. Es lo que hace el Java y el frontend sólo lo llama con el
    # username del token.
    ventas = await VentaService.get_all_by_username(session, username)
    if not ventas:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ventas


# POST /ventas/registrar — una sola venta.
#
# Dos cosas que no son evidentes:
#
#   1. Devuelve 200, no 201. /users/insert sí da 201 (UserController.java usa
#      ResponseEntity.status(CREATED)); aquí el Java hace ResponseEntity.ok
#      (VentaController.java:54). No es un descuido, es el original.
#   2. ESTE ENDPOINT NO LO LLAMA NADIE. El carrito del Angular usa sólo
#      /registrar/list (ventas-user.service.ts:47). Se replica por contrato, pero
#      no hay frontend que lo valide.
@router.post("/registrar", response_model=VentaOut)
async def registrar_venta(
        venta_dto: VentaCreate,
        session: AsyncSession = Depends(get_db),
        # Reemplaza al obtenerUsuarioAutenticado() que el Java tenía DENTRO del
        # @Service leyendo del SecurityContextHolder. Aquí el service no sabe nada
        # de autenticación: recibe el username ya resuelto.
        current_user: Users = Depends(get_current_user),
):
    """Equivalente a ResponseEntity<Ventas> registrarVenta(VentaDTO)"""
    # OJO — REGISTRAR UNA VENTA NO DESCUENTA STOCK.
    #
    # VentaService.java inyecta articulosRepository y no lo usa en ningún sitio.
    # Quien descuenta es el FRONTEND, en una segunda petición: el carrito llama a
    # PUT /articulos/updateStock después de registrar (carritocomponent.ts:157,
    # actualizarStockBatch).
    #
    # Son dos peticiones sin transacción común: si la segunda falla con 409, la
    # venta ya está registrada y el stock sin tocar. Es deuda real de producción y
    # se replica tal cual, como el DELETE de /articulos. Si algún día se arregla,
    # el sitio es el service, descontando dentro de la misma transacción.
    return await VentaService.registrar_venta(session, current_user.username, venta_dto)


# POST /ventas/registrar/list — un ticket entero de una vez.
# Este sí es el que usa el carrito del Angular.
@router.post("/registrar/list", response_model=list[VentaOut])
async def registrar_ventas(
        ventas_dto: list[VentaCreate],
        session: AsyncSession = Depends(get_db),
        current_user: Users = Depends(get_current_user),
):
    """Equivalente a ResponseEntity<List<Ventas>> registrarVentas(List<VentaDTO>)"""
    # Un solo commit para todo el lote, en el service: si una venta del ticket
    # falla, no se guarda ninguna. El Java no lo garantizaba (sin @Transactional,
    # cada save() iba por su cuenta).
    return await VentaService.registrar_ventas(session, current_user.username, ventas_dto)


# DELETE /ventas/cancelar/{id}?responsable=... — cancela y mueve al historial.
#
# Devuelve 200 con cuerpo vacío, no 204: el Java hace ResponseEntity.ok().build()
# (VentaController.java:70). El DELETE de /articulos sí es 204. Distintos porque
# los controladores originales son distintos.
@router.delete("/cancelar/{id}", status_code=status.HTTP_200_OK)
async def cancelar_venta(
        request: Request,
        id: int,
        # 'responsable' sin valor por defecto y sin estar en la ruta = query param
        # OBLIGATORIO. Es el equivalente de @RequestParam String responsable: si
        # falta, FastAPI devuelve 422 (el Java daba 400).
        responsable: str,
        session: AsyncSession = Depends(get_db),
        current_user: Users = Depends(get_current_user),
):
    """Equivalente a ResponseEntity<Void> cancelarVenta(Integer, String)"""
    # Si la venta no existe, el service lanza ResourceNotFoundException -> 404 y
    # no se llega al log. El Java lanzaba RuntimeException y daba 500.
    await VentaService.cancelar_venta(session, id, responsable)

    # El log guarda current_user.username, NO el 'responsable' del query param.
    # Son dos cosas distintas a propósito: 'responsable' es quien FIRMA la
    # cancelación en el historial (y el cliente puede poner el nombre que quiera,
    # el Java tampoco lo valida), mientras el log es el rastro de quién la pidió
    # de verdad, sacado del token. Si alguien firma con otro nombre, aquí se ve.
    ip_address = request.client.host if request.client else "unknown"
    await ActivityLogService.log(
        session, current_user.username, "CANCEL_SALE", f"id={id}", ip_address
    )

    # Response vacía de verdad, para que el cuerpo sea exactamente lo que manda el
    # Java. Devolviendo None, FastAPI serializaría "null" — al Angular le da igual
    # (sólo mira next/error, ventas-usuario.component.ts:193), pero esto es exacto.
    return Response(status_code=status.HTTP_200_OK)
