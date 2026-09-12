"""Integration fixtures: a real postgres and a real object store via dokker.

There are no mocks here. The S3 code under test generates presigned URLs and calls
``upload_fileobj``; a mock that reimplements S3 semantics only ever proves the mock
agrees with itself, so the suite talks to an actual RustFS container.
"""

import os
import time

import boto3
import psycopg
import pytest
from django.contrib.contenttypes.management import create_contenttypes
from django.db.models.signals import post_migrate
from dokker import PortNotFoundError, testing

COMPOSE = os.path.join(os.path.dirname(__file__), "integration", "docker-compose.yaml")

#: Must match tests/integration/configs/rustfs.yaml and settings_test.
ACCESS_KEY = "dokuments_access_key"
SECRET_KEY = "dokuments_secret_key"
BUCKETS = ("media", "files")


@pytest.fixture(scope="session")
def backend_stack():
    """Bring up the stack and yield the host ports docker assigned.

    Neither port is fixed: the compose file publishes 5432 and 9000 with no host
    port, so docker picks free ones per run and this asks the running stack which it
    got. That is the whole isolation story -- dokker mints a unique
    ``dokker-test-<uuid>`` project per run, but a pinned host port defeats it, since
    two projects with different names still cannot both bind one host port.

    Returns a ``(db_port, s3_port)`` tuple; both are needed before Django touches
    either service, so they are resolved together.
    """
    with testing(COMPOSE) as e:
        e.up()

        # Ask the running stack, not the compose file: `get_port` shells out to
        # `docker compose port`, the only thing that knows what docker picked.
        # Resolved inside the retry loop because `up()` is not called with `wait`
        # and prints nothing for a container that is not up yet, which dokker
        # turns into PortNotFoundError.
        db_port = s3_port = None
        deadline = time.monotonic() + 60
        while True:
            try:
                if db_port is None:
                    db_port = e.get_port("db", 5432)
                if s3_port is None:
                    s3_port = e.get_port("rustfs", 9000)
                with psycopg.connect(
                    dbname="testdb",
                    user="test",
                    password="test",
                    host="localhost",
                    port=db_port,
                    connect_timeout=1,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                break
            except (psycopg.OperationalError, PortNotFoundError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)

        # `initc` only waits for rustfs's container to *start*, not to accept
        # connections, so it can race the server and exit before provisioning. Wait
        # for /health, then run it explicitly and let a failure surface here rather
        # than as a confusing NoSuchBucket later.
        _wait_for_rustfs(s3_port, deadline=time.monotonic() + 60)
        e.run("initc", command="python init.py")
        _wait_for_buckets(s3_port, deadline=time.monotonic() + 30)

        yield db_port, s3_port


def _wait_for_rustfs(port: int, deadline: float) -> None:
    import urllib.error
    import urllib.request

    while True:
        try:
            # RustFS's native health endpoint (it also serves MinIO's
            # /minio/health/live as a compat shim; prefer its own).
            if urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2).status == 200:
                return
        except (urllib.error.URLError, OSError, urllib.error.HTTPError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"rustfs on port {port} never became healthy")
        time.sleep(0.2)


def _wait_for_buckets(port: int, deadline: float) -> None:
    client = _client(port)
    while True:
        try:
            names = {b["Name"] for b in client.list_buckets()["Buckets"]}
            if set(BUCKETS) <= names:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"initc did not provision {BUCKETS} (port {port})")
        time.sleep(0.2)


def _client(port: int):
    return boto3.client(
        "s3",
        endpoint_url=f"http://localhost:{port}",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="us-east-1",
    )


@pytest.fixture(scope="session")
def django_db_modify_db_settings(backend_stack):
    """Point Django at the postgres port the stack came up on.

    pytest-django calls this before creating the test database, which is the only
    window in which the port can be set: ``settings_test`` is imported long before
    any fixture runs, so it cannot know a port docker had not assigned yet.
    """
    from django.conf import settings

    db_port, _ = backend_stack
    settings.DATABASES["default"]["PORT"] = str(db_port)
    yield


@pytest.fixture(scope="session", autouse=True)
def s3_endpoint(backend_stack):
    """Point the service's datalayer at the object store's mapped port.

    ``settings.AWS_S3_ENDPOINT_URL`` is what ``core.datalayer.Datalayer`` builds its
    boto3 client from, and ``get_current_datalayer()`` constructs a fresh Datalayer
    per call, so overwriting the setting is enough -- no cached client to invalidate.
    Autouse because the presigned-URL code also rewrites this prefix out of its
    output, so a stale value silently corrupts URLs rather than failing.
    """
    from django.conf import settings

    _, s3_port = backend_stack
    settings.AWS_S3_ENDPOINT_URL = f"http://localhost:{s3_port}"
    yield settings.AWS_S3_ENDPOINT_URL


@pytest.fixture
def s3_client(backend_stack, s3_endpoint):
    """boto3 client for the real object store, as the provisioned scoped user."""
    _, s3_port = backend_stack
    return _client(s3_port)


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    # Every transaction=True test teardown flushes the DB and re-fires post_migrate,
    # which rebuilds all contenttypes and permissions from the model registry. The
    # rows never change between tests, so snapshot them once and swap the rebuild for
    # a bulk re-insert with the original pks (keeps guardian FKs and the ContentType
    # pk cache valid).
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    with django_db_blocker.unblock():
        contenttypes = list(ContentType.objects.all())
        permissions = list(Permission.objects.all())

    post_migrate.disconnect(dispatch_uid="django.contrib.auth.management.create_permissions")
    post_migrate.disconnect(create_contenttypes)

    def restore(sender, **kwargs):
        if getattr(sender, "label", None) != "contenttypes":
            return
        ContentType.objects.bulk_create(contenttypes, ignore_conflicts=True)
        Permission.objects.bulk_create(permissions, ignore_conflicts=True)

    post_migrate.connect(restore, dispatch_uid="tests.restore_contenttypes_and_permissions")
    yield

    # Async tests run sync ORM code in asgiref's executor threads, whose connections
    # outlive the tests and block dropping the test database.
    from django.db import connections

    with django_db_blocker.unblock():
        with connections["default"].cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        connections.close_all()


@pytest.fixture(scope="function")
def authenticated_context(db, backend_stack):
    """A context whose identity matches what the static "test" token resolves to.

    The schema's authentikate extension authenticates as that identity at resolve
    time, so an ad-hoc user here would leave organization-scoped queries seeing no
    data. dokuments' Dataset and File both carry a non-null organization, so the
    membership matters.
    """
    from authentikate.models import Client, Membership, Organization, User
    from kante.context import HttpContext, UniversalRequest
    from strawberry.http.temporal_response import TemporalResponse

    user, _ = User.objects.get_or_create(
        sub="1", iss="static_issuer", defaults={"username": "static_issuer_1"}
    )
    client, _ = Client.objects.get_or_create(client_id="dokuments-test")
    org, _ = Organization.objects.get_or_create(slug="static_org")
    membership, _ = Membership.objects.get_or_create(user=user, organization=org)

    request = UniversalRequest(
        _extensions={"token": "test"},
        _client=client,  # type: ignore[arg-type]
        _user=user,  # type: ignore[arg-type]
        _organization=org,  # type: ignore[arg-type]
    )
    request.set_membership(membership)  # type: ignore[arg-type]

    return HttpContext(
        request=request,
        response=TemporalResponse(),
        headers={"Authorization": "Bearer test"},
        type="http",
    )
