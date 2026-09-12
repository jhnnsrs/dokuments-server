"""The S3 surface, exercised against the real object store in the compose stack.

Everything here goes over the wire to RustFS. That is the point: the code under test
generates presigned POST forms, presigned GET URLs and STS session credentials, and
those are precisely the parts whose correctness lives in the *server's* agreement with
the signature -- a mock that reimplements S3 can only agree with itself.
"""

import io
import uuid

import pytest
import requests
from django.conf import settings

from core import models
from core.datalayer import get_current_datalayer
from core.mutations.file import (
    RequestFileAccessInput,
    RequestFileUploadInput,
    request_file_access,
    request_file_upload,
    request_file_upload_presigned,
)


def test_initc_provisioned_the_buckets(s3_client):
    """`initc` ran and created what settings_test points at."""
    names = {b["Name"] for b in s3_client.list_buckets()["Buckets"]}
    assert settings.FILE_BUCKET in names
    assert settings.MEDIA_BUCKET in names


def test_datalayer_client_reaches_the_running_store(s3_client):
    """The service's own Datalayer talks to the same store the fixture does."""
    key = f"probe/{uuid.uuid4().hex}"
    s3_client.put_object(Bucket=settings.MEDIA_BUCKET, Key=key, Body=b"probe")

    s3 = get_current_datalayer().s3
    assert s3.get_object(Bucket=settings.MEDIA_BUCKET, Key=key)["Body"].read() == b"probe"


@pytest.mark.django_db
def test_presigned_post_upload_round_trip(s3_client):
    """`request_file_upload_presigned` mints a POST form that the store accepts.

    The signature is verified by RustFS, not by us: a wrong policy, credential or
    signature field comes back as a 4xx here. This is the check moto could not make.
    """
    creds = request_file_upload_presigned(
        None,  # info is unused on this path
        RequestFileUploadInput(file_name="report.pdf", datalayer="default"),
    )

    body = b"%PDF-1.4 not really a pdf, but bytes are bytes"
    response = requests.post(
        settings.AWS_S3_ENDPOINT_URL + f"/{creds.bucket}",
        data={
            "key": creds.key,
            "x-amz-algorithm": creds.x_amz_algorithm,
            "x-amz-credential": creds.x_amz_credential,
            "x-amz-date": creds.x_amz_date,
            "x-amz-signature": creds.x_amz_signature,
            "policy": creds.policy,
        },
        files={"file": ("report.pdf", body)},
        timeout=30,
    )
    assert response.status_code in (200, 204), response.text

    stored = s3_client.get_object(Bucket=creds.bucket, Key=creds.key)["Body"].read()
    assert stored == body

    store = models.BigFileStore.objects.get(id=creds.store)
    assert store.key == creds.key
    assert store.bucket == settings.FILE_BUCKET
    assert store.file_name == "report.pdf"
    assert store.mime_type == "application/pdf"


@pytest.mark.django_db
def test_bigfilestore_presigned_url_downloads_the_bytes(s3_client):
    """`BigFileStore.get_presigned_url` produces a URL the store honours."""
    key = uuid.uuid4().hex
    body = b"downloadable content"
    s3_client.put_object(Bucket=settings.FILE_BUCKET, Key=key, Body=body)

    store = models.BigFileStore.objects.create(
        path=f"s3://{settings.FILE_BUCKET}/{key}",
        key=key,
        bucket=settings.FILE_BUCKET,
        file_name="thing.txt",
        mime_type="text/plain",
    )

    # `host=None` makes get_presigned_url strip the endpoint prefix and return a
    # relative URL, so put it back to address the running store.
    relative = store.get_presigned_url(None, datalayer=get_current_datalayer())
    response = requests.get(settings.AWS_S3_ENDPOINT_URL + relative, timeout=30)
    assert response.status_code == 200, response.text
    assert response.content == body
    # The download disposition the resolver sets is what makes a browser save it.
    assert 'filename="thing.txt"' in response.headers.get("content-disposition", "")


@pytest.mark.django_db
def test_mediastore_put_file_uploads(s3_client):
    """`MediaStore.put_file` pushes a file object into the store."""
    key = uuid.uuid4().hex
    store = models.MediaStore.objects.create(
        path=f"s3://{settings.MEDIA_BUCKET}/{key}", key=key, bucket=settings.MEDIA_BUCKET
    )

    store.put_file(get_current_datalayer(), io.BytesIO(b"an image, allegedly"))

    assert s3_client.get_object(Bucket=settings.MEDIA_BUCKET, Key=key)["Body"].read() == b"an image, allegedly"


@pytest.mark.django_db
def test_sts_scoped_credentials_can_read_the_object(s3_client):
    """`request_file_access` returns STS credentials the store actually accepts.

    Exercises the AssumeRole branch end to end: mint a session, then use it as a
    separate client. A mock would hand back plausible-looking strings that no server
    ever validates.
    """
    import boto3

    key = uuid.uuid4().hex
    s3_client.put_object(Bucket=settings.FILE_BUCKET, Key=key, Body=b"scoped read")
    store = models.BigFileStore.objects.create(
        path=f"s3://{settings.FILE_BUCKET}/{key}",
        key=key,
        bucket=settings.FILE_BUCKET,
        file_name="scoped.txt",
        mime_type="text/plain",
    )

    creds = request_file_access(None, RequestFileAccessInput(store=str(store.id), duration=900))

    scoped = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.session_token,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    assert scoped.get_object(Bucket=creds.bucket, Key=creds.key)["Body"].read() == b"scoped read"


@pytest.mark.django_db
def test_request_file_upload_returns_usable_session(s3_client):
    """The non-presigned upload path: STS credentials that can write the key."""
    import boto3

    creds = request_file_upload(
        None, RequestFileUploadInput(file_name="notes.txt", datalayer="default")
    )

    scoped = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.session_token,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    scoped.put_object(Bucket=creds.bucket, Key=creds.key, Body=b"written with a session")

    assert s3_client.get_object(Bucket=creds.bucket, Key=creds.key)["Body"].read() == b"written with a session"
    assert models.BigFileStore.objects.filter(id=creds.store).exists()
