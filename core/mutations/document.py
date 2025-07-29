from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from pydantic import BaseModel
import hashlib
import json


def hash_model(config) -> str:
    # Convert to dict, dump as sorted JSON string
    model_json = json.dumps(strawberry.asdict(config), sort_keys=True)
    return hashlib.sha256(model_json.encode("utf-8")).hexdigest()


@strawberry.input()
class CreateDocumentInput:
    file: strawberry.ID | None = None
    title: str


def create_document(
    info: Info,
    input: CreateDocumentInput,
) -> types.Document:
    document = models.Document.objects.create(
        title=input.title,
        file_id=input.file,
    )

    return document
