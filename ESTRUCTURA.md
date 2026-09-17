# EasyFarma API — Migración de Spring Boot a FastAPI

Documento de referencia de la estructura del proyecto. Réplica funcional del backend
`farmacia-ko2-back` (Spring Boot 3 / Java 21) sobre **FastAPI + async**.

- **Proyecto origen:** `/home/jabier/Documentos/backup/farmacia-ko2-back` (rama `master`)
- **Proyecto destino:** `/home/jabier/Documentos/backup/farmacia-ko2-back_fastApi`
- **Python:** 3.12.3
- **Fecha:** 2026-09-01

---

## 1. Decisión de arquitectura: todo async

Se construye **async de principio a fin**. Motivos:

- FastAPI está diseñado async-first; es el idioma dominante en su ecosistema.
- SQLAlchemy 2.0 tiene soporte async maduro y estable.
- Es lo que más valor aporta de cara al mercado laboral.

**Matiz honesto:** no todas las empresas Python trabajan async. Django (síncrono) sigue
teniendo más cuota de mercado, y hay mucho FastAPI en producción con SQLAlchemy síncrono.
Async es *una* opción profesional válida y la más idiomática para FastAPI, no la única.

### Regla de oro del async (leer antes de escribir código)

> Una sola llamada **bloqueante** dentro de un `async def` congela el *event loop* entero
> y degrada el rendimiento de **toda** la aplicación, no solo de esa petición.

Prohibido dentro de un `async def`:

| Nunca (bloquea) | Usar en su lugar |
|---|---|
| `requests.get(...)` | `await httpx.AsyncClient().get(...)` |
| `time.sleep(n)` | `await asyncio.sleep(n)` |
| `session.query(...)` síncrona | `await session.execute(select(...))` |
| `open()` / lectura de ficheros | `aiofiles` |
| `bcrypt.hashpw(...)` (usa CPU, ~100 ms) | `await asyncio.to_thread(bcrypt.hashpw, ...)` |

Si una librería no tiene versión async, se envuelve con `await asyncio.to_thread(fn, args)`.

### Nota sobre el pool de conexiones

La base de datos en Aiven está limitada (en Spring: `hikari.maximum-pool-size=3`).
Con async es fácil abrir muchas conexiones a la vez, así que hay que **limitar el pool
explícitamente** en el engine:

```python
create_async_engine(url, pool_size=3, max_overflow=0, pool_pre_ping=True)
```

---

## 2. Stack elegido

| Necesidad | Librería | Equivalente en Spring |
|---|---|---|
| Framework web | `fastapi` | `spring-boot-starter-web` |
| Servidor ASGI | `uvicorn[standard]` | Tomcat embebido |
| ORM async | `sqlalchemy[asyncio]` 2.x | Hibernate / Spring Data JPA |
| Driver MySQL async | `aiomysql` | `mysql-connector-j` |
| Configuración | `pydantic-settings` | `application.properties` + `@Value` |
| Validación / DTOs | `pydantic` v2 | DTOs + Jackson |
| JWT | `pyjwt` | `jjwt` |
| Hash de contraseñas | `bcrypt` | `BCryptPasswordEncoder` |
| HTTP client async | `httpx` | `RestTemplate` |
| Migraciones (opcional) | `alembic` | (no había; `ddl-auto=none`) |
| Tests | `pytest`, `pytest-asyncio`, `httpx` | JUnit + `spring-security-test` |
| Multipart / formularios | `python-multipart` | — |

**Compatibilidad de contraseñas:** Spring Security genera hashes BCrypt con prefijo `$2a$`.
La librería `bcrypt` de Python los verifica sin problema, así que **los usuarios existentes
en la base de datos seguirán pudiendo entrar**. No hay que migrar contraseñas.

> Nota: se usa `bcrypt` directamente y no `passlib`, que lleva sin publicar versión desde
> 2020 y da problemas de compatibilidad con bcrypt 4.x.

---

## 3. Estructura de carpetas

