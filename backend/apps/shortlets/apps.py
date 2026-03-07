from django.apps import AppConfig


class ShortletsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shortlets"
    label = "shortlets"

    def ready(self):
        import apps.shortlets.signals  # noqa: F401
