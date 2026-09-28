# app/services/articulo_service.py
import random
from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.articulo_model import Articulos
from app.repositories.articulo_repository import ArticuloRepository
from app.schemas.articulo_schema import ArticuloCreate, ArticuloUpdate

# Las excepciones del paso 8. Sustituyen a los ValueError que había aquí: el
# servicio ya no tiene que pensar en códigos HTTP (no sabe nada de HTTP, igual
# que el @Service del Java), y el controlador se queda sin un solo try/except
# porque handlers.py las traduce sola. Es lo que hacía @RestControllerAdvice.
from app.exceptions.custom import (
    InsufficientStockException,
    ResourceNotFoundException,
)


class ArticuloService:

    @staticmethod
    async def get_all(session: AsyncSession) -> Sequence[Articulos]:
        return await ArticuloRepository.find_all(session)

    @staticmethod
    async def search_by_keyword(session: AsyncSession, keyword: str) -> Sequence[Articulos]:
        return await ArticuloRepository.find_by_nombre_containing(session, keyword)

    @staticmethod
    async def update_stock_batch(session: AsyncSession, updates: list[ArticuloUpdate]) -> list[Articulos]:
        """
        Equivalente al @Transactional.
        En FastAPI con SQLAlchemy, la sesión ya es una transacción abierta.
        Si algo falla (raise ValueError), la petición HTTP devolverá un error y
        el commit() nunca se ejecutará, haciendo un rollback automático de todo el lote.
        """
        articulos_actualizados = []

        for update in updates:
            articulo = await ArticuloRepository.find_by_codigo(session, update.codigo)

            # TU VERSIÓN (obsoleta — un solo raise para dos motivos distintos):
            #     if not articulo or articulo.cantidad < update.cantidad_vendida:
            #         raise ValueError(f"Artículo no encontrado o cantidad insuficiente: {update.codigo}")
            #
            # Es la traducción literal del Java (ArticuloService.java:38-40), pero
            # allí daba igual porque los dos casos acababan en el mismo 500. Aquí
            # sí importa: "no existe" es un 404 y "no hay stock" un 409, y no se
            # puede distinguir después si vienen en la misma excepción.
            if not articulo:
                raise ResourceNotFoundException(f"Artículo no encontrado: {update.codigo}")
            if articulo.cantidad < update.cantidad_vendida:
                raise InsufficientStockException(
                    f"Stock insuficiente de {articulo.nombre}: "
                    f"quedan {articulo.cantidad} y se piden {update.cantidad_vendida}"
                )

            articulo.cantidad -= update.cantidad_vendida
            articulos_actualizados.append(articulo)

        await session.commit()
        return articulos_actualizados

    @staticmethod
    async def update_item(session: AsyncSession, cambios: ArticuloUpdate) -> Articulos:
        articulo = await ArticuloRepository.find_by_codigo(session, cambios.codigo)
        if not articulo:
            # OBSOLETO: raise ValueError(f"Artículo no encontrado: {cambios.codigo}")
            raise ResourceNotFoundException(f"Artículo no encontrado: {cambios.codigo}")

        articulo.cantidad = cambios.cantidad
        articulo.precio = cambios.precio

        await session.commit()
        return articulo

    @staticmethod
    async def _generar_codigo_unico(session: AsyncSession) -> str:
        """Método privado (indicado por el guion bajo) para generar el EAN13 aleatorio"""
        while True:
            # Genera un número aleatorio de hasta 13 dígitos
            numero_aleatorio = random.randint(0, 9999999999999)
            # Formatea con ceros a la izquierda (ej: 0001234567890)
            codigo = f"{numero_aleatorio:013d}"

            # Verificamos si ya existe
            existe = await ArticuloRepository.find_by_codigo(session, codigo)
            if not existe:
                return codigo

    @staticmethod
    async def insertar_articulo(session: AsyncSession, insert_dto: ArticuloCreate) -> Articulos:
        codigo = await ArticuloService._generar_codigo_unico(session)

        nuevo_articulo = Articulos(
            nombre=insert_dto.nombre,
            categoria=insert_dto.categoria,
            precio=insert_dto.precio,
            cantidad=insert_dto.cantidad,
            codigo=codigo,
            aemps_code=insert_dto.aemps_code,
            laboratorio=insert_dto.laboratorio
        )

        await ArticuloRepository.save(session, nuevo_articulo)
        await session.commit()
        return nuevo_articulo

    @staticmethod
    async def get_by_id(session: AsyncSession, articulo_id: int) -> Articulos | None:
        return await ArticuloRepository.find_by_id(session, articulo_id)

    @staticmethod
    async def delete_articulo_by_id(session: AsyncSession, articulo_id: int) -> None:
        existe = await ArticuloRepository.exists_by_id(session, articulo_id)
        if not existe:
            # OBSOLETO: raise ValueError(f"Artículo no encontrado con id: {articulo_id}")
            raise ResourceNotFoundException(f"Artículo no encontrado con id: {articulo_id}")

        await ArticuloRepository.delete_by_id(session, articulo_id)
        await session.commit()

    @staticmethod
    async def link_aemps(session: AsyncSession, articulo_id: int, aemps_code: str, laboratorio: str) -> Articulos:
        articulo = await ArticuloRepository.find_by_id(session, articulo_id)
        if not articulo:
            # OBSOLETO: raise ValueError(f"Artículo no encontrado con id: {articulo_id}")
            raise ResourceNotFoundException(f"Artículo no encontrado con id: {articulo_id}")

        articulo.aemps_code = aemps_code
        articulo.laboratorio = laboratorio

        await session.commit()
        return articulo