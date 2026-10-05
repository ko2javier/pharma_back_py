# app/services/venta_service.py
from datetime import date, datetime
from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venta_model import Ventas
from app.models.venta_cancelada_model import VentaCancelada, CancellationStatus
# TU VERSIÓN:
#     from app.repositories.venta_repository import VentaRepository, VentaCanceladaRepository
# Funcionaba, porque las dos clases estaban en ese fichero. Eso era el bug.
from app.repositories.venta_repository import VentaRepository
from app.repositories.venta_cancelada_repository import VentaCanceladaRepository
from app.schemas.venta_schema import VentaCreate

# El paso 8. Sin esto, "venta no encontrada" sale como 500: ValueError no tiene
# handler registrado en handlers.py y acaba en el genérico.
from app.exceptions.custom import ResourceNotFoundException


class VentaService:

    @staticmethod
    async def get_all(session: AsyncSession) -> Sequence[Ventas]:
        return await VentaRepository.find_all(session)

    @staticmethod
    async def get_all_by_username(session: AsyncSession, username: str) -> Sequence[Ventas]:
        return await VentaRepository.find_by_username(session, username)

    @staticmethod
    async def registrar_venta(session: AsyncSession, username: str, venta_dto: VentaCreate) -> Ventas:
        nueva_venta = Ventas(
            fecha=date.today(),
            hora=datetime.now().time(),
            username=username,
            dnicliente=venta_dto.dnicliente,
            nameproducto=venta_dto.nameproducto,
            cantidad=venta_dto.cantidad,
            importe=venta_dto.importe,
            codigo=venta_dto.codigo
        )

        await VentaRepository.save(session, nueva_venta)
        await session.commit()
        return nueva_venta

    @staticmethod
    async def registrar_ventas(session: AsyncSession, username: str, ventas_dto: list[VentaCreate]) -> list[Ventas]:
        nuevas_ventas = []
        for dto in ventas_dto:
            venta = Ventas(
                fecha=date.today(),
                hora=datetime.now().time(),
                username=username,
                dnicliente=dto.dnicliente,
                nameproducto=dto.nameproducto,
                cantidad=dto.cantidad,
                importe=dto.importe,
                codigo=dto.codigo
            )
            await VentaRepository.save(session, venta)
            nuevas_ventas.append(venta)

        # Un solo commit para todo el lote
        await session.commit()
        return nuevas_ventas

    @staticmethod
    async def cancelar_venta(session: AsyncSession, id_venta: int, username_responsable: str) -> None:
        """
        Equivalente a @Transactional. El AsyncSession de SQLAlchemy maneja la transacción:
        si algo falla antes del commit(), las dos escrituras se deshacen juntas.

        Matiz de tu redacción: el rollback no lo hace MySQL por su cuenta. Lo hace
        SQLAlchemy al salir del "async with" de get_db() sin haber llegado al
        commit() — cierra la sesión y manda ROLLBACK. MySQL sólo obedece.
        """
        # 1. Buscamos la venta original
        venta_original = await VentaRepository.find_by_id(session, id_venta)
        if not venta_original:
            # TU VERSIÓN:
            #     # Más adelante el controlador atrapará esto y lanzará ResourceNotFoundException
            #     raise ValueError(f"Venta no encontrada con id: {id_venta}")
            #
            # Ese "más adelante el controlador lo atrapa" es el try/except que el
            # paso 8 quitó de los tres endpoints de artículos. El service no debe
            # saber de HTTP, pero sí debe lanzar la excepción que handlers.py sabe
            # traducir; ValueError no está registrada y cae en el handler genérico,
            # así que el cliente recibe un 500 donde toca 404.
            #
            # El Java aquí lanza RuntimeException("Venta no encontrada")
            # (VentaService.java:91) y da 500 de verdad. Desviación deliberada, la
            # misma que en artículos y usuarios.
            raise ResourceNotFoundException(f"Venta no encontrada con id: {id_venta}")

        # 2. Copiamos los datos de la venta al registro de cancelación
        cancelacion = VentaCancelada(
            nombre_producto=venta_original.nameproducto,
            cantidad=venta_original.cantidad,
            importe=venta_original.importe,
            responsable=username_responsable,
            fecha=datetime.now(),
            status=CancellationStatus.CANCELLED
        )

        # 3. Guardamos en el historial de cancelaciones
        await VentaCanceladaRepository.save(session, cancelacion)

        # 4. Eliminamos la venta de la tabla principal
        await VentaRepository.delete(session, venta_original)

        # 5. Confirmamos ambas operaciones en la misma transacción
        await session.commit()