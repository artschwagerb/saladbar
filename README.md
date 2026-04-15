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

# Optional broker URL override. Falls back to CELERY_BROKER_URL.
# Default: None
SALADBAR_BROKER_URL = "redis://custom-redis:6379/1"
```

### Tuning

These settings let you adjust detection thresholds and query limits for your workload:

| Setting | Default | Description |
|---------|---------|-------------|
| `SALADBAR_CACHE_TTL` | `30` | Seconds to cache Celery inspector + Redis info |
| `SALADBAR_STALE_MULTIPLIER` | `2.0` | Multiplier for expected interval to flag a task as stale |
| `SALADBAR_ON_SCHEDULE_MULTIPLIER` | `1.5` | Multiplier for expected interval to consider a task on-schedule |
| `SALADBAR_LONG_RUNNING_MULTIPLIER` | `3.0` | Multiplier for average runtime to flag a task as long-running |
| `SALADBAR_MAX_RUNTIME_RECORDS` | `2000` | Max runtime records loaded for avg/slowest calculations |
| `SALADBAR_TASK_HISTORY_LIMIT` | `50` | Max entries shown on the task detail history page |
| `SALADBAR_MAX_RESULT_RECORDS` | `5000` | Max result records loaded for per-queue stats |
| `SALADBAR_API_RESULT_TRUNCATION` | `200` | Max characters in the task-status API result field |

## Permissions

Saladbar defines two permissions:

- `saladbar.can_view_saladbar` — required to access the dashboard and all read-only pages
- `saladbar.can_manage_saladbar` — required to run tasks, revoke tasks, and purge queues

Assign these to users or groups via the Django admin.

> **Security note:** Saladbar exposes Celery task metadata — task names, arguments, results, tracebacks, worker info, and Redis broker stats — to users with `can_view_saladbar`. Users with `can_manage_saladbar` can execute, revoke, and purge tasks. **Grant these permissions carefully.**

## Features

### Dashboard

- Real-time worker status and pool utilization
- 24h/7d task volume charts (with empty-state handling)
- Periodic task health tracking (on-schedule / missed / never-run)
- 24-hour schedule timeline visualization
- Queue depth and throughput monitoring
- Redis broker info (memory, clients, hit rate, evictions)
- In-flight task monitoring with long-running detection
- Error grouping by exception type
- Task retry tracking with per-task retry counts
- Top tasks by volume with trend indicators
- Slowest tasks by average runtime
- Per-queue statistics
- Stale task detection
- Auto-refresh with countdown timer

### Task List

- Server-side filtering by enabled/disabled status, schedule type, and name search
- Run history visualization per task
- One-click task execution

### Task Logs (Results)

- Server-side filtering by status, task name, and date range
- Filters are bookmarkable via GET parameters

### Task Detail

- Execution history with runtime trend chart
- Success/failure/retry counts
- Runtime statistics (avg, min, max)

### Management Actions

- Manual task execution
- Task revocation (with optional terminate)
- Queue purge

## URL Routes

All under the prefix you configure (e.g., `/saladbar/`):

| Path | Name | Description |
|------|------|-------------|
| `/` | `dashboard` | Main monitoring dashboard |
| `/tasks/` | `task-list` | Periodic task list with filters |
| `/tasks/<pk>/` | `task-detail` | Task detail with execution history |
| `/tasks/<task_name>/` | `task-detail-by-name` | Task detail by dotted name |
| `/tasks/<pk>/run/` | `task-run` | POST: trigger task execution |
| `/results/` | `result-list` | Task execution logs with filters |
| `/results/<pk>/` | `result-detail` | Single result with traceback |
| `/revoke/<task_id>/` | `task-revoke` | POST: revoke/terminate task |
| `/queue/purge/` | `queue-purge` | POST: purge all queued tasks |
| `/api/task-status/<task_id>/` | `task-status` | JSON: task status + result |
| `/metrics/` | `metrics` | Prometheus metrics (opt-in) |

## Prometheus Metrics

Saladbar can expose monitoring data in Prometheus text exposition format for integration with Grafana, PagerDuty, Datadog, etc.

### Setup

```python
# settings.py
SALADBAR_METRICS_ENABLED = True

# Optional: bearer token auth for Prometheus scraper (bypasses Django login)
SALADBAR_METRICS_TOKEN = "my-secret-token"
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: saladbar
    metrics_path: /saladbar/metrics/
    bearer_token: my-secret-token
    static_configs:
      - targets: ['myapp:8000']
```

### Exposed Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `saladbar_tasks_total{status="..."}` | gauge | Task count by status (24h) |
| `saladbar_queue_depth{queue="..."}` | gauge | Messages per queue |
| `saladbar_workers_active` | gauge | Number of active workers |
| `saladbar_worker_pool_utilization{worker="..."}` | gauge | Pool utilization % per worker |
| `saladbar_periodic_tasks_stale` | gauge | Number of stale periodic tasks |
| `saladbar_task_avg_runtime_seconds{task="..."}` | gauge | Average runtime per task (24h) |
| `saladbar_redis_connected` | gauge | Broker reachability (0/1) |
| `saladbar_redis_connected_clients` | gauge | Connected Redis clients |

### Authentication

When `SALADBAR_METRICS_TOKEN` is set, requests must include `Authorization: Bearer <token>`. Otherwise, standard Django session auth with `can_view_saladbar` permission is required.

The endpoint returns 404 when `SALADBAR_METRICS_ENABLED` is `False` (default).

## Development

No local Python required. Everything runs in Docker:

```bash
make check    # Build package, run tests, twine check, import verify
make build    # Build and copy dist/ artifacts locally
make test     # Run tests only
make clean    # Remove dist/, build/, *.egg-info
```

## License

MIT
