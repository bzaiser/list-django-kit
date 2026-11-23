from django.apps import AppConfig


class ListKitConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "list_kit"
    verbose_name = "Listen & Builder"

    def ready(self):
        try:
            from notify_kit.registry import register_notification_topic
            register_notification_topic(
                key="list_kit.submission",
                label="Neue Formular-Eingänge",
                description="Benachrichtigung bei öffentlichen Einreichungen über list_kit.",
                icon="bi-inbox",
                default_enabled=True,
                staff_only=True,
            )
        except Exception:
            pass
