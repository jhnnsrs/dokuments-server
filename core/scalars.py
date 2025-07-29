from typing import NewType

import strawberry


FileLike = strawberry.scalar(
    NewType("FileLike", str),
    description="The `FileLike` scalar type represents a reference to a big file"
    " storage previously created by the user n a datalayer",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)


