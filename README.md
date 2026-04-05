# django-saladbar

A Celery task monitoring dashboard for Django. Drop-in UI for monitoring workers, periodic tasks, queue depth, error grouping, and more.

## Requirements

- Python 3.10+
- Django 4.2+
- Celery 5.0+ with Redis broker
- django-celery-beat
- django-celery-results

## Installation

```bash
pip install django-saladbar
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django_celery_results",
    "django_celery_beat",
    "saladbar",
]
```

Include the URL conf:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("saladbar/", include("saladbar.urls")),
]
```

Run migrations:

```bash
python manage.py migrate
```

## Configuration

All settings are optional. Add to your Django `settings.py`:

```python
# Template that saladbar pages extend.
# Must provide blocks: title, css, content, script-footer.
# Default: "saladbar/base.html" (ships with the package — includes Bootstrap 5 + FontAwesome)
SALADBAR_BASE_TEMPLATE = "myapp/base.html"

# Dotted path to your Celery app instance.
# Default: auto-discovered via celery.current_app
SALADBAR_CELERY_APP = "myproject.celery.app"

# Queue names to check for depth on the dashboard.
# Default: ("celery", "default", "bulk")
SALADBAR_QUEUE_NAMES = ("celery", "default", "high-priority")
```

## Permissions

Saladbar defines two permissions:

- `saladbar.can_view_saladbar` — required to access the dashboard and all read-only pages
- `saladbar.can_manage_saladbar` — required to run tasks, revoke tasks, and purge queues

Assign these to users or groups via the Django admin.

> **Security note:** Saladbar exposes Celery task metadata — task names, arguments, results, tracebacks, worker info, and Redis broker stats — to users with `can_view_saladbar`. Users with `can_manage_saladbar` can execute, revoke, and purge tasks. **Grant these permissions carefully.**

## Features

- Real-time worker status and pool utilization
- 24h/7d task volume charts
- Periodic task health tracking (on-schedule / missed / never-run)
- 24-hour schedule timeline visualization
- Queue depth and throughput monitoring
- Redis broker info (memory, clients, hit rate, evictions)
- In-flight task monitoring with long-running detection
- Error grouping by exception type
- Top tasks by volume with trend indicators
- Slowest tasks by average runtime
- Per-queue statistics
- Stale task detection
- Task execution history with runtime trend charts
- Manual task execution and revocation
- Queue purge
- Auto-refresh with countdown timer

## Development

```bash
git clone https://github.com/bartschwager/django-saladbar.git
cd django-saladbar
pip install -e ".[dev]"
```

## License

MIT
