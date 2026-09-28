# app/exceptions/custom.py
#
# Equivalente a exception/*.java, pero sin ResourceNotFoundException.java
# calcado: en el Java esa clase existe y tiene handler, pero no la lanza nada
# — todos los "no encontrado" de ArticuloService/UserService usan
# RuntimeException a pelo, así que en producción esos casos devuelven 500, no
# 404. Aquí SÍ se lanza esta excepción a propósito: es un endurecimiento
# deliberado (como los 3 ya recogidos en fastapi_api_contract.md) y no rompe
# a ningún cliente — el frontend Angular sólo mira err.status en 4 sitios
# (401/403 en el interceptor, y tres 409 puntuales) y en ninguno de ellos le
# importa si "no encontrado" es 404 o 500.
#
# Nada de FastAPI aquí, mismo criterio que core/security.py: son excepciones
# Python normales que lanzan repositories/services; handlers.py (que sí
# importa FastAPI) decide en qué respuesta HTTP se convierten.


class ResourceNotFoundException(Exception):
    """Artículo, usuario o venta que no existe (por id o código)."""


class DuplicateResourceException(Exception):
    """Ya existe un recurso con esa clave única.

    Cubre con un solo tipo los dos chequeos que en el Java estaban sueltos en
    cada controlador: "El producto ya existe en el inventario"
    (CimaController.validarMedicamento) y "El usuario ya existe"
    (UserController.insertarUsuario). Las dos las mira el frontend por su
    código 409 (almacen.component.ts y users.component.ts), nunca por el
    texto del mensaje.
    """


class InsufficientStockException(Exception):
    """No hay unidades suficientes para descontar lo que se quiere vender.

    En el Java iba en el mismo `throw` que el "no encontrado"
    (ArticuloService.java:39, un RuntimeException con los dos motivos en el
    mismo mensaje) y salía como 500. Aquí se separa porque no es lo mismo: el
    artículo existe, es su estado el que no permite la operación. Va como 409
    a propósito — carritocomponent.ts:189 ya tiene mensaje propio para el 409
    de /updateStock ("el stock fue modificado, recarga e inténtalo"), que es
    casi exactamente lo que ha pasado.
    """


class AempsNotFoundException(Exception):
    """AEMPS no tiene resultados para la búsqueda.

    Distinta de ResourceNotFoundException aunque comparta el 404: aquí no es
    que falte algo en nuestra base de datos, es que el catálogo oficial no
    tiene ese medicamento. almacen.component.ts:309 la distingue del 409 de
    arriba con un mensaje distinto ("No encontrado en AEMPS").
    """


class ExternalServiceException(Exception):
    """Fallo hablando con un servicio externo (AEMPS o el microservicio IA).

    Es la única de las cuatro que también existe y se lanza de verdad en el
    Java (CimaController, catch de RestTemplate) — se replica el nombre tal
    cual.
    """
