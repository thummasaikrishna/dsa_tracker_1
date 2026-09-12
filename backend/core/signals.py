"""
Auto-create a Profile the instant a User row is created.

This mirrors the PRD's "New User" login flow:
    User authenticates -> no profile exists -> create profile with role=user
Here it's implemented as a Django signal (observer pattern) so it fires
no matter which code path creates the User (register endpoint, admin
panel, management command, etc.) — a single source of truth instead of
duplicating "create profile" logic in every call site.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=User)
def create_profile_on_user_creation(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
