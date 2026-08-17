from django.apps import AppConfig


class EntriesConfig(AppConfig):
    name = 'entries'

    def ready(self):
        from . import signals  # noqa: F401
