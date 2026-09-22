from kante.types import Info
from dokuments_server.logs import QuietErrorsSchema
from typing import AsyncGenerator, List
import strawberry

from core.datalayer import DatalayerExtension
from strawberry import ID as StrawberryID
from typing import Any, Type
from core import types, models
from core import mutations
from core import queries
from core import subscriptions
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from core.render.objects import types as render_types
from typing import Annotated
from authentikate.strawberry.extension import AuthentikateExtension
from strawberry_django.optimizer import DjangoOptimizerExtension


ID = Annotated[StrawberryID, strawberry.argument(description="The unique identifier of an object")]


@strawberry.type
class Query:
    files: list[types.File] = strawberry_django.field()
    documents: list[types.Document] = strawberry_django.field()
    pages: list[types.Page] = strawberry_django.field()

    @strawberry_django.field(permission_classes=[])
    def file(self, info: Info, id: ID) -> types.File:
        return models.File.objects.get(id=id)

    @strawberry_django.field(permission_classes=[])
    def document(self, info: Info, id: ID) -> types.Document:
        return models.Document.objects.get(id=id)

    @strawberry_django.field(permission_classes=[])
    def page(self, info: Info, id: ID) -> types.Page:
        return models.Page.objects.get(id=id)


@strawberry.type
class Mutation:
    # File
    request_file_upload: types.Credentials = strawberry_django.mutation(resolver=mutations.request_file_upload, description="Request credentials to upload a new file")
    request_file_upload_presigned: types.PresignedPostCredentials = strawberry_django.mutation(resolver=mutations.request_file_upload_presigned, description="Request presigned credentials for file upload")
    request_file_access: types.AccessCredentials = strawberry_django.mutation(resolver=mutations.request_file_access, description="Request credentials to access a file")
    from_file_like = strawberry_django.mutation(resolver=mutations.from_file_like, description="Create a file from file-like data")
    delete_file = strawberry_django.mutation(resolver=mutations.delete_file, description="Delete an existing file")

    # Experiment
    create_document = strawberry_django.mutation(resolver=mutations.create_document, description="Create a new document")

    # Page
    create_page = strawberry_django.mutation(resolver=mutations.create_page, description="Create a new page in a document")


@strawberry.type
class Subscription:
    """The root subscription type"""

    files = strawberry.subscription(resolver=subscriptions.files, description="Subscribe to real-time file updates")


class Schema(QuietErrorsSchema, strawberry.Schema):
    """strawberry.Schema, logging expected resolver errors as one line and bugs with a traceback (see logs.py)."""


schema = Schema(
    query=Query,
    subscription=Subscription,
    mutation=Mutation,
    extensions=[
        KoherentExtension,
        AuthentikateExtension,
        DjangoOptimizerExtension,
        DatalayerExtension,
    ],
    types=[],
)
