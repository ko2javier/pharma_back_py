# app/services/ia_service.py
# ← IaService.java
#
# Un solo POST al microservicio de IA (distinguished-vibrancy_micro_GPT) con la
# cabecera x-api-key. El cliente HTTP entra como parámetro, igual que en
# cima_service.py.
#
# OJO — AQUÍ NO HAY try/except, Y ES A PROPÓSITO.
#
# En el Java no hay ningún try ni en IaService.java ni alrededor de la llamada
# (CimaController.java:105). Si la IA está caída, tarda demasiado, rechaza la
# api-key (401) o revienta (5xx), la excepción de RestTemplate sube sin
# capturar hasta el @ExceptionHandler(Exception.class) genérico → 500
# "Error interno del servidor". NO es el 502 de AEMPS, aunque las dos sean
# "servicio externo caído".
#
# Decisión del 2026-10-11: se replica el 500 y queda como deuda. Aquí sube la
# excepción de httpx tal cual y la recoge el generic_exception_handler de
# handlers.py. Al Angular le da igual: almacen.component.ts:307-312 sólo
# distingue 409 y 404, todo lo demás cae en el mismo "No se pudo validar".
#
# Consecuencia que también se replica: si la IA falla, el controlador no llega
# a escribir el IA_MATCH, así que los intentos fallidos no dejan rastro en el
# activity_log.

import httpx

from app.core.config import get_settings
from app.schemas.ia_schema import IaMatchRequest, MedicamentoAemps

# Un LLM tarda bastante más que AEMPS: el cliente compartido va con 10 s y esta
# llamada lo sube a 30. Valor puesto a ojo, sin medir. El Java no tiene ningún
# timeout (new RestTemplate() sin configurar): esto es desviación deliberada,
# porque en async una llamada colgada deja la conexión abierta para siempre.
IA_TIMEOUT_SEGUNDOS = 30.0


class IaService:

    @staticmethod
    async def llamar_microservicio_ia(
            client: httpx.AsyncClient,
            busqueda: str,
            lista_medicamentos: list[MedicamentoAemps],
    ) -> dict:
        """Equivalente a Map<String, Object> llamarMicroservicioIa(String, List<MedicamentoAempsDTO>)"""
        settings = get_settings()

        cuerpo = IaMatchRequest(busqueda_usuario=busqueda, lista_limpia=lista_medicamentos)

        response = await client.post(
            f"{settings.ia_service_url}/api/v1/ia/match",
            # model_dump() da las claves en snake_case (busqueda_usuario,
            # lista_limpia), que es lo que espera el micro: es Python también.
            # El Java tenía que forzarlas con @JsonProperty.
            json=cuerpo.model_dump(),
            headers={"x-api-key": settings.ia_service_api_key},
            timeout=IA_TIMEOUT_SEGUNDOS,
        )

        # INCORRECTO (lo obvio viniendo de RestTemplate):
        #     return response.json()
        #
        # RestTemplate lanza excepción con un 4xx/5xx; httpx NO. Sin esta línea,
        # una api-key mala (401 del micro) se devolvería al Angular como un 200
        # con el cuerpo de error dentro. Con ella, HTTPStatusError → 500, como
        # el Java.
        response.raise_for_status()

        return response.json()
