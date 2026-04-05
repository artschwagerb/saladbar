"""
Saladbar configuration with sensible defaults.

Users can override these in their Django settings module:

    SALADBAR_BASE_TEMPLATE = "myapp/base.html"
    SALADBAR_CELERY_APP = "myproject.celery.app"
"""

from django.conf import settings

# Template that all saladbar pages extend. Must provide blocks:
#   title, css, content, script-footer
DEFAULT_BASE_TEMPLATE = "saladbar/base.html"

# Dotted path to the Celery app instance, e.g. "myproject.celery.app".
# When None, saladbar discovers it automatically via celery._state.
DEFAULT_CELERY_APP = None

# Queue names to check for depth on the dashboard.
DEFAULT_QUEUE_NAMES = ("celery", "default", "bulk")


def get_base_template():
    return getattr(settings, "SALADBAR_BASE_TEMPLATE", DEFAULT_BASE_TEMPLATE)


def get_celery_app():
    app_path = getattr(settings, "SALADBAR_CELERY_APP", DEFAULT_CELERY_APP)
    if app_path:
        from importlib import import_module

        module_path, attr = app_path.rsplit(".", 1)
        return getattr(import_module(module_path), attr)

    # Auto-discover: grab the current default Celery app
    from celery import current_app

    return current_app


def get_queue_names():
    return getattr(settings, "SALADBAR_QUEUE_NAMES", DEFAULT_QUEUE_NAMES)
