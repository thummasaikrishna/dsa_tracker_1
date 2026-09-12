"""
Django settings for the DSA Tracker backend.

NOTE ON AUTH:
The app retains its Django REST Framework SimpleJWT sessions for the existing
username/password login. Google OAuth is performed by Supabase Auth in the
browser; Django validates the returned Supabase access token and then issues
the same application JWTs. Authorization remains based solely on the local
Profile.role field, never provider or client-side metadata.
"""

from datetime import timedelta
import os
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

ENVIRONMENT = config("DJANGO_ENV", default="development").strip().lower()
if ENVIRONMENT not in {"development", "production"}:
    raise ImproperlyConfigured("DJANGO_ENV must be either 'development' or 'production'.")


def _validate_production_settings(debug, secret_key):
    if debug:
        raise ImproperlyConfigured("DEBUG must be False when DJANGO_ENV=production.")
    if not secret_key:
        raise ImproperlyConfigured("SECRET_KEY is required when DJANGO_ENV=production.")


if ENVIRONMENT == "production":
    # Production must deliberately opt in to a non-debug, environment-provided secret.
    DEBUG = config("DEBUG", cast=bool)
    SECRET_KEY = config("SECRET_KEY", default="")
    _validate_production_settings(DEBUG, SECRET_KEY)
else:
    DEBUG = config("DEBUG", default=True, cast=bool)
    SECRET_KEY = config("SECRET_KEY", default="django-insecure-local-development-only")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "core.apps.CoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dsatracker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "dsatracker.wsgi.application"

# Browser E2E runs are deliberately isolated from the developer database.
# The Playwright bootstrap sets this flag before Django starts.
E2E_TEST_MODE = os.environ.get("E2E_TEST_MODE") == "1"
DATABASE_URL = config("DATABASE_URL", default="")

# Supabase Auth is used only to verify a Google OAuth access token before
# issuing this application's existing Django JWTs. Both values are public
# project configuration; never expose a service-role key in this application.
SUPABASE_URL = config("SUPABASE_URL", default="").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = config("SUPABASE_PUBLISHABLE_KEY", default="")

if E2E_TEST_MODE:
    if not DEBUG:
        raise ImproperlyConfigured(
            "E2E_TEST_MODE is local-test-only and cannot be enabled when DEBUG=False."
        )
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "e2e.sqlite3"}}
elif DATABASE_URL:
    # Supabase PostgreSQL. Use the connection string from Supabase's Connect
    # panel (including sslmode=require); no credentials are stored in source.
    database_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
    if database_config["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured(
            "DATABASE_URL must be a PostgreSQL connection URL for Supabase; "
            "SQLite is never permitted outside local development."
        )
    DATABASES = {
        "default": database_config
    }
    if not DEBUG:
        DATABASES["default"].setdefault("OPTIONS", {}).setdefault("sslmode", "require")
