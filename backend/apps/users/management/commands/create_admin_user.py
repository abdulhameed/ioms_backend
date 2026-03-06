"""
Management command: create_admin_user

Creates the first privileged (md or hr_full) user for bootstrapping a fresh
database. Idempotent — skips silently if the email already exists.

Usage:
    python manage.py create_admin_user
    python manage.py create_admin_user --email boss@example.com --password Secret99! --role hr_full

Defaults: email=admin@example.com, password=AdminPass123!, role=md
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.users.models import CustomUser

PRIVILEGED_ROLES = ("md", "hr_full")


class Command(BaseCommand):
    help = "Create the first privileged user (md or hr_full) for a fresh database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@example.com")
        parser.add_argument("--password", default="AdminPass123!")
        parser.add_argument("--role", default="md", choices=PRIVILEGED_ROLES)

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]
        role = options["role"]

        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f"User '{email}' already exists — skipping."))
            return

        try:
            group = Group.objects.get(name=role)
        except Group.DoesNotExist:
            raise CommandError(
                f"Group '{role}' not found. Run 'make seed' first to create permission groups."
            )

        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=role,
            permission_level="full",
            is_active=True,
        )
        user.groups.add(group)

        self.stdout.write(self.style.SUCCESS(f"Created {role} user: {email}"))
