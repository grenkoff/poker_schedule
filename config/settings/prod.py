"""Production settings (Railway)."""

from .base import *
from .base import MIDDLEWARE, env

DEBUG = False

# Whitenoise serves hashed/compressed static files in prod; dev uses
# Django's built-in staticfiles view so the middleware adds nothing there.
MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]

# Railway provides RAILWAY_PUBLIC_DOMAIN; we also allow a comma-separated list
# via DJANGO_ALLOWED_HOSTS for custom domains.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
_railway_domain = env("RAILWAY_PUBLIC_DOMAIN", default="")
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)

CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if host and host != "*"]

# In production the manifest storage fingerprints static assets and raises
# if a referenced file is missing — much stricter than dev, which just
# serves files off disk with no manifest.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days, bumped later after verification
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Email — plugged in once SMTP provider is wired up. Default to console so a
# misconfigured prod still logs rather than crashes on sendmail.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