```
farmacia-ko2-back_fastApi/
│
├── app/                              # Todo el código de la aplicación
│   ├── __init__.py
│   ├── main.py                       ← FpApplication.java + CORS de SecurityConfig
│   │
│   ├── core/                         ← paquete config/
│   │   ├── __init__.py
│   │   ├── config.py                 ← application.properties (pydantic-settings)
│   │   ├── database.py               ← DataSource + Hikari (async engine, sessionmaker)
│   │   └── security.py               ← JwtUtil.java (crear/validar JWT, hash bcrypt)
│   │
│   ├── models/                               ← paquete model/, solo las @Entity (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py                           ← DeclarativeBase común
│   │   ├── user_model.py                     ← Users.java              → tabla users
│   │   ├── authority_model.py                ← Authorities.java        → tabla authorities
│   │   ├── articulo_model.py                 ← Articulos.java          → tabla articulos
│   │   ├── venta_model.py                    ← Ventas.java             → tabla ventas
│   │   ├── venta_cancelada_model.py          ← VentaCancelada.java     → tabla ventas_canceladas
│   │   │                                       (+ enum CancellationStatus)
│   │   └── activity_log_model.py             ← ActivityLog.java        → tabla activity_log
│   │
│   ├── schemas/                              ← los *_DTO.java (Pydantic, entrada/salida)
│   │   ├── __init__.py
│   │   ├── auth_schema.py                    ← credenciales de login + respuesta {token}
│   │   ├── user_schema.py                    ← Insert_User_DTO.java + UserOut (sin password)
│   │   ├── articulo_schema.py                ← Insert_DTO.java + UpdateDTO.java
│   │   ├── venta_schema.py                   ← VentaDTO.java
│   │   ├── venta_cancelada_schema.py         ← entrada/salida de cancelaciones
│   │   ├── activity_log_schema.py            ← salida del historial
│   │   └── ia_schema.py                      ← MatchRequestDTO + MedicamentoAempsDTO
│   │
│   ├── repositories/                         ← paquete repository/ (acceso a datos, sin lógica)
│   │   ├── __init__.py
│   │   ├── user_repository.py                ← UserRepository + AuthoritiesRepository
│   │   ├── articulo_repository.py            ← ArticulosRepository
│   │   ├── venta_repository.py               ← VentasRepository
│   │   ├── venta_cancelada_repository.py
│   │   └── activity_log_repository.py
│   │
│   ├── services/                             ← paquete service/ (lógica de negocio)
│   │   ├── __init__.py
│   │   ├── user_service.py                   ← UserService.java
│   │   ├── articulo_service.py               ← ArticuloService.java
│   │   ├── venta_service.py                  ← VentaService.java (transacciones)
│   │   ├── venta_cancelada_service.py
│   │   ├── activity_log_service.py           ← ActivityLogService.java
│   │   ├── cima_service.py                   ← lógica AEMPS que hoy vive en CimaController
│   │   └── ia_service.py                     ← IaService.java (httpx async + x-api-key)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                           ← JwtAuthenticationFilter + @PreAuthorize
│   │   │                                       get_db / get_current_user / require_role
│   │   └── routes/                           ← paquete controller/
│   │       ├── __init__.py
│   │       ├── router.py                     ← agrupa todos los routers y los monta
│   │       ├── auth_controller.py            ← AuthController           → /auth
│   │       ├── user_controller.py            ← UserController           → /users
│   │       ├── articulo_controller.py        ← ArticuloController       → /articulos
│   │       ├── venta_controller.py           ← VentaController          → /ventas
│   │       ├── venta_cancelada_controller.py ← VentaCanceladaController → /cancelaciones
│   │       ├── activity_log_controller.py    ← ActivityLogController    → /activity-log
│   │       └── cima_controller.py            ← CimaController           → /api/cima
│   │
│   └── exceptions/                   ← paquete exception/
│       ├── __init__.py
│       ├── custom.py                 ← ResourceNotFoundException + ExternalServiceException
│       └── handlers.py               ← GlobalExceptionHandler (@app.exception_handler)
│
├── tests/                            ← src/test/java/
│   ├── __init__.py
│   ├── conftest.py                   ← fixtures: cliente async, BD de prueba
│   ├── test_auth_controller.py       ← AuthControllerTest.java
│   └── test_health.py                ← FpApplicationTests.java (contexto arranca)
│
├── alembic/                          # Opcional — el esquema ya existe en Aiven
│   ├── versions/
│   └── env.py
├── alembic.ini
│
├── .venv/                            # Entorno virtual (NO se sube a git)
├── .env                              # Secretos reales (NO se sube a git)
├── .env.example                      # Plantilla con las claves vacías (sí se sube)
├── .gitignore
├── requirements.txt                  ← pom.xml
├── Dockerfile                        ← Dockerfile (multistage)
├── docker-compose.yml                ← docker-compose.yml
├── .github/workflows/deploy.yml      ← mismo workflow de deploy
└── README.md
```

### Por qué esta estructura

Es la disposición estándar de un proyecto FastAPI mediano-grande (la que recomienda la
documentación oficial en "Bigger Applications" y la que popularizó la plantilla
`full-stack-fastapi-template`), y además mantiene **la misma separación por capas que ya
tienes en Java**, para que la traducción sea fichero a fichero:

```
controller  →  api/routes      (HTTP: recibe, valida, responde)
service     →  services        (lógica de negocio, transacciones)
repository  →  repositories    (consultas a la BD)
model       →  models          (tablas) + schemas (DTOs)
config      →  core            (arranque, seguridad, conexión)
exception   →  exceptions      (errores propios y su traducción a HTTP)
```

