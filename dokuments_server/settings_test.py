from .settings import *  # noqa
from .settings import DATABASES, AUTHENTIKATE

DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
# Django forces DEBUG=False under the test runner, and authentikate 3.0 refuses static
# tokens when DEBUG is False. These are deliberate test fixtures, so opt in explicitly.
AUTHENTIKATE = {**AUTHENTIKATE, "allow_static_tokens_in_production": True, "static_tokens": {"test": {"sub": "1"}}}
