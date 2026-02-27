from django.apps import AppConfig


class ArenaApiConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = 'arena_api'
