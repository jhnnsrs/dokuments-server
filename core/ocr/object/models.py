from datetime import datetime
from typing import List, Optional, Tuple

import strawberry
from pydantic import BaseModel
from strawberry.experimental import pydantic as strawberry_pydantic


class OCRTextLineModel(BaseModel):
    text: str
    score: float
    angle: float
    bbox: List[Tuple[int, int]]


class OCRPageResultModel(BaseModel):
    lines: List[OCRTextLineModel]
    angle: float


@strawberry_pydantic.type(OCRTextLineModel)
class OCRTextLine:
    text: str
    score: float
    angle: float
    bbox: List[Tuple[int, int]]


@strawberry_pydantic.type(OCRPageResultModel)
class OCRPageResult:
    lines: List[OCRTextLine] = strawberry.field(description="List of recognized text lines")
    angle: float = strawberry.field(description="Estimated rotation angle of the page")