La única diferencia real de criterio es que en Python se **separa la tabla del DTO** en
dos carpetas (`models/` vs `schemas/`), mientras que en tu proyecto Java conviven las dos
cosas en el paquete `model/`. Esa separación es obligatoria aquí: las tablas son
SQLAlchemy y los DTOs son Pydantic, son dos librerías distintas.

### Convención de nombres: sufijo explícito en todos los ficheros

**Regla única: cada fichero lleva el sufijo de su capa.** Una clase Java se traduce a un
fichero Python con el mismo nombre en `snake_case`:

| Java | Python |
|---|---|
| `UserController.java` | `api/routes/user_controller.py` |
| `UserService.java` | `services/user_service.py` |
| `UserRepository.java` | `repositories/user_repository.py` |
| `Users.java` (`@Entity`) | `models/user_model.py` |
| `Insert_User_DTO.java` | `schemas/user_schema.py` |

Sí, el sufijo repite lo que ya dice la carpeta (`models/user_model.py`). Es redundante a
propósito: con la convención "corta" tendrías **tres ficheros llamados `user.py`** abiertos
a la vez en el editor y la pestaña no te diría cuál es cuál. El nombre completo elimina esa
ambigüedad en las pestañas, en los buscadores (`Ctrl+Mayús+N`), en los *stack traces* y en
los mensajes de error de importación.

> **Matiz honesto:** la convención más extendida en el ecosistema FastAPI es la corta
> (`api/routes/users.py`, `schemas/user.py`), apoyándose en que el paquete ya da el
> contexto: `from app.schemas import user`. Es igual de válida y la verás en la plantilla
> oficial `full-stack-fastapi-template`. Aquí se elige la explícita porque este proyecto
> es además un ejercicio de aprendizaje y porque `repositories/` y `services/` ya la usaban
> de forma natural. Lo importante es no mezclar las dos.

Y por lo mismo, al importar se nombra el módulo completo, nunca se abrevia:

```python
from app.models.user_model import Users          # la tabla (SQLAlchemy)
from app.schemas.user_schema import UserOut      # el DTO (Pydantic)
```

Excepciones a la regla, porque no tienen capa que desambiguar: `base.py`, `router.py`,
`deps.py`, `__init__.py` y todo lo de `core/` (`config.py`, `database.py`, `security.py`)
y `exceptions/` (`custom.py`, `handlers.py`).

---

## 4. Equivalencias conceptuales (no es traducción literal)

| Spring Boot | FastAPI | Comentario |
|---|---|---|
| `SwaggerConfig.java` | *(no existe)* | FastAPI genera `/docs` y `/openapi.json` solo. **Fichero eliminado.** |
| `JwtAuthenticationFilter` | `api/deps.py` | Deja de ser un filtro global: es una *dependencia* que se inyecta por router. |
| `@PreAuthorize` / `hasRole` | `Depends(require_role("SUPERADMIN"))` | Aquí encaja la jerarquía de roles y elimina los `if` repetidos del `UserController`. |
| `JdbcUserDetailsManager` | `user_repository` | Las dos consultas SQL del `SecurityConfig` pasan a ser consultas normales. |
| `@Transactional` | `async with session.begin():` | Imprescindible en `cancelar_venta`: devuelve stock y escribe en dos tablas. |
| `@Version` (bloqueo optimista) | `__mapper_args__ = {"version_id_col": version}` | SQLAlchemy lo soporta igual que Hibernate. |
| `RestTemplate` | `httpx.AsyncClient` | Para AEMPS y el microservicio de IA. |
| `@Autowired` | `Depends(...)` | Inyección de dependencias nativa de FastAPI. |
| `ResponseEntity.status(...)` | `raise HTTPException(...)` | O `Response(status_code=...)` cuando haga falta el cuerpo. |
| `application-dev.properties` | `.env` + `ENVIRONMENT=dev` | Un solo `config.py` que lee del entorno. |
| `SecurityContextHolder.getContext()` | `current_user: Users = Depends(get_current_user)` | El usuario autenticado se recibe como parámetro, no desde un contexto global. |

---

## 5. Endpoints a replicar

