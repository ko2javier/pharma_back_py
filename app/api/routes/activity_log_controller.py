# app/api/routes/activity_log_controller.py
# ← ActivityLogController.java
#
# El original es el controlador más corto del backend: un @GetMapping("/all")
# que devuelve activityLogService.getAll() y nada más. Aquí igual — el repo
# (find_all_ordered) y el service (get_all) ya se hicieron en el paso 6, así
# que de este paso sólo faltaba esta capa.
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.activity_log_schema import ActivityLogOut
from app.services.activity_log_service import ActivityLogService

# El router NO declara el control de acceso, igual que articulos y users: la
# regla (SUPERADMIN) vive en el include_router() de router.py, que es la tabla
# equivalente al SecurityConfig.java. Aquí sólo se declara la ruta.
router = APIRouter(prefix="/activity-log", tags=["Activity Log"])


# GET /activity-log/all — historial completo, del más reciente al más antiguo.
#
# OJO, aquí NO va el 204 que sí lleva GET /articulos/All. No es un descuido:
# es que los dos controladores del Java no hacen lo mismo, y se ha comprobado
# en el original antes de escribir esto.
#
#   ArticuloController.java:44-50   ResponseEntity<List<Articulos>>
#                                   if (articulos.isEmpty()) -> noContent()  -> 204
#   ActivityLogController.java:19   List<ActivityLog> obtenerTodos()
#                                   devuelve la lista pelada              -> 200 []
#
# Spring serializa una List vacía como [] con 200. Replicarlo importa porque
# un 204 no trae cuerpo, y el Angular que pintase la tabla del historial se
# encontraría un undefined donde espera un array.
#
# Tampoco hay POST ni DELETE: el historial no se escribe nunca desde HTTP, lo
# escribe el propio backend llamando a ActivityLogService.log() (por eso
# activity_log_schema.py sólo tiene schema de salida). Es un registro de
# auditoría: sin endpoint de borrado, el rastro no se puede limpiar.
@router.get("/all", response_model=list[ActivityLogOut])
async def obtener_todos(session: AsyncSession = Depends(get_db)):
    """Equivalente a List<ActivityLog> obtenerTodos()"""
    # El orden (fecha DESC, hora DESC) lo pone el repositorio, igual que el
    # findAllByOrderByFechaDescHoraDesc() de JpaRepository: no se reordena aquí.
    return await ActivityLogService.get_all(session)
