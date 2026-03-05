"""
Management command: seed_groups

Creates the 13 permission groups and assigns Django model-level permissions.
Idempotent — safe to run multiple times.

Phase 2: Full permission assignment for users-app models.
Later phases: Re-run after each migration to pick up new model permissions.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

GROUPS = [
    "md",
    "hr_full",
    "hr_limited",
    "finance_full",
    "finance_limited",
    "admin_full",
    "admin_limited",
    "pm_full",
    "pm_limited",
    "front_desk",
    "social_media_full",
    "social_media_limited",
    "content_creator",
]

# Permission map: group_name -> list of (app_label, codename)
# Only permissions that exist at migration time will be assigned.
# Re-run this command in later phases to pick up new model permissions.
GROUP_PERMISSIONS = {
    "md": [
        ("users", "add_customuser"),
        ("users", "change_customuser"),
        ("users", "view_customuser"),
        ("users", "delete_customuser"),
        ("users", "view_auditlog"),
        ("users", "view_notification"),
        ("users", "add_notification"),
        ("users", "view_permissiongrant"),
        ("users", "add_permissiongrant"),
        ("users", "change_permissiongrant"),
    ],
    "hr_full": [
        ("users", "add_customuser"),
        ("users", "change_customuser"),
        ("users", "view_customuser"),
        ("users", "view_auditlog"),
        ("users", "view_notification"),
        ("users", "view_permissiongrant"),
        ("users", "add_permissiongrant"),
        ("users", "change_permissiongrant"),
    ],
    "hr_limited": [
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "finance_full": [
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "finance_limited": [
        ("users", "view_customuser"),
    ],
    "admin_full": [
        ("users", "add_customuser"),
        ("users", "change_customuser"),
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "admin_limited": [
        ("users", "view_customuser"),
    ],
    "pm_full": [
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "pm_limited": [
        ("users", "view_customuser"),
    ],
    "front_desk": [
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "social_media_full": [
        ("users", "view_customuser"),
        ("users", "view_notification"),
    ],
    "social_media_limited": [
        ("users", "view_customuser"),
    ],
    "content_creator": [
        ("users", "view_customuser"),
    ],
}


class Command(BaseCommand):
    help = "Create all 13 permission groups and assign model-level permissions (idempotent)."

    def handle(self, *args, **options):
        self.stdout.write("Seeding permission groups...\n")
        created_count = 0

        for name in GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                created_count += 1
                self.stdout.write(f"  [+] Created  : {name}")
            else:
                self.stdout.write(f"  [=] Exists   : {name}")

            perms_to_assign = GROUP_PERMISSIONS.get(name, [])
            assigned = 0
            skipped = 0
            for app_label, codename in perms_to_assign:
                try:
                    perm = Permission.objects.get(
                        codename=codename,
                        content_type__app_label=app_label,
                    )
                    group.permissions.add(perm)
                    assigned += 1
                except Permission.DoesNotExist:
                    skipped += 1

            if assigned or skipped:
                self.stdout.write(
                    f"       permissions: {assigned} assigned, "
                    f"{skipped} skipped (model not yet migrated)"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} group(s) created, "
                f"{len(GROUPS) - created_count} already existed."
            )
        )
