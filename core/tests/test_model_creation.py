"""Model-level smoke tests against a real postgres.

Previously this asserted a shape the models no longer have -- it created a
`Dataset` with no `organization` (which is non-null) and a `Document` with
`dataset=`/`creator=` kwargs that `Document` does not define (it hangs off a
`File`). It had never run: collection died earlier on a missing `moto` import, so
nothing flagged the drift.
"""

from authentikate.models import Organization
from django.contrib.auth import get_user_model

from core.models import BigFileStore, Dataset, Document, File


def test_create_dataset_file_and_document(db):
    """A Dataset -> File -> Document chain persists with its relations intact."""
    user = get_user_model().objects.create_user(username="testuser", password="123456789")
    org = Organization.objects.create(slug="testorg")

    dataset = Dataset.objects.create(
        name="Test Dataset",
        description="This is a test dataset",
        creator=user,
        organization=org,
    )

    store = BigFileStore.objects.create(
        path="s3://files/abc", key="abc", bucket="files", file_name="a.pdf", mime_type="application/pdf"
    )
    file = File.objects.create(
        name="a.pdf", dataset=dataset, store=store, creator=user, organization=org
    )
    document = Document.objects.create(file=file, title="Scanned report")

    assert document.pk is not None
    assert document.file == file
    assert file.dataset == dataset
    assert file.store == store
    # The reverse accessors the resolvers rely on.
    assert list(dataset.files.all()) == [file]
    assert list(file.documents.all()) == [document]


def test_dataset_requires_an_organization(db):
    """`Dataset.organization` is non-null -- tenancy is not optional."""
    import pytest
    from django.db.utils import IntegrityError

    user = get_user_model().objects.create_user(username="orphan", password="123456789")
    with pytest.raises(IntegrityError):
        Dataset.objects.create(name="No org", creator=user)
