"""Test settings: a real postgres and a real object store, both from
``tests/integration/docker-compose.yaml``.

Neither host port is pinned. Docker assigns them per run and ``tests/conftest.py``
asks the running stack which it got, then writes them in here -- ``DATABASES`` via
``django_db_modify_db_settings`` and ``AWS_S3_ENDPOINT_URL`` via the ``s3_endpoint``
fixture. The placeholders below only matter if you point the suite at a stack you
started by hand.
"""

from .settings import *  # noqa
from .settings import DATABASES, AUTHENTIKATE
import logging

DATABASES["default"] = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "testdb",
    "USER": "test",
    "PASSWORD": "test",
    "HOST": "localhost",
    # Placeholder -- conftest overwrites this with the port docker actually assigned.
    "PORT": "5432",
}

# Django forces DEBUG=False under the test runner, and authentikate 3.0 refuses static
# tokens when DEBUG is False. These are deliberate test fixtures, so opt in explicitly.
AUTHENTIKATE = {
    **AUTHENTIKATE,
    "allow_static_tokens_in_production": True,
    "static_tokens": {"test": {"sub": "1"}},
}

# --- object storage -------------------------------------------------------------
# The credentials are the scoped user `initc` provisions (see
# tests/integration/configs/rustfs.yaml), not the RustFS root pair: the suite should
# exercise the same kind of identity the service uses in production.
AWS_ACCESS_KEY_ID = "dokuments_access_key"
AWS_SECRET_ACCESS_KEY = "dokuments_secret_key"
AWS_S3_REGION_NAME = "us-east-1"
# Placeholder -- the `s3_endpoint` fixture overwrites this with the mapped port.
AWS_S3_ENDPOINT_URL = "http://localhost:9000"
# RustFS is served over plain http in the test stack.
AWS_S3_USE_SSL = False
AWS_S3_SECURE_URLS = False
FILE_BUCKET = "files"
MEDIA_BUCKET = "media"
AWS_STORAGE_BUCKET_NAME = "media"


# Disable migrations for faster tests: the schema is built with run-syncdb.
class DisableMigrations:
    """Disable migrations during testing for faster test execution."""

    def __contains__(self, item: str) -> bool:
        return True

    def __getitem__(self, item: str) -> None:
        return None


MIGRATION_MODULES = DisableMigrations()

logging.disable(logging.CRITICAL)

# Redis is in the stack but the suite does not need a broker.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# The presigned-URL code caches per (bucket, key, host); an in-process cache keeps
# tests independent of a shared redis.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
