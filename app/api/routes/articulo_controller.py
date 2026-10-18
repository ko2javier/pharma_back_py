# app/api/routes/articulo_controller.py
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# INCORRECTO (lo que había antes):
#     # Importaremos la dependencia del JWT que crearemos a continuación
#     from app.api.dependencies.auth_deps import get_current_username
#
#     ModuleNotFoundError: No module named 'app.api.dependencies'
#
# Ese paquete no existe y la dependencia no está por crear: se hizo en el paso 7
# y vive en app/api/deps.py (sin subcarpeta y sin sufijo, es una de las
# excepciones a la regla de nombres, como router.py o core/*). Además no se
# llama get_current_username ni devuelve un str: es get_current_user y devuelve
# la entidad Users entera, igual que el UserDetails de Spring — de ahí que abajo
# se use current_user.username.
from app.api.deps import get_current_user
from app.models.user_model import Users
from app.schemas.articulo_schema import ArticuloCreate, ArticuloUpdate, ArticuloOut, ArticuloAempsLink
from app.services.articulo_service import ArticuloService
from app.services.activity_log_service import ActivityLogService

# TU VERSIÓN: APIRouter(prefix="/articulos", tags=["Artículos"])
#
# Faltaba el dependencies=[...], y eso dejaba CINCO de los siete endpoints
# abiertos sin token: sólo /insert y DELETE /{id} pedían autenticación. En el
# Java no hace falta declararlo endpoint por endpoint porque SecurityConfig
# termina en .anyRequest().authenticated(), así que todo /articulos/** exige
# JWT; tal como estaba, cualquiera sin token podía vaciar el stock con
# PUT /updateStock.
#
# VERSIÓN INTERMEDIA (correcta, pero movida el 2026-10-04):
#     router = APIRouter(
#         prefix="/articulos",
#         tags=["Artículos"],
#         dependencies=[Depends(get_current_user)],
#     )
#
# El gate sigue existiendo, pero ahora vive en el include_router() de
# router.py, para tener TODAS las reglas de acceso en un sitio como en
# SecurityConfig.java. Funciona igual: las dependencias declaradas en el
# include_router se suman a las de cada ruta de este fichero.
#
# Los endpoints que necesitan saber QUIÉN llama lo siguen pidiendo como
# parámetro — de ahí que el import de get_current_user siga aquí —, y no hay
# doble consulta a la BD porque FastAPI cachea cada dependencia dentro de la
# misma petición.
router = APIRouter(prefix="/articulos", tags=["Artículos"])


@router.get("/search/{keyword}", response_model=list[ArticuloOut])
async def buscar_articulos(keyword: str, session: AsyncSession = Depends(get_db)):
    articulos = await ArticuloService.search_by_keyword(session, keyword)
    if not articulos:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return articulos


@router.get("/All", response_model=list[ArticuloOut])
async def obtener_todos(session: AsyncSession = Depends(get_db)):
    articulos = await ArticuloService.get_all(session)
    if not articulos:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return articulos


# Los try/except ValueError de estos tres endpoints son lo que queda obsoleto
# con el paso 8. Antes hacían falta porque el servicio lanzaba ValueError, que
# no dice nada de HTTP, así que había que traducirlo aquí a mano; ahora el
# servicio lanza ResourceNotFoundException / InsufficientStockException y
# handlers.py las convierte en 404 y 409 para toda la app. Es la diferencia
# entre un try/catch en cada controlador y tener el @RestControllerAdvice.
#
# De paso arregla una incoherencia: el MISMO "artículo no encontrado" salía como
# 400 aquí (except ValueError) y como 404 en /updateItem.
@router.put("/updateStock", response_model=list[ArticuloOut])
async def actualizar_stock_lote(updates: list[ArticuloUpdate], session: AsyncSession = Depends(get_db)):
    # OBSOLETO:
    #     try:
    #         articulos_actualizados = await ArticuloService.update_stock_batch(session, updates)
    #         ...
    #     except ValueError as e:
    #         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    articulos_actualizados = await ArticuloService.update_stock_batch(session, updates)
    if not articulos_actualizados:
        # Esto NO es el "no encontrado" del servicio: es el caso de que llegue
        # una lista vacía. El Java respondía igual (ResponseEntity.notFound()
        # cuando la lista vuelve vacía, ArticuloController.java:56-58).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se actualizaron artículos")
    return articulos_actualizados


@router.put("/updateItem", response_model=ArticuloOut)
async def actualizar_articulo(cambios: ArticuloUpdate, session: AsyncSession = Depends(get_db)):
    # OBSOLETO:
    #     try:
    #         ...
    #     except ValueError as e:
    #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return await ArticuloService.update_item(session, cambios)


@router.post("/insert", response_model=ArticuloOut)
async def crear_articulo(
        request: Request,
        insert_dto: ArticuloCreate,
        session: AsyncSession = Depends(get_db),
        # TU VERSIÓN: username: str = Depends(get_current_username)
        # get_current_user devuelve la entidad, no el nombre (ver el import).
        current_user: Users = Depends(get_current_user)  # Reemplaza SecurityContextHolder
):
    nuevo_articulo = await ArticuloService.insertar_articulo(session, insert_dto)

    # Activity Log
    ip_address = request.client.host if request.client else "unknown"
    await ActivityLogService.log(
        session, current_user.username, "INSERT_PRODUCT", nuevo_articulo.nombre, ip_address
    )

    return nuevo_articulo


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_articulo(
        request: Request,
        id: int,
        session: AsyncSession = Depends(get_db),
        current_user: Users = Depends(get_current_user)
):
    # BORRADO LÓGICO desde el 2026-10-18: el servicio pone enabled=False.
    #
    # Antes era un DELETE físico, y se llevaba el historial de ventas:
    #     fk_articulos_ventas   ventas.codigo -> articulos.codigo   DELETE RULE: CASCADE
    # (comprobado en Aiven el 2026-09-28, information_schema). La FK sigue
    # ahí; lo que cambia es que ya no se manda ningún DELETE que la dispare.
    # Se pudo hacer al apagarse el Java, que compartía la BD: la columna
    # 'enabled' se añadió a mano en Aiven (ddl-auto=none).
    #
    # DESVIACIÓN DELIBERADA respecto al Java, que sí borra la fila. Al
    # Angular le da igual: sigue recibiendo un 204 y el artículo desaparece
    # de /All.
    #
    # get_by_id ya filtra los retirados: si el artículo ya estaba retirado,
    # aquí sale None y el servicio lanza el 404 antes de llegar al log.
    articulo = await ArticuloService.get_by_id(session, id)
    nombre = articulo.nombre if articulo else f"id={id}"

    # OBSOLETO:
    #     try:
    #         await ArticuloService.delete_articulo_by_id(session, id)
    #     except ValueError as e:
    #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    await ArticuloService.delete_articulo_by_id(session, id)

    ip_address = request.client.host if request.client else "unknown"
    await ActivityLogService.log(
        session, current_user.username, "DELETE_PRODUCT", nombre, ip_address
    )

    # En FastAPI, al devolver None en un endpoint con status_code=204, se genera la respuesta vacía correcta
    return None


@router.patch("/{id}/aemps", response_model=ArticuloOut)
async def vincular_aemps(
        id: int,
        body: ArticuloAempsLink,  # Usamos el DTO que creamos en lugar del Map genérico
        session: AsyncSession = Depends(get_db)
):

    return await ArticuloService.link_aemps(session, id, body.aemps_code, body.laboratorio)