| Método | Ruta | Rol requerido | Origen |
|---|---|---|---|
| POST | `/auth/login` | público | `AuthController` |
| GET | `/auth/protected` | autenticado | `AuthController` |
| GET | `/users/all` | autenticado | `UserController` |
| GET | `/users/{username}` | autenticado | `UserController` |
| POST | `/users/insert` | ADMIN solo puede crear SELLER | `UserController` |
| PUT | `/users/update` | ADMIN no puede tocar ADMIN/SUPERADMIN | `UserController` |
| DELETE | `/users/{id}` | ADMIN no puede borrar ADMIN/SUPERADMIN | `UserController` |
| GET | `/articulos/All` | autenticado | `ArticuloController` |
| GET | `/articulos/search/{keyword}` | autenticado | `ArticuloController` |
| POST | `/articulos/insert` | autenticado | `ArticuloController` |
| PUT | `/articulos/updateStock` | autenticado (lote) | `ArticuloController` |
| PUT | `/articulos/updateItem` | autenticado | `ArticuloController` |
| PATCH | `/articulos/{id}/aemps` | autenticado | `ArticuloController` |
| DELETE | `/articulos/{id}` | autenticado | `ArticuloController` |
| GET | `/ventas/all` | autenticado | `VentaController` |
| GET | `/ventas/{username}` | autenticado | `VentaController` |
| POST | `/ventas/registrar` | autenticado | `VentaController` |
| POST | `/ventas/registrar/list` | autenticado (lote) | `VentaController` |
| DELETE | `/ventas/cancelar/{id}?responsable=` | autenticado | `VentaController` |
| GET | `/cancelaciones` | autenticado | `VentaCanceladaController` |
| POST | `/cancelaciones` | autenticado | `VentaCanceladaController` |
| GET | `/activity-log/all` | **SUPERADMIN** | `ActivityLogController` |
| GET | `/api/cima/medicamento?nregistro=` | autenticado | `CimaController` |
| GET | `/api/cima/buscar` | autenticado | `CimaController` |
| GET | `/api/cima/validar?nombre=` | autenticado | `CimaController` |

### Flujo de `/api/cima/validar` (el más complejo)

1. Si el producto ya existe en inventario → `409 Conflict`.
2. Consulta a AEMPS (`https://cima.aemps.es/cima/rest/medicamentos`), hasta 100 resultados.
3. Convierte los resultados crudos a `MedicamentoAempsDTO` (`nregistro` + `nombre`).
4. Si no hay resultados → `404 Not Found`.
5. Envía la lista al microservicio de IA (`POST {IA_SERVICE_URL}/api/v1/ia/match`, cabecera `x-api-key`).
6. Registra la búsqueda en `activity_log` con la acción `IA_MATCH` y la IP.
7. Devuelve el resultado de la IA.

---

## 6. Variables de entorno (`.env`)

Las mismas que ya usa el backend Java, para poder apuntar a la misma base de datos:

```
PORT=8000
JWT_SECRET=
DB_URL=            # formato SQLAlchemy: mysql+aiomysql://user:pass@host:puerto/basedatos
DB_USER=
DB_PASSWORD=
IA_SERVICE_URL=
IA_SERVICE_API_KEY=
ENVIRONMENT=dev
```

**Ojo:** el formato de `DB_URL` cambia respecto a Java. Spring usa
`jdbc:mysql://host:puerto/bd`; SQLAlchemy necesita `mysql+aiomysql://usuario:clave@host:puerto/bd`.
Aiven además exige SSL, que se pasa aparte en `connect_args`.

---

## 7. Orden de construcción

Se construye de dentro hacia fuera: primero lo que no depende de nada.

| Paso | Qué se hace | Ficheros |
|---|---|---|
| 1 | Esqueleto, dependencias y arranque | `requirements.txt`, `app/main.py`, `.env` |
| 2 | Configuración y conexión a BD | `core/config.py`, `core/database.py` |
| 3 | Tablas | `models/*_model.py` |
| 4 | DTOs | `schemas/*_schema.py` |
| 5 | Seguridad: JWT + bcrypt | `core/security.py` |
| 6 | Login funcionando | `repositories/user_repository.py`, `services/user_service.py`, `api/routes/auth_controller.py` |
| 7 | Dependencias de autenticación y roles | `api/deps.py` |
| 8 | Errores propios | `exceptions/*` |
| 9 | CRUD de artículos | `repositories` + `services` + `routes` de artículos |
| 10 | Ventas y cancelaciones (transacciones) | íd. ventas |
| 11 | Activity log | íd. activity log |
| 12 | AEMPS + microservicio IA | `cima_service.py`, `ia_service.py`, `routes/cima_controller.py` |
| 13 | Tests | `tests/*` |
| 14 | Docker y despliegue | `Dockerfile`, `docker-compose.yml`, workflow |

---

## 8. Estado actual

Ya existe en la carpeta:

- `.venv/` con Python 3.12.3 — FastAPI 0.141.1, uvicorn 0.52.4, pydantic 2.13.5 instalados.
- `main.py` — plantilla "Hello World" de PyCharm. **Se sustituirá por `app/main.py`.**
- `test_main.http` — peticiones de prueba de PyCharm, se puede conservar o borrar.
- `.idea/` — configuración de PyCharm, va al `.gitignore`.

Pendiente: todo lo demás.
