"""
User signals — Phase 2.

sync_user_group: keeps Django Group membership in sync with user.role + permission_level.
"""

from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import CustomUser


@receiver(post_save, sender=CustomUser)
def sync_user_group(sender, instance, **kwargs):
    """
    After any CustomUser save: clear all group memberships and re-add the
    single group that matches the user's current role + permission_level.

    If the user is promoted to 'full' permission level, all individual
    PermissionGrant records are also deactivated.
    """
    if not instance.role:
        return

    instance.groups.clear()
    group, _ = Group.objects.get_or_create(name=instance.get_role_key())
    instance.groups.add(group)

    if instance.permission_level == "full":
        instance.user_permissions.clear()
        instance.granted_permissions.filter(is_active=True).update(is_active=False)
