from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from core.ocr.inputs import OCRPageResultInput


@strawberry.input()
class CreatePageInput:
    image: scalars.FileLike
    index: int
    document: strawberry.ID
    ocr_result: OCRPageResultInput
    content: str | None = None


def create_page(
    info: Info,
    input: CreatePageInput,
) -> types.Page:
    page = models.Page.objects.create(index=input.index, document_id=input.document, image=models.BigFileStore.objects.get(id=input.image), ocr_result=strawberry.asdict(input.ocr_result), content=input.content)

    return page
