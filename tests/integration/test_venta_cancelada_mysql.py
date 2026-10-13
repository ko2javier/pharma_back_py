# tests/integration/test_venta_cancelada_mysql.py
#
# Primer test del nivel 3. Fija una divergencia entre el modelo y el esquema
# REAL de Aiven que los 195 tests no pueden ver:
#
#     ventas.nameproducto               varchar(100)  DEFAULT NULL   <- admite NULL
#     ventas_canceladas.nombre_producto varchar(255)  NOT NULL       <- no lo admite
#
# cancelar_venta copia uno en otro. Una venta sin nombre de producto no se
# puede cancelar: el INSERT revienta con ERROR 1048 y el cliente recibe un 500.
# El modelo VentaCancelada declara la columna Optional, la fabrica del
# conftest de arriba la construye con None, y con la sesion falsa todo pasa.
#
# Son tests de CARACTERIZACION: fijan lo que hace HOY la aplicacion, no lo
# que deberia hacer. Que hacer con una venta sin nombre (rellenar "", dar un
# 409, prohibir el NULL en ventas) esta sin decidir. El dia que se arregle,
# los dos primeros se ponen rojos -- y eso es lo que se busca: que el cambio
# no pase sin que nadie lo vea.
from datetime import date, time

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.articulo_model import Articulos
from app.models.user_model import Users
from app.models.venta_cancelada_model import CancellationStatus, VentaCancelada
from app.models.venta_model import Ventas
from app.services.venta_service import VentaService

CODIGO = "8470001234567"


async def _preparar_venta(sesion, nameproducto: str | None) -> int:
    """Una venta confirmada en MySQL, con su usuario y su articulo.

    El usuario y el articulo no son relleno: fk_usuario_ventas y
    fk_articulos_ventas obligan a que existan. Sin ellos el INSERT de la
    venta falla -- es la primera prueba de que este esquema SI tiene las
    claves ajenas que un create_all() no habria puesto.
    """
    sesion.add(Users(username="tester", password="x", enabled=True, permiso="ADMIN"))
    sesion.add(Articulos(nombre="Ibuprofeno 600mg", categoria="Antiinflamatorio",
                         precio=12.95, cantidad=50, codigo=CODIGO))
    await sesion.flush()
    venta = Ventas(fecha=date(2026, 10, 13), hora=time(13, 45), username="tester",
                   dnicliente="12345678A", nameproducto=nameproducto,
                   cantidad=2, importe=25.90, codigo=CODIGO)
    sesion.add(venta)
    await sesion.commit()
    return venta.id


async def _contar(sesion, modelo) -> int:
    return (await sesion.execute(select(func.count()).select_from(modelo))).scalar_one()


# -------------------------------------------------------------------------
# La causa: el NOT NULL de ventas_canceladas
# -------------------------------------------------------------------------
async def test_cancelar_venta_sin_nombre_revienta_con_error_1048(sesion):
    id_venta = await _preparar_venta(sesion, nameproducto=None)

    with pytest.raises(IntegrityError) as error:
        await VentaService.cancelar_venta(sesion, id_venta, "admin")

    # 1048 = "Column cannot be null". Se comprueba el codigo y la columna,
    # no solo el tipo: un IntegrityError tambien lo daria una clave ajena.
    assert error.value.orig.args[0] == 1048
    assert "nombre_producto" in str(error.value.orig)


# -------------------------------------------------------------------------
# La consecuencia: 500 en el endpoint, y la venta sigue ahi
# -------------------------------------------------------------------------
async def test_endpoint_cancelar_venta_sin_nombre_hoy_da_500_y_no_borra(client, autenticar, sesion):
    id_venta = await _preparar_venta(sesion, nameproducto=None)
    autenticar()

    r = await client.delete(f"/ventas/cancelar/{id_venta}", params={"responsable": "admin"})

    assert r.status_code == 500
    assert r.json() == {"error": "Error interno del servidor"}
    # Lo importante: el fallo no deja la base a medias. La venta no se borro
    # y no hay cancelacion huerfana. La peticion uso su propia sesion (como
    # en produccion), asi que esto es lo que quedo en MySQL, no en memoria.
    assert await _contar(sesion, Ventas) == 1
    assert await _contar(sesion, VentaCancelada) == 0


# -------------------------------------------------------------------------
# Control: con nombre, la misma cancelacion funciona
# -------------------------------------------------------------------------
async def test_endpoint_cancelar_venta_con_nombre_da_200(client, autenticar, sesion):
    """Sin este, el 500 de arriba podria venir de cualquier otra cosa
    (el contenedor, la fixture, la autenticacion) y el test pasaria igual."""
    id_venta = await _preparar_venta(sesion, nameproducto="Ibuprofeno 600mg")
    autenticar()

    r = await client.delete(f"/ventas/cancelar/{id_venta}", params={"responsable": "admin"})

    assert r.status_code == 200
    assert await _contar(sesion, Ventas) == 0
    cancelacion = (await sesion.execute(select(VentaCancelada))).scalar_one()
    assert cancelacion.nombre_producto == "Ibuprofeno 600mg"
    assert cancelacion.responsable == "admin"
    assert cancelacion.status == CancellationStatus.CANCELLED
    # decimal(10,2) en Aiven, double en ventas: MySQL lo devuelve como
    # Decimal y SQLAlchemy (Double en el modelo) lo convierte a float.
    assert cancelacion.importe == pytest.approx(25.90)
