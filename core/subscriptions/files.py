import logging
from typing import AsyncGenerator

import strawberry
import strawberry_django
from kante.types import Info
from core import models, scalars, types, channels

logger = logging.getLogger(__name__)


@strawberry.type
class FileEvent:
    create: types.File | None = None
    delete: strawberry.ID | None = None
    update: types.File    | None = None
    moved: types.File | None = None


async def files(
    self,
    info: Info,
    dataset: strawberry.ID | None = None,
) -> AsyncGenerator[FileEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    if dataset is None:
        schannels = ["files"]
    else:
        schannels = ["dataset_files_" + str(dataset)]



    async for message in channels.file_channel.listen(info.context, schannels):
        logger.debug("File channel message: %s", message)
        if message.create:
            file = await models.File.objects.aget(
                id=message.create
            )
            yield FileEvent(create=file)

        elif message.delete:
            yield FileEvent(delete=message.delete)

        elif message.update:
            file = await models.File.objects.aget(
                id=message.update
            )
            yield FileEvent(update=file)

