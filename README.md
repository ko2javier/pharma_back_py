# pharma_back_py — EasyFarma API on FastAPI

A full rewrite of the **EasyFarma** pharmacy backend (`farmacia-ko2-back`, Spring Boot 3 /
Java 21) on **fully async FastAPI**. Same database, same 25 REST endpoints, same JSON
contract — so the existing Angular frontend talks to it without a single change.

**It is live.** Since 2026-10-12 the production frontend at `pharma.ko2-oreilly.com` is
served by this API, running on a Hetzner VPS behind Cloudflare. The Java backend stays up
on its own subdomain as a rollback path.

## Why

The Java backend works. This is not a rescue project — it is a deliberate port, written to
learn Python the way a working codebase forces you to: every file here maps to the `.java`
file it replaces, and every deviation from the original is documented and justified rather
than quietly introduced.

## Stack

| Concern | Library | Spring equivalent |
|---|---|---|
| Web framework | `fastapi` 0.141 | `spring-boot-starter-web` |
| ASGI server | `uvicorn[standard]` | embedded Tomcat |
| Async ORM | `sqlalchemy[asyncio]` 2.0 | Hibernate / Spring Data JPA |
| MySQL driver | `aiomysql` | `mysql-connector-j` |
| Validation / DTOs | `pydantic` v2 | Jakarta Validation + DTOs |
| JWT | `PyJWT` | `jjwt` |
| Password hashing | `bcrypt` | `BCryptPasswordEncoder` |
| Async HTTP client | `httpx` | `RestTemplate` |

Python 3.14. Every version pinned in `requirements.txt` — there is no
`spring-boot-starter-parent` here to decide them for you.

## Design decisions

- **Async all the way down.** One blocking call inside an `async def` freezes the event
  loop for every request, not just its own. Anything without an async version is wrapped in
  `asyncio.to_thread(...)` — `bcrypt` included: four hashes in a row block the loop for
  **821 ms** called directly, **22 ms** through a thread. Spring never had this problem
  because each request owned a Tomcat thread.
- **The connection pool is capped at 3** (`pool_size=3, max_overflow=0`) to stay inside the
  Aiven quota, mirroring `hikari.maximum-pool-size=3` in the Java.
- **Same database, same passwords.** Spring's `$2a$` BCrypt hashes verify as-is with
  Python's `bcrypt`, so no user had to reset anything.
- **Stricter TLS than the original.** The Java connects to Aiven with
  `verifyServerCertificate=false`; this API ships Aiven's CA certificate and verifies the
  chain and the hostname.
- **`models/` and `schemas/` are separate packages**, though Java keeps both in `model/`.
- **Every file carries its layer as a suffix** — `user_model.py`, `user_schema.py`,
  `user_repository.py`, `user_service.py`, `user_controller.py`. The idiomatic short form
  (`schemas/user.py`) was rejected on purpose: three tabs named `user.py` are
  indistinguishable in an editor.
- **`app/models/__init__.py` imports all six entities by hand.** SQLAlchemy has no
  classpath scan: a table that nobody imported does not exist in `Base.metadata`, and
  Alembic would happily generate a migration dropping it.

## Running it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # then fill in the values
python -m app.main
```

Interactive docs at <http://localhost:8001/docs>.

Nine environment variables are required and **none has a default**: a missing one stops the
app at startup naming the variable, instead of failing later with something cryptic.

> **On Windows**, start it with `python -m app.main`, not the bare `uvicorn` command.
> uvicorn 0.36+ picks the event loop through a factory and ignores
> `set_event_loop_policy`; the Windows default (`ProactorEventLoop`) cannot do MySQL's
> mid-connection TLS upgrade, and the failure surfaces as an unhelpful
> `OSError [WinError 87]`. `app/main.py` pins `asyncio:SelectorEventLoop`, which is also
> the Linux default, so it is one line for both systems.

## Tests

```bash
pytest -q                 # 195 tests, ~1.6 s, no network and no database
pytest -m integration     # against a real MySQL in Docker (Testcontainers), ~30 s
```

Every external boundary is mocked in the default run: it never opens a connection to
Aiven, to AEMPS or to the AI service.

**Integration tests run against the real schema, not one generated from the models.** The
database schema was created by hand (`ddl-auto=none` in the original Java backend), and the
ORM models deliberately declare no foreign keys, so `create_all()` would build a database
without the `ON DELETE CASCADE` rules that matter most. Instead, `tests/schema.sql` is the
production DDL dumped with `SHOW CREATE TABLE`, loaded into a throwaway MySQL container.
The suite runs twice — on **MySQL 8.0.45** (production today) and on **8.4** (the version
the managed database is forced onto after 31 October 2026) — so the upgrade is tested
before it happens. They are excluded from the default run with a pytest marker, so the
fast suite and CI do not need Docker.

**The suite was tested against itself.** Five real bugs were injected one at a time — an
auth gate removed from `/articulos`, `require_role` comparing against the wrong role
prefix, a 24-hour token instead of 10, a SELLER allowed to create users, a 204 where the
contract says 200 — and each one turned the suite red. A green suite that has never been
shown to fail proves nothing.

## Deployment

```
browser ──https──▶ Cloudflare ──https──▶ nginx (VPS) ──http──▶ container :8001
```

Every push to `master` goes to production through `.github/workflows/deploy.yml`, and
nothing reaches the server without passing both test suites:

```
push ──┬──▶ tests         195 unit and contract tests, mocked database
       └──▶ integration   real MySQL 8.0 and 8.4 via Testcontainers
                 │  both must pass
                 ▼
            build-and-push   image to ghcr.io, tagged `latest` and the commit SHA
                 │
                 ▼
            deploy           SSH into the VPS, pull that SHA, restart, wait for a 200
```

The two test jobs run in parallel, so the pipeline waits for the slower one rather than
for both. The deploy uses the commit SHA, not `latest`, so the running container always
says exactly which code it is — and rolling back is the same command with the previous SHA.
If the API does not answer 200 within 30 seconds of the restart, the job fails and prints
the container's last log lines.

The server pulls the image; it never builds. The `docker-compose.yml` here is the one
running in production — it joins an external Docker network so the API can reach the AI
microservice by container name. Changes to that file or to the server's `.env` are still
applied by hand: the pipeline only swaps the image.

## Documentation

- **[`ESTRUCTURA.md`](ESTRUCTURA.md)** — the full build log, in Spanish: the directory tree
  annotated with the originating `.java` file, a Spring → FastAPI mapping table, all 25
  endpoints, and the 14 construction steps with what each one taught. Read it before
  touching the code.
- **[`.env.example`](.env.example)** — the nine required variables.

## Original project

`farmacia-ko2-back` — Spring Boot 3, Java 21, MySQL on Aiven. This repository replicates
its 25 REST endpoints and its data model. Where behaviour differs, it is deliberate and
documented in `ESTRUCTURA.md` — for instance, AEMPS query parameters are URL-encoded here,
where the Java concatenated them into the URL.
