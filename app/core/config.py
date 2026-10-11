# app/core/config.py
#
# Equivale a application.properties + las anotaciones @Value de Spring.
# Una sola clase declara TODA la configuración de la aplicación.

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# La raiz del proyecto, calculada desde este fichero: app/core/config.py -> ../..
# Hace falta para resolver rutas relativas sin depender del directorio desde el
# que se arranque uvicorn. Es lo que en Spring te daba el classpath: un
# classpath:ca.pem se encuentra siempre, "./ca.pem" sólo si el cwd acompaña.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # ── Servidor ──────────────────────────────────────────────────────────
    #
    # INCORRECTO (lo que había antes):
    #     port: int = 8000
    #
    # El 8000 es justo el puerto del microservicio de IA en local. Si un día
    # falta el .env, esta API arrancaría encima de él y IA_SERVICE_URL
    # apuntaría a sí misma. Sin valor por defecto, pydantic obliga a definirlo.
    port: int

    # ── Seguridad ─────────────────────────────────────────────────────────
    # Sin default a propósito: si falta, la app no arranca. Es el mismo
    # comportamiento que ${JWT_SECRET} en el application.properties del Java.
    jwt_secret: str

    # ── Base de datos ─────────────────────────────────────────────────────
    #
    # INCORRECTO (lo que había antes):
    #     db_url: str
    #
    # Dos problemas. Uno: en el .env no existe DB_URL, así que pydantic
    # lanzaba "Field required". Dos: aunque existiera, una URL de SQLAlchemy
    # lleva usuario y contraseña dentro (mysql+aiomysql://user:pass@host...),
    # de modo que tendrías el mismo secreto en dos sitios y una contraseña
    # con @ o # rompería la cadena.
    #
    # Se guardan las cinco piezas sueltas y la URL se compone abajo, en la
    # propiedad database_url.
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # ── Certificado de la CA de Aiven ─────────────────────────────────────
    #
    # Aiven firma el certificado del servidor con una CA propia, que no está en
    # el almacén de confianza del sistema. Sin este fichero, el handshake TLS
    # muere con "CERTIFICATE_VERIFY_FAILED: self-signed certificate in
    # certificate chain". Es el equivalente al truststore de Java.
    #
    # SÍ lleva valor por defecto (al contrario que los secretos): el fichero
    # viaja en el repositorio, no es un secreto, y la ruta es siempre la misma.
    # Se declara aqui y no a mano en database.py para poder apuntar a otra ruta
    # por entorno -- en la imagen Docker estará en /app/ca.pem.
    aiven_ca_path: Path = Path("ca.pem")

    # ── Microservicio de IA ───────────────────────────────────────────────
    #
    # INCORRECTO (lo que había antes):
    #     ia_service_url: str = ""
    #     ia_service_api_key: str = ""
    #
    # Con "" por defecto, si faltan en el .env la aplicación arranca tan
    # tranquila y revienta mucho más tarde, al llamar al microservicio, con un
    # error incomprensible. Sin default falla al arrancar y te dice el nombre
    # exacto de la variable que falta. Fallar pronto y fuerte.
    ia_service_url: str
    ia_service_api_key: str

    # ── Entorno ───────────────────────────────────────────────────────────
    # Este SÍ lleva default: "dev" es el caso normal al trabajar en local.
    environment: str = "dev"

    # ── CORS ──────────────────────────────────────────────────────────────
    # Era el "TODO (paso 2)" que quedó apuntado en main.py: la lista blanca
    # estaba escrita a mano dentro del middleware. Aquí se puede tener una
    # lista distinta por entorno sin tocar código.
    #
    # Ojo: si algún día quieres fijarla desde el .env, pydantic-settings
    # espera JSON en la variable, no valores separados por comas.
    cors_origins: list[str] = [
        "http://localhost:4200",
        "https://farmacia-ko2.up.railway.app",
        "https://pharma.ko2-oreilly.com",
        "https://pharma-b.ko2-oreilly.com",
        "https://farmacia-ko2-frontend.vercel.app",
        "https://farmacia-ko2-back-production.up.railway.app",
    ]

    # ── Origen de los valores ─────────────────────────────────────────────
    #
    # Faltaba extra="ignore". Por defecto pydantic-settings RECHAZA cualquier
    # variable del .env que la clase no declare: eran los cinco errores
    # "Extra inputs are not permitted". Con "ignore", el .env puede llevar
    # variables para otras herramientas (HOST_PORT para Docker, por ejemplo)
    # sin tumbar el arranque.
    model_config = SettingsConfigDict(
        # ANTES: env_file=".env"
        # Ruta relativa al directorio desde el que se LANZA el proceso. Con
        # PyCharm ejecutando app\main.py el cwd es ...pp, ahi no hay .env y
        # los 9 campos obligatorios salian como "Field required" de golpe.
        # Mismo criterio que aiven_ca_file: un fichero de la raiz se resuelve
        # contra la raiz.
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── URL de SQLAlchemy, derivada ───────────────────────────────────────
    # Una @property es un atributo calculado: se usa como settings.database_url,
    # sin paréntesis. Es el equivalente a un @Bean que construye un valor a
    # partir de otros.
    #
    # quote_plus() escapa la contraseña. Si contiene @ : / o #, sin escapar
    # partiría la URL por el sitio equivocado y el error sería indescifrable.
    # Ruta absoluta del ca.pem. Si en el .env se pone una ruta relativa, se
    # resuelve contra la raíz del proyecto y no contra el directorio actual:
    # arrancar uvicorn desde otra carpeta dejaría de encontrarlo.
    @property
    def aiven_ca_file(self) -> Path:
        if self.aiven_ca_path.is_absolute():
            return self.aiven_ca_path
        return _PROJECT_ROOT / self.aiven_ca_path

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


# ── Acceso a la configuración ─────────────────────────────────────────────
#
# TU VERSIÓN (funciona perfectamente, es un patrón común):
#     settings = Settings()
#
# La única diferencia práctica está en los tests del paso 13: con una función
# puedes sustituirla mediante app.dependency_overrides para apuntar a otra
# base de datos. Con la variable de módulo no, porque se construye al importar.
#
# @lru_cache hace que Settings() se cree UNA sola vez: sin ella, cada
# Depends(get_settings) releería el .env del disco en cada petición.
# Es el bean singleton de Spring, en un decorador.
@lru_cache
def get_settings() -> Settings:
    return Settings()
