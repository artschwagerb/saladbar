"""
Saladbar configuration with sensible defaults.

Users can override these in their Django settings module:

    SALADBAR_BASE_TEMPLATE = "myapp/base.html"
    SALADBAR_CELERY_APP = "myproject.celery.app"
    SALADBAR_CACHE_TTL = 60
    SALADBAR_STALE_MULTIPLIER = 2.0
    SALADBAR_ON_SCHEDULE_MULTIPLIER = 1.5
    SALADBAR_LONG_RUNNING_MULTIPLIER = 3.0
    SALADBAR_MAX_RUNTIME_RECORDS = 2000
    SALADBAR_TASK_HISTORY_LIMIT = 50
    SALADBAR_MAX_RESULT_RECORDS = 5000
    SALADBAR_API_RESULT_TRUNCATION = 200
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

# Infra cache TTL in seconds (Celery inspector + Redis info).
DEFAULT_CACHE_TTL = 30

# Multiplier for expected interval to consider a periodic task "stale".
DEFAULT_STALE_MULTIPLIER = 2.0

# Multiplier for expected interval to consider a periodic task "on schedule".
DEFAULT_ON_SCHEDULE_MULTIPLIER = 1.5

# Multiplier for average runtime to flag a task as "long-running".
DEFAULT_LONG_RUNNING_MULTIPLIER = 3.0

# Max runtime records loaded for avg/slowest/long-running calculations.
DEFAULT_MAX_RUNTIME_RECORDS = 2000

# Max execution history entries shown on the task detail page.
DEFAULT_TASK_HISTORY_LIMIT = 50

# Max result records loaded for per-queue stats grouping.
DEFAULT_MAX_RESULT_RECORDS = 5000

# Max characters for result truncation in the task-status API.
DEFAULT_API_RESULT_TRUNCATION = 200


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


def get_cache_ttl():
    return getattr(settings, "SALADBAR_CACHE_TTL", DEFAULT_CACHE_TTL)


def get_stale_multiplier():
    return getattr(settings, "SALADBAR_STALE_MULTIPLIER", DEFAULT_STALE_MULTIPLIER)


def get_on_schedule_multiplier():
    return getattr(settings, "SALADBAR_ON_SCHEDULE_MULTIPLIER", DEFAULT_ON_SCHEDULE_MULTIPLIER)


def get_long_running_multiplier():
    return getattr(settings, "SALADBAR_LONG_RUNNING_MULTIPLIER", DEFAULT_LONG_RUNNING_MULTIPLIER)


def get_max_runtime_records():
    return getattr(settings, "SALADBAR_MAX_RUNTIME_RECORDS", DEFAULT_MAX_RUNTIME_RECORDS)


def get_task_history_limit():
    return getattr(settings, "SALADBAR_TASK_HISTORY_LIMIT", DEFAULT_TASK_HISTORY_LIMIT)


def get_max_result_records():
    return getattr(settings, "SALADBAR_MAX_RESULT_RECORDS", DEFAULT_MAX_RESULT_RECORDS)


def get_api_result_truncation():
    return getattr(settings, "SALADBAR_API_RESULT_TRUNCATION", DEFAULT_API_RESULT_TRUNCATION)
