# app/repositories/articulo_repository.py
from collections.abc import Sequence
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.articulo_model import Articulos

# Borrado logico (2026-10-18): un articulo retirado tiene enabled=False y para
# la aplicacion NO existe. Todas las lecturas llevan este filtro menos DOS, y
# las dos a proposito: codigo_en_uso y find_by_codigo_incluso_retirados (ver
# alli). Las dos llevan el motivo en el nombre para que nadie las use para
# listar.
#
# Una sola expresion para las cuatro lecturas: si cada metodo escribiera su
# propio "enabled == True", el dia que se anada un quinto se olvida y ese
# listado empieza a mostrar productos retirados sin que nada falle.
# El "== True" es intencionado: SQLAlchemy lo compila a "enabled = true".
_ACTIVO = Articulos.enabled == True  # noqa: E712


class ArticuloRepository:

    @staticmethod
    async def find_all(session: AsyncSession) -> Sequence[Articulos]:
        stmt = select(Articulos).where(_ACTIVO)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_nombre_containing(session: AsyncSession, keyword: str) -> Sequence[Articulos]:
        """Equivalente a findByNombreContaining.

        OJO: no solo la usa GET /search. cima_controller.py:84 la usa para el
        409 "El producto ya existe en el inventario" antes de dar de alta. Que
        filtre es lo que permite volver a dar de alta un producto retirado; sin
        el filtro, retirarlo lo bloquearia para siempre contra un fantasma.
        """
        # TU VERSIÓN: .ilike(f"%{keyword}%"), con el comentario "usamos ilike para
        # que no distinga mayúsculas/minúsculas".
        #
        # El resultado es el mismo, pero el motivo no se sostiene y tiene coste:
        # en MySQL el LIKE normal YA ignora mayúsculas, porque lo decide la
        # collation de la columna (utf8mb4_..._ci, de "case insensitive"), no el
        # operador. ilike no existe en MySQL: SQLAlchemy lo compila a
        # LOWER(nombre) LIKE LOWER(%s), y una función sobre la columna impide
        # usar el índice de 'nombre' (lo que en Java sería un full table scan).
        # El Java, con findByNombreContaining, generaba el LIKE de abajo.
        #
        # El % es el comodín de SQL equivalente a "cualquier cosa antes o después"
        stmt = select(Articulos).where(Articulos.nombre.like(f"%{keyword}%"), _ACTIVO)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_codigo(session: AsyncSession, codigo: str) -> Articulos | None:
        # Para LEER (updateStock, updateItem). Para saber si un codigo esta
        # libre NO sirve: eso es codigo_en_uso.
        stmt = select(Articulos).where(Articulos.codigo == codigo, _ACTIVO)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def codigo_en_uso(session: AsyncSession, codigo: str) -> bool:
        """True si CUALQUIER fila tiene ese codigo, retirada o no.

        Es la unica consulta SIN el filtro de enabled, y no por descuido: la
        UNIQUE KEY codigo_unico de MySQL tampoco filtra. Un articulo retirado
        sigue ocupando su codigo, y si el generador lo diera por libre, el
        INSERT moriria con IntegrityError -> 500. Es la misma regla que
        crear_usuario: find_by_username no filtra enabled por lo mismo.
        """
        stmt = select(exists().where(Articulos.codigo == codigo))
        result = await session.execute(stmt)
        # bool(): MySQL devuelve el EXISTS como 1/0 (ver la nota que tenia
        # exists_by_id, quitado abajo).
        return bool(result.scalar())

    @staticmethod
    async def find_by_codigo_incluso_retirados(session: AsyncSession, codigo: str) -> Articulos | None:
        """El articulo de ese codigo, este retirado o no. SIN el filtro.

        Solo para cancelar_venta, que devuelve al stock lo vendido. Una venta
        se puede cancelar aunque su articulo se haya retirado despues, y la
        caja devuelta tiene que constar igual: decidido el 2026-10-18 ("sea
        que este retirado o no se hace lo mismo"). El retirado sigue sin verse
        en ningun listado; solo cambia su cantidad.

        Se busca por codigo y no por id porque la venta no guarda el id del
        articulo: guarda ventas.codigo, que es la FK (fk_articulos_ventas) y
        apunta a articulos.codigo, UNIQUE. Una sola fila, sin depender del
        nombre.
        """
        stmt = select(Articulos).where(Articulos.codigo == codigo)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_id(session: AsyncSession, articulo_id: int) -> Articulos | None:
        # LO VIEJO: return await session.get(Articulos, articulo_id)
        #
        # session.get busca por clave primaria y no admite WHERE: devolveria
        # los retirados. Peor: si el objeto ya esta en la sesion, ni consulta
        # la base. Por eso pasa a ser un select como los demas.
        stmt = select(Articulos).where(Articulos.id == articulo_id, _ACTIVO)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def save(session: AsyncSession, articulo: Articulos) -> Articulos:
        session.add(articulo)
        # Quitado el 2026-10-05: await session.refresh(articulo)
        # Unificado con los repositorios de ventas. flush() ya deja el id y el
        # version rellenos en el objeto (version lo lleva SQLAlchemy por el
        # version_id_col, no MySQL), así que el refresh releía lo que ya estaba:
        #     Articulos.id tras SOLO flush -> 1 / Articulos.version -> 1
        await session.flush()
        return articulo

    # QUITADOS el 2026-10-18, con el borrado logico:
    #
    #   * delete_by_id -- hacia session.delete(), un DELETE fisico que MySQL
    #     propagaba a 'ventas' por fk_articulos_ventas (ON DELETE CASCADE). Se
    #     quito en vez de dejarlo sin usar porque era justo el peligroso: quien
    #     lo viera aqui lo usaria como "el borrado normal" y se llevaria el
    #     historial de ventas sin aviso.
    #   * exists_by_id -- solo lo usaba delete_articulo_by_id para preguntar
    #     "existe?" antes de borrar. Ahora el servicio hace find_by_id (que ya
    #     filtra) y modifica ese mismo objeto: una consulta responde a las dos
    #     cosas.
