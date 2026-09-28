# app/repositories/articulo_repository.py
from collections.abc import Sequence
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.articulo_model import Articulos

class ArticuloRepository:

    @staticmethod
    async def find_all(session: AsyncSession) -> Sequence[Articulos]:
        stmt = select(Articulos)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_nombre_containing(session: AsyncSession, keyword: str) -> Sequence[Articulos]:
        """Equivalente a findByNombreContaining."""
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
        stmt = select(Articulos).where(Articulos.nombre.like(f"%{keyword}%"))
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_codigo(session: AsyncSession, codigo: str) -> Articulos | None:
        stmt = select(Articulos).where(Articulos.codigo == codigo)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_id(session: AsyncSession, articulo_id: int) -> Articulos | None:
        return await session.get(Articulos, articulo_id)

    @staticmethod
    async def exists_by_id(session: AsyncSession, articulo_id: int) -> bool:
        """Devuelve True si existe, False si no, sin cargar toda la entidad en memoria"""
        stmt = select(exists().where(Articulos.id == articulo_id))
        result = await session.execute(stmt)
        # TU VERSIÓN: return result.scalar()
        # Funciona, pero MySQL devuelve el EXISTS como 1/0 (no tiene BOOLEAN de
        # verdad: es un alias de TINYINT), así que la firma dice -> bool y la
        # función devuelve un int. Funciona por "truthiness" y nadie se queja,
        # pero es la misma clase de mentira que un método Java declarado boolean
        # devolviendo un Integer.
        return bool(result.scalar())

    @staticmethod
    async def save(session: AsyncSession, articulo: Articulos) -> Articulos:
        session.add(articulo)
        await session.flush()
        await session.refresh(articulo)
        return articulo

    @staticmethod
    async def delete_by_id(session: AsyncSession, articulo_id: int) -> None:
        articulo = await session.get(Articulos, articulo_id)
        if articulo:
            await session.delete(articulo)
            await session.flush()