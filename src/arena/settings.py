"""
Configuração do Documentos Arena.

Tudo que varia entre ambientes vem de variável de ambiente (ver .env.example).
Nunca escreva credencial neste arquivo — AGENTS.md §6.
"""

from pathlib import Path

import environ

# src/arena/settings.py → SRC_DIR = src/ ; BASE_DIR = raiz do repositório.
SRC_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = SRC_DIR.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    ARMAZENAMENTO=(str, "local"),
    PROVEDOR_IA=(str, "fake"),
    PROVEDOR_COMPLIANCE=(str, "fake"),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# --- Aplicações -------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

TERCEIROS = [
    "django_htmx",
]

# Apps do projeto (AGENTS.md §8).
APPS_LOCAIS = [
    "contas",
    "auditoria",
    "documentos",
    "contrapartes",
    "operacoes",
    "solicitacoes",
    "analise",
    "compliance",
    "credito",
    "juridico",
]

INSTALLED_APPS = DJANGO_APPS + TERCEIROS + APPS_LOCAIS

# Modelo de usuário próprio desde o início: trocar depois da primeira migração
# é inviável na prática.
AUTH_USER_MODEL = "contas.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "arena.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [SRC_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "analise.contexto.papeis",
            ],
        },
    },
]

WSGI_APPLICATION = "arena.wsgi.application"
ASGI_APPLICATION = "arena.asgi.application"

# --- Banco ------------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticação -----------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"

# --- Localização (AGENTS.md §3) ---------------------------------------------

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Arquivos estáticos e documentos ----------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [SRC_DIR / "static"]

ARMAZENAMENTO = env("ARMAZENAMENTO")

# O backend com manifest exige `collectstatic` antes de qualquer {% static %};
# em desenvolvimento e nos testes isso quebraria a renderização, então ele fica
# reservado para o deploy, onde o collectstatic é passo obrigatório.
BACKEND_ESTATICOS = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if not DEBUG
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)

if ARMAZENAMENTO == "s3":
    # Bucket privado, acesso apenas por presigned URL (AGENTS.md §5.4).
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
                "region_name": env("AWS_S3_REGION_NAME", default="sa-east-1"),
                "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),
                "default_acl": None,
                "querystring_auth": True,
                "querystring_expire": 300,
                "file_overwrite": False,
            },
        },
        "staticfiles": {"BACKEND": BACKEND_ESTATICOS},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": BACKEND_ESTATICOS},
    }
    MEDIA_ROOT = BASE_DIR / "uploads"
    MEDIA_URL = "uploads/"

# --- Fila (Celery) ----------------------------------------------------------

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
# Toda chamada externa é task; falha de rede não pode travar worker indefinidamente.
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540

# --- Integrações (AGENTS.md §5) ---------------------------------------------

PROVEDOR_IA = env("PROVEDOR_IA")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODELO = env("GEMINI_MODELO", default="gemini-2.5-flash-lite")
IA_LOCAL_URL = env("IA_LOCAL_URL", default="")

PROVEDOR_COMPLIANCE = env("PROVEDOR_COMPLIANCE")
TRILLIA_API_TOKEN = env("TRILLIA_API_TOKEN", default="")
TRILLIA_BASE_URL = env("TRILLIA_BASE_URL", default="")

# --- Segurança --------------------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
    CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Log --------------------------------------------------------------------
# Nunca logue conteúdo de documento, CPF completo ou token (AGENTS.md §6).

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "padrao"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
    },
}
