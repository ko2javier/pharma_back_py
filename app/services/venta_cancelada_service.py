# app/services/venta_cancelada_service.py
from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venta_cancelada_model import VentaCancelada
from app.repositories.venta_cancelada_repository import VentaCanceladaRepository
from app.schemas.venta_cancelada_schema import VentaCanceladaCreate


class VentaCanceladaService:

    # OJO: VentaService.cancelar_venta NO pasa por aquí. Llama directo a
    # VentaCanceladaRepository.save, porque necesita el insert y el delete de la
    # venta en la MISMA transacción y aquí dentro hay un commit() propio.
    # Son dos caminos para escribir ventas_canceladas, y es así en el Java
    # (VentaService.java:103 usa canceladaRepository, no el service). Se mantiene
    # para no divergir, pero si algún día hay que validar algo al cancelar, hay
    # que tocar los dos sitios.
    @staticmethod
    async def registrar_cancelacion(session: AsyncSession, datos: VentaCanceladaCreate) -> VentaCancelada:
        """Guarda una cancelación en el historial."""
        # TU VERSIÓN:
        #     async def registrar_cancelacion(session, venta_cancelada: VentaCancelada):
        #         await VentaCanceladaRepository.save(session, venta_cancelada)
        #
        # Es la firma literal del Java, y el cuerpo estaba bien. Lo que cambia es
        # QUIÉN construye la entidad. Con la entidad en la firma, el controlador
        # tiene que importar el modelo y montarla, y entonces el único sitio donde
        # se garantiza que el cliente no manda un 'id' es ese controlador. Con el
        # schema en la firma no hay nada que recordar: VentaCanceladaCreate no
        # tiene campo id, así que no existe forma de que llegue uno.
        #
        # Y es la convención de las otras tres: ningún service del proyecto recibe
        # una entidad de SQLAlchemy, y ningún controlador construye una.
        nueva_cancelacion = VentaCancelada(
            nombre_producto=datos.nombre_producto,
            cantidad=datos.cantidad,
            importe=datos.importe,
            responsable=datos.responsable,
            # Si viene None, la rellena el default=datetime.now de la columna.
            # Comprobado ejecutando: SQLAlchemy aplica el default igual aunque le
            # pases None a mano, no sólo cuando omites el campo.
            fecha=datos.fecha,
            status=datos.status,
        )

        await VentaCanceladaRepository.save(session, nueva_cancelacion)
        await session.commit()
        return nueva_cancelacion

    @staticmethod
    async def obtener_todas(session: AsyncSession) -> Sequence[VentaCancelada]:
        """Devuelve todas las cancelaciones registradas (para el historial en el frontend)."""
        return await VentaCanceladaRepository.find_all(session)