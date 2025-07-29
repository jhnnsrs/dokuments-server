from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from core import models, channels
from core import models



@receiver(post_save, sender=models.File)
def my_file_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.file_channel.broadcast(
            channels.FileSignal(create=instance.id),
            ["files"],
        )
    else:
        channels.file_channel.broadcast(
            channels.FileSignal(update=instance.id),
            ["files"],
        )
      

@receiver(pre_delete, sender=models.File)
def my_file_delete_handler(sender, instance=None, **kwargs):
     channels.file_channel.broadcast(
        channels.FileSignal(delete=instance.id),
        ["files"],
    )
