"""
Migration: revoke UPDATE on the audit log table from the application DB user.

The archive task (audit_log_archive) uses queryset.delete() on old rows —
that path is intentional and still works. What we revoke is UPDATE only,
preventing accidental in-place edits to audit entries.

The DO-block is a no-op when the 'propms_user' role doesn't exist (e.g. in
CI test databases), so this migration is safe in all environments.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'propms_user') THEN
                    REVOKE UPDATE ON users_auditlog FROM propms_user;
                END IF;
            END
            $$;
            """,
            reverse_sql="""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'propms_user') THEN
                    GRANT UPDATE ON users_auditlog TO propms_user;
                END IF;
            END
            $$;
            """,
        ),
    ]