elif DEBUG:
    # Local-only convenience fallback. Production must always set DATABASE_URL.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("DATABASE_URL is required when DEBUG=False. Production cannot use SQLite.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# REST Framework / JWT / CORS configuration
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.TrackerJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Authentication endpoints opt into these scopes individually. Normal API
    # operations intentionally remain unthrottled by this security control.
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "5/min",
        "auth_register": "5/hour",
        "auth_refresh": "10/min",
        "auth_google": "10/min",
        "auth_logout": "10/min",
    },
    "DEFAULT_FILTER_BACKENDS": (
        "core.filters.StrictDjangoFilterBackend",
        "core.filters.BoundedSearchFilter",
        "core.filters.StrictOrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.FlexiblePagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "core.exception_handler.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ALGORITHM": "HS256",
    "CHECK_REVOKE_TOKEN": True,
    "REVOKE_TOKEN_CLAIM": "hash_password",
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = False


<<<<<<< HEAD
def _is_valid_cors_origin(origin):
=======
def _valid_origin(origin):
    parsed = urlsplit(origin)
    return (
        origin == origin.strip()
        and "*" not in origin
        and parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


<<<<<<< HEAD
def _validate_origins(origins, name, production=False, required=False):
    if required and not origins:
        raise ImproperlyConfigured(
            f"{name} is required when DJANGO_ENV=production."
        )

    if any(not _valid_origin(origin) for origin in origins):
        raise ImproperlyConfigured(
            f"{name} must contain explicit HTTP(S) origins only."
        )

    if production and any(
        urlsplit(origin).scheme != "https" for origin in origins
    ):
        raise ImproperlyConfigured(
            f"{name} must use HTTPS origins when DJANGO_ENV=production."
        )


_validate_origins(
    CORS_ALLOWED_ORIGINS,
    "CORS_ALLOWED_ORIGINS",
    ENVIRONMENT == "production",
    required=ENVIRONMENT == "production",
)

_validate_origins(
    CSRF_TRUSTED_ORIGINS,
    "CSRF_TRUSTED_ORIGINS",
    ENVIRONMENT == "production",
)
    if required and not origins:
        raise ImproperlyConfigured(f"{name} is required when DJANGO_ENV=production.")
    if any(not _valid_origin(origin) for origin in origins):
        raise ImproperlyConfigured(f"{name} must contain explicit HTTP(S) origins only.")
    if production and any(urlsplit(origin).scheme != "https" for origin in origins):
        raise ImproperlyConfigured(f"{name} must use HTTPS origins when DJANGO_ENV=production.")


_validate_origins(CORS_ALLOWED_ORIGINS, "CORS_ALLOWED_ORIGINS", ENVIRONMENT == "production", required=ENVIRONMENT == "production")
_validate_origins(CSRF_TRUSTED_ORIGINS, "CSRF_TRUSTED_ORIGINS", ENVIRONMENT == "production")
>>>>>>> db3c86d (Implement security phase 3 validation)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

# Sandboxed code execution (never runs student code inside Django).
# Prefer Judge0 when JUDGE0_BASE_URL is set. Self-hosted Piston is used when
# PISTON_BASE_URL points at a non-public instance. Otherwise Wandbox is used.
JUDGE0_BASE_URL = config("JUDGE0_BASE_URL", default="")
JUDGE0_API_KEY = config("JUDGE0_API_KEY", default="")
JUDGE0_API_HOST = config("JUDGE0_API_HOST", default="")
PISTON_BASE_URL = config("PISTON_BASE_URL", default="")
WANDBOX_BASE_URL = config("WANDBOX_BASE_URL", default="https://wandbox.org/api")
# Never call an execution provider from E2E.  The deterministic executor below
# is enabled only by the isolated Playwright process.
E2E_MOCK_EXECUTOR = E2E_TEST_MODE

# OpenRouter — DSA Problem Analysis Agent (keys never leave the backend)
OPENROUTER_API_URL = config("OPENROUTER_API_URL", default="https://openrouter.ai/api/v1/chat/completions")
# Key 1 is primary.  Slots 2-5 are bounded sequential fallbacks; each is
# attempted once for provider/network/schema failures and no credential is
# ever returned to the frontend or logged.
OPENROUTER_API_KEYS = [config(f"OPENROUTER_API_KEY_{index}", default="") for index in range(1, 6)]
OPENROUTER_MODEL = config("OPENROUTER_MODEL", default="openai/gpt-oss-20b")
OPENROUTER_TIMEOUT = config("OPENROUTER_TIMEOUT", default=45, cast=int)
OPENROUTER_TEMPERATURE = config("OPENROUTER_TEMPERATURE", default=0.0, cast=float)
OPENROUTER_SITE_URL = config("OPENROUTER_SITE_URL", default="http://localhost:8000")
OPENROUTER_APP_NAME = config("OPENROUTER_APP_NAME", default="DSA Tracker")
