# app/services/cima_service.py
#
# Equivale a las tres llamadas a AEMPS que en el Java viven DENTRO de
# CimaController.java (allí no hay service: el controlador hace el
# new RestTemplate() él mismo). Aquí se sacan a un service para que el
# controlador sólo decida códigos HTTP, como en el resto del proyecto.
#
# El cliente HTTP entra como primer parámetro, igual que la AsyncSession en
# los demás services: este fichero no sabe de dónde sale (lo crea el lifespan
# de main.py y lo inyecta un Depends). Es el @Autowired RestTemplate que el
# Java no tenía — allí era un new RestTemplate() por llamada, sin reutilizar
# conexiones.
#
# Lo que NO va aquí, a propósito:
#   - el 409 de "ya existe en inventario" (es de nuestra BD) → controlador
#   - el 404 de "AEMPS no tiene resultados" (lo decide quien recibe la lista
#     vacía) → controlador
#   - la llamada a la IA → ia_service.py, y SIN try: si la IA falla debe dar
#     500 como en el Java, no el 502 de aquí.

import httpx

from app.exceptions.custom import ExternalServiceException
from app.schemas.ia_schema import MedicamentoAemps

# Hardcodeadas en el Java (CimaController.java:25 y :42), sin propiedad en
# application.properties. Se mantienen como constantes: es la API pública
# oficial, no cambia por entorno.
AEMPS_BASE_URL = "https://cima.aemps.es/cima/rest"

_ERROR_AEMPS = "Error conectando con AEMPS"


class CimaService:

    # ── GET /api/cima/medicamento ─────────────────────────────────────────
    #
    # Devuelve el TEXTO crudo, no un dict, igual que el ResponseEntity<String>
    # del Java. No es pereza, es necesario: con un nregistro que no existe
    # AEMPS contesta 204 con cuerpo vacío (comprobado el 2026-10-11), y
    #     return response.json()
    # reventaría con ValueError → 502. El Java en ese caso devuelve 200 vacío
    # (getForObject da null y lo reenvía), y eso es lo que se replica.
    @staticmethod
    async def obtener_medicamento(client: httpx.AsyncClient, nregistro: str) -> str:
        return await CimaService._get_texto(
            client, "/medicamento", {"nregistro": nregistro}
        )

    # ── GET /api/cima/buscar ──────────────────────────────────────────────
    #
    # El Angular manda también &tamanioPagina=8 (cima.service.ts:18), pero el
    # Java sólo declara nombre y pagina y Spring descarta el resto. NO
    # reenviarlo: cambiaría lo que ve el catálogo en producción. (Y de todas
    # formas AEMPS lo ignora: responde siempre con páginas de 200.)
    @staticmethod
    async def buscar(client: httpx.AsyncClient, nombre: str, pagina: int) -> str:
        return await CimaService._get_texto(
            client, "/medicamentos", {"nombre": nombre, "pagina": pagina}
        )

    # ── Paso 2 y 3 de GET /api/cima/validar ───────────────────────────────
    #
    # Aquí sí se parsea, porque hay que convertir cada resultado al
    # MedicamentoAemps que entiende la IA (nregistro → id).
    #
    # tamanioPagina=100 se manda por fidelidad al Java, pero AEMPS lo ignora
    # (comprobado: con tamanioPagina=2 devuelve "tamanioPagina":200). El
    # comentario "hasta 100 resultados" del Java es falso: la IA recibe hasta
    # 200.
    #
    # Devuelve [] si no hay resultados; el 404 lo pone el controlador.
    @staticmethod
    async def buscar_para_ia(client: httpx.AsyncClient, nombre: str) -> list[MedicamentoAemps]:
        try:
            response = await client.get(
                f"{AEMPS_BASE_URL}/medicamentos",
                params={"nombre": nombre, "pagina": 1, "tamanioPagina": 100},
            )
            response.raise_for_status()
            # Cuerpo vacío: en el Java getForObject(..., Map.class) da null y
            # acaba en lista vacía → 404. Sin este if, .json() lanzaría
            # ValueError → 502.
            datos = response.json() if response.content else None
        except (httpx.HTTPError, ValueError) as e:
            raise ExternalServiceException(_ERROR_AEMPS) from e

        # INCORRECTO (calco literal del Java):
        #     for m in datos["resultados"]: ...
        # Con "resultados": null el Java da NullPointerException → 500. Aquí
        # se trata como lista vacía → 404, que es lo que significa.
        resultados = (datos or {}).get("resultados") or []

        # Los None → "" son del Java (CimaController.java:92-93). Se comprueba
        # "is None" y no "or": un valor falsy que no sea None (0, "") debe
        # pasar por str() como hace el toString() del Java.
        return [
            MedicamentoAemps(
                id="" if m.get("nregistro") is None else str(m["nregistro"]),
                nombre="" if m.get("nombre") is None else str(m["nombre"]),
            )
            for m in resultados
        ]

    # ── Común a /medicamento y /buscar ────────────────────────────────────
    #
    # Las tres trampas de pasar de RestTemplate a httpx están aquí:
    #
    # 1. params= y no concatenar. El Java hace "?nombre=" + nombre: un "&" en
    #    el nombre mete parámetros nuevos en la petición a AEMPS. httpx los
    #    codifica. Desviación deliberada, arregla un fallo.
    #
    # 2. raise_for_status(). RestTemplate lanza excepción con un 4xx/5xx;
    #    httpx NO — sin esta línea, una página de error 503 de AEMPS se
    #    reenviaría al Angular como si fuera una respuesta buena.
    #
    # 3. httpx.HTTPError cubre conexión rechazada, timeout y el
    #    HTTPStatusError del punto 2. Es el catch (Exception e) del Java,
    #    pero sin tragarse también los bugs nuestros.
    @staticmethod
    async def _get_texto(client: httpx.AsyncClient, ruta: str, params: dict) -> str:
        try:
            response = await client.get(f"{AEMPS_BASE_URL}{ruta}", params=params)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ExternalServiceException(_ERROR_AEMPS) from e
        return response.text
