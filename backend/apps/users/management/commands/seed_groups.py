"""
Management command: seed_groups

Creates the 13 permission groups used throughout the system.
Idempotent — safe to run multiple times without creating duplicates.

Phase 1: Creates group names only.
Phase 2: Enhances this command to assign Django model-level permissions to each group.
"""

from django.contrib.auth.models import Group
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


class Command(BaseCommand):
    help = "Create all 13 permission groups (idempotent)."

    def handle(self, *args, **options):
        self.stdout.write("Seeding permission groups...\n")
        created_count = 0

        for name in GROUPS:
            _, created = Group.objects.get_or_create(name=name)
            if created:
                created_count += 1
                self.stdout.write(f"  [+] Created  : {name}")
            else:
                self.stdout.write(f"  [=] Exists   : {name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} group(s) created, "
                f"{len(GROUPS) - created_count} already existed."
            )
        )
