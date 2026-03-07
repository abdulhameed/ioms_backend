from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    label = "maintenance"

    def ready(self):
        pass  # No signals needed — tasks handle async work
