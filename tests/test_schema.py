"""The GraphQL schema over a real database and a real object store.

Replaces the previous tests/test.py, which queried `core.models.Image` and a
`dataset { name }` field on File -- neither exists in dokuments (Image is mikro's
model, and Dataset is not exposed in this schema at all). It had been copied across
from mikro and never run.

Queries go through `await schema.execute(...)`, not `execute_sync`: the koherent
provenance extension's `on_operation` hook is async, and a sync execution fails with
"SchemaExtension hook ... failed to complete synchronously".
"""

import uuid

import pytest
import requests
from asgiref.sync import sync_to_async
from django.conf import settings

from core import models
from dokuments_server.schema import schema

FILE_QUERY = """
    query File($id: ID!) {
        file(id: $id) {
            id
            name
            store { id key bucket path }
        }
    }
"""


@pytest.fixture
def make_file(authenticated_context):
    """Create a File backed by a BigFileStore, returning (file, store)."""

    @sync_to_async
    def _make(key: str, body: bytes | None = None):
        store = models.BigFileStore.objects.create(
            path=f"s3://{settings.FILE_BUCKET}/{key}",
            key=key,
            bucket=settings.FILE_BUCKET,
            file_name="a.pdf",
            mime_type="application/pdf",
        )
        file = models.File.objects.create(
            name="a.pdf",
            store=store,
            creator=authenticated_context.request.user,
            organization=authenticated_context.request.organization,
        )
        return file, store

    return _make


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_file_query_resolves_its_store(authenticated_context, make_file):
    """A File created through the ORM is readable through the schema."""
    key = uuid.uuid4().hex
    file, store = await make_file(key)

    result = await schema.execute(
        FILE_QUERY, variable_values={"id": str(file.id)}, context_value=authenticated_context
    )

    assert not result.errors, result.errors
    assert result.data["file"]["name"] == "a.pdf"
    assert result.data["file"]["store"]["key"] == key
    assert result.data["file"]["store"]["bucket"] == settings.FILE_BUCKET


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_presigned_url_resolver_returns_a_working_url(
    authenticated_context, make_file, s3_client
):
    """`BigFileStore.presignedUrl` is resolved by signing against the live store.

    This is the whole schema-to-storage path in one assertion: the resolver reaches
    the datalayer, the datalayer signs against RustFS, and RustFS honours the
    signature. Against a mock the URL would be unverifiable.
    """
    key = uuid.uuid4().hex
    body = b"the actual bytes behind the presigned url"
    await sync_to_async(s3_client.put_object)(
        Bucket=settings.FILE_BUCKET, Key=key, Body=body
    )
    file, _ = await make_file(key)

    result = await schema.execute(
        """
        query File($id: ID!) {
            file(id: $id) { store { presignedUrl } }
        }
        """,
        variable_values={"id": str(file.id)},
        context_value=authenticated_context,
    )
    assert not result.errors, result.errors

    # The resolver calls get_presigned_url with host=None, which strips the endpoint
    # prefix and yields a relative URL; put it back to address the running store.
    relative = result.data["file"]["store"]["presignedUrl"]
    response = await sync_to_async(requests.get)(
        settings.AWS_S3_ENDPOINT_URL + relative, timeout=30
    )
    assert response.status_code == 200, response.text
    assert response.content == body


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_document_and_pages_traverse_back_to_the_file(
    authenticated_context, make_file
):
    """Document -> pages -> image walks the relations the OCR pipeline writes."""
    file, store = await make_file(uuid.uuid4().hex)

    @sync_to_async
    def _make_doc():
        document = models.Document.objects.create(file=file, title="Scanned report")
        models.Page.objects.create(document=document, index=0, content="page one", image=store)
        models.Page.objects.create(document=document, index=1, content="page two", image=store)
        return document

    document = await _make_doc()

    result = await schema.execute(
        """
        query Document($id: ID!) {
            document(id: $id) {
                title
                file { name }
                pages { index content image { key } }
            }
        }
        """,
        variable_values={"id": str(document.id)},
        context_value=authenticated_context,
    )

    assert not result.errors, result.errors
    doc = result.data["document"]
    assert doc["title"] == "Scanned report"
    assert doc["file"]["name"] == "a.pdf"
    assert [p["index"] for p in doc["pages"]] == [0, 1]
    assert [p["content"] for p in doc["pages"]] == ["page one", "page two"]
    assert doc["pages"][0]["image"]["key"] == store.key
