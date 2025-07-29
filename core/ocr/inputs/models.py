from typing import List, Optional, Tuple
from pydantic import BaseModel
from strawberry.experimental import pydantic as strawberry_pydantic
import strawberry


class OCRTextLineModel(BaseModel):
    text: str  # Recognized text string
    score: float  # Confidence score of recognition
    angle: float  # Detected rotation angle of the text line
    bbox: List[Tuple[int, int]]  # Bounding box points (polygon of 4 coordinates)


class OCRPageResultModel(BaseModel):
    lines: List[OCRTextLineModel]  # List of recognized text lines


@strawberry_pydantic.input(OCRTextLineModel)
class OCRTextLineInput:
    text: str = strawberry.field(description="Recognized text string")
    score: float = strawberry.field(description="Confidence score of recognition")
    angle: float = strawberry.field(description="Detected rotation angle of the text line")
    bbox: List[Tuple[int, int]] = strawberry.field(description="Bounding box points (polygon of 4 coordinates)")


@strawberry_pydantic.input(OCRPageResultModel)
class OCRPageResultInput:
    lines: List[OCRTextLineInput] = strawberry.field(description="List of recognized text lines")
    angle: float = strawberry.field(description="Estimated rotation angle of the page")
