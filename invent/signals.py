from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def create_or_ensure_user_profile(sender, instance, created, **kwargs):
    """
    Ensure a Profile exists for each User. Use get_or_create to avoid integrity errors.
    This is defensive — admin add flow will not try to create an inline profile thanks to admin.get_inline_instances override.
    """
    Profile.objects.get_or_create(user=instance)