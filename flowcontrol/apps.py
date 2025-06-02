from django.apps import AppConfig


class FlowcontrolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flowcontrol"

    def ready(self):
        # Import the action registry to ensure it's initialized
        from . import actions  # noqa: F401
