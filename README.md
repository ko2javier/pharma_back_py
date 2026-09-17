# pharma_back_py — EasyFarma API en FastAPI

Réplica del backend **EasyFarma** (`farmacia-ko2-back`, Spring Boot 3 / Java 21) sobre
**FastAPI totalmente async**. Es a la vez una migración y un proyecto de aprendizaje
Java → Python: cada fichero se corresponde con su `.java` de origen.

> ⚠️ **Proyecto en construcción.** El esqueleto está completo, pero la mayoría de los
> ficheros todavía están vacíos. Ver *Estado actual* más abajo.

## Stack

| Necesidad | Librería | Equivalente en Spring |
|---|---|---|
| Framework web | `fastapi` | `spring-boot-starter-web` |
| Servidor ASGI | `uvicorn[standard]` | Tomcat embebido |
| ORM async | `sqlalchemy[asyncio]` 2.x | Hibernate / Spring Data JPA |
| Driver MySQL async | `aiomysql` | `mysql-connector-j` |
| Validación / DTOs | `pydantic` v2 | Jakarta Validation + DTOs |
| JWT | `PyJWT` | `jjwt` |
| Hash de contraseñas | `bcrypt` | `BCryptPasswordEncoder` |
| Cliente HTTP async | `httpx` | `RestTemplate` / `WebClient` |

Python 3.12.3. Versiones exactas fijadas en `requirements.txt`.

## Decisiones de diseño

- **Async de principio a fin.** Una sola llamada bloqueante dentro de un `async def`
  congela el *event loop* de toda la aplicación. Lo que no tenga versión async se
  envuelve en `await asyncio.to_thread(...)` — `bcrypt` incluido.
- **Pool limitado a 3 conexiones** (`pool_size=3, max_overflow=0`) para respetar la
  cuota de Aiven, igual que `hikari.maximum-pool-size=3` en el Java.
- **`models/` y `schemas/` separados**, aunque en Java conviven en `model/`.
- **Sufijo de capa obligatorio en el nombre de cada fichero**: `user_model.py`,
  `user_schema.py`, `user_repository.py`, `user_service.py`, `user_controller.py`.
  Con tres `user.py` abiertos en el IDE no se distingue la capa. Sin sufijo solo:
  `base.py`, `router.py`, `deps.py`, `core/*`, `exceptions/*`.
- **`app/models/__init__.py` importa las 6 entidades.** SQLAlchemy no escanea el
  classpath como Hibernate: una tabla no existe en `Base.metadata` si nadie la ha
  importado. Es el "escáner de entidades" a mano.
- Apunta a la **misma base de datos** que el backend Java. Los hashes BCrypt `$2a$`
  de Spring los verifica la librería `bcrypt` de Python, así que no hay que migrar
  contraseñas.

## Puesta en marcha

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # el -r arrastra requirements.txt

cp .env.example .env                  # y rellenar los valores

uvicorn app.main:app --reload
```

Documentación interactiva en <http://localhost:8000/docs>.

**Ojo con `DB_URL`:** cambia de formato respecto a Java. Spring usa
`jdbc:mysql://host:puerto/bd`; SQLAlchemy necesita
`mysql+aiomysql://usuario:clave@host:puerto/bd`.

## Estado actual

De los 14 pasos del plan (`ESTRUCTURA.md`, sección 7):

| Paso | Qué | Estado |
|---|---|---|
| 1 | Esqueleto, dependencias y arranque | ✅ hecho y verificado |
| 2 | `core/config.py`, `core/database.py` | ⬜ siguiente |
| 3 | `models/` — 6 entidades + `base.py` | ✅ hecho y verificado |
| 4 | `schemas/` — 7 ficheros, 14 clases Pydantic | ✅ hecho y verificado |
| 5–14 | Seguridad, repositorios, servicios, controladores, tests | ⬜ pendiente |

Los ficheros de las capas pendientes existen vacíos, con su nombre definitivo.
`app/main.py` arranca y `/docs` responde; todavía no hay router registrado.

## Documentación

- **[`ESTRUCTURA.md`](ESTRUCTURA.md)** — el plan completo: árbol de carpetas anotado con
  el `.java` de origen de cada fichero, tabla de equivalencias Spring → FastAPI, los 25
  endpoints y los 14 pasos de construcción en orden. **Leer antes de tocar código.**
- **[`.claude/memory/`](.claude/memory/)** — notas de contexto acumuladas durante la
  migración: contrato JSON que debe respetar la API, decisiones tomadas y hallazgos ya
  verificados que no merece la pena volver a investigar.

## Proyecto de origen

`farmacia-ko2-back` — Spring Boot 3, Java 21, MySQL en Aiven. Este repo replica sus 25
endpoints REST y su modelo de datos; el contrato JSON que consume el frontend Angular se
mantiene salvo las desviaciones deliberadas documentadas en
`.claude/memory/fastapi_api_contract.md`.
