from pydantic import BaseModel
import strawberry
import strawberry_django
from strawberry import auto
from typing import List, Optional, Annotated, Union, cast
import strawberry_django
from core import models, scalars, filters, enums
from django.contrib.auth import get_user_model
from kante.types import Info
import datetime
from asgiref.sync import sync_to_async
from itertools import chain
from enum import Enum
from core.datalayer import get_current_datalayer
from core.render.objects import models as rmodels
from strawberry.experimental import pydantic
from typing import Union
from strawberry import LazyType
from authentikate.strawberry.types import Client, User
from koherent.strawberry.types import ProvenanceEntry
from core.ocr.object import OCRPageResult


@strawberry.type(description="Temporary Credentials for a file upload that can be used by a Client (e.g. in a python datalayer)")
class Credentials:
    """Temporary Credentials for a a file upload."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    datalayer: str
    bucket: str
    key: str
    store: str


@strawberry.type(description="Temporary Credentials for a file upload that can be used by a Client (e.g. in a python datalayer)")
class PresignedPostCredentials:
    """Temporary Credentials for a a file upload."""

    key: str
    x_amz_algorithm: str
    x_amz_credential: str
    x_amz_date: str
    x_amz_signature: str
    policy: str
    datalayer: str
    bucket: str
    store: str


@strawberry.type(description="Temporary Credentials for a file download that can be used by a Client (e.g. in a python datalayer)")
class AccessCredentials:
    """Temporary Credentials for a a file upload."""

    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str


@strawberry.enum
class ViewKind(str, Enum):
    """The kind of view.

    Views can be of different kinds. For example, a view can be a label view
    that will map a labeleling agent (e.g. an antibody) to a specific image channel.

    Depending on the kind of view, different fields will be available.

    """

    TIMEPOINT = "timepoint_views"


@strawberry_django.type(models.BigFileStore)
class BigFileStore:
    id: auto
    path: str
    bucket: str
    key: str

    @strawberry.field()
    def presigned_url(self, info: Info) -> str:
        datalayer = get_current_datalayer()
        return cast(models.BigFileStore, self).get_presigned_url(info, datalayer=datalayer)


@strawberry_django.type(models.MediaStore)
class MediaStore:
    id: auto
    path: str
    bucket: str
    key: str

    @strawberry_django.field()
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(info, datalayer=datalayer, host=host)


@strawberry_django.type(models.File, filters=filters.FileFilter, pagination=True)
class File:
    id: auto
    name: auto
    store: BigFileStore
    documents: list["Document"] = strawberry_django.field(
        description="The documents that reference this file",
    )


@strawberry_django.type(models.Dataset, filters=filters.DatasetFilter, pagination=True)
class Dataset:
    id: auto
    name: auto
    description: auto
    creator: User
    created_at: datetime.datetime
    updated_at: datetime.datetime
    pinned: bool = strawberry.field(description="Whether the dataset is pinned.")


@strawberry_django.type(models.Document, filters=filters.DocumentFilter, pagination=True)
class Document:
    """Document type."""

    id: strawberry.ID
    file: "File"
    title: str
    page_count: Optional[int]
    ocr_engine: str
    processed_at: Optional[str]
    pages: list["Page"]


@strawberry_django.type(models.Page, filters=filters.PageFilter, pagination=True)
class Page:
    id: strawberry.ID
    document: "Document"
    index: int
    image: BigFileStore
    content: str = strawberry.field(description="The content of the page as a flat string.")

    @strawberry.field
    def ocr_result(self) -> OCRPageResult:
        """Returns the OCR result for the page."""
        if self.ocr_result:
            return OCRPageResult(**self.ocr_result)
        return None
