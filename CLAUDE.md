# CLAUDE.md

## Project Overview

django-saladbar is a pip-installable Django app (`pip install django-saladbar`) that provides a Celery task monitoring dashboard. It gives visibility into workers, periodic tasks, queue depth, error grouping, and task execution history. It has no models with database tables (permissions-only unmanaged model) and is read-only against `django-celery-beat` and `django-celery-results` tables.

Designed to be reusable across any Django + Celery + Redis project.

## Development Commands

No local Python required. Everything runs in Docker:

```bash
make check    # Build package, run 45 tests, twine check, import verify
make build    # Build and copy dist/ artifacts locally
make test     # Run tests only
make clean    # Remove dist/, build/, *.egg-info
make publish  # Build + upload to PyPI (needs TWINE_USERNAME/TWINE_PASSWORD)
```

## Architecture

### Package Layout (src layout)

```
src/saladbar/
├── conf.py              # Settings with defaults (base template, celery app, queue names)
├── views.py             # All views + helper functions (single file, ~860 lines)
├── urls.py              # 10 URL patterns under app_name="saladbar"
├── models.py            # SaladBarPermissions (unmanaged, permissions-only)
├── apps.py              # SaladbarConfig
├── templatetags/        # saladbar_tags.py (saladbar_base_template tag)
├── templates/saladbar/  # 6 templates (base, dashboard, task_list/detail, result_list/detail)
├── static/saladbar/js/  # chart.min.js (Chart.js 4.5.1, vendored)
├── migrations/          # 0001_initial.py (permissions only)
└── py.typed             # PEP 561 marker
```

### Key Design Decisions

- **No managed models.** Saladbar only reads from `django-celery-beat` (`PeriodicTask`) and `django-celery-results` (`TaskResult`). The only model is `SaladBarPermissions` with `managed = False` — it exists solely to register Django permissions.
- **Configurable base template.** Templates use `{% extends saladbar_base_template %}` where the variable is injected by `_ctx()` in views. Users set `SALADBAR_BASE_TEMPLATE` to their project's base template. Default is `saladbar/base.html` which ships a standalone page with CDN Bootstrap/FontAwesome.
- **Configurable Celery app.** Uses `celery.current_app` by default. Users can set `SALADBAR_CELERY_APP = "myproject.celery.app"` for explicit resolution.
- **Chart.js is vendored as a static file** (`static/saladbar/js/chart.min.js`), not loaded from CDN. Pinned to 4.5.1.
- **CDN resources in `base.html` only.** The default `base.html` fallback uses CDN for Bootstrap/FontAwesome with SRI hashes. Page templates never load these — that's the base template's responsibility.
- **In-memory cache** (`_infra_cache`) caches Celery inspector + Redis info (configurable via `SALADBAR_CACHE_TTL`, default 30s) to avoid 1-4s latency on every page load. Module-level dict, per-process.
- **Redis connection pooling.** A module-level `ConnectionPool` is lazily initialized and reused across requests, avoiding per-request connection overhead.
- **Server-side filtering.** Task list and result list views support server-side filtering via GET parameters (bookmarkable URLs).

### Settings (all optional)

| Setting | Default | Purpose |
|---------|---------|---------|
| `SALADBAR_BASE_TEMPLATE` | `"saladbar/base.html"` | Template all pages extend (must provide blocks: title, css, content, script-footer) |
| `SALADBAR_CELERY_APP` | `None` (auto-discover) | Dotted path to Celery app instance |
| `SALADBAR_QUEUE_NAMES` | `("celery", "default", "bulk")` | Queue names to check for depth |
| `SALADBAR_BROKER_URL` | `None` (falls back to `CELERY_BROKER_URL`) | Optional Redis broker URL override |
| `SALADBAR_CACHE_TTL` | `30` | Infra cache TTL in seconds |
| `SALADBAR_STALE_MULTIPLIER` | `2.0` | Multiplier for stale task detection threshold |
| `SALADBAR_ON_SCHEDULE_MULTIPLIER` | `1.5` | Multiplier for on-schedule tolerance |
| `SALADBAR_LONG_RUNNING_MULTIPLIER` | `3.0` | Multiplier for long-running task detection |
| `SALADBAR_MAX_RUNTIME_RECORDS` | `2000` | Max runtime records for avg/slowest calculations |
| `SALADBAR_TASK_HISTORY_LIMIT` | `50` | Max entries on task detail history |
| `SALADBAR_MAX_RESULT_RECORDS` | `5000` | Max result records for per-queue stats |
| `SALADBAR_API_RESULT_TRUNCATION` | `200` | Max chars in task-status API result |
| `SALADBAR_METRICS_ENABLED` | `False` | Enable the Prometheus `/metrics/` endpoint |
| `SALADBAR_METRICS_TOKEN` | `None` | Bearer token for Prometheus scraper auth |

### Permissions

- `saladbar.can_view_saladbar` — all read-only views (dashboard, task list, results, API)
- `saladbar.can_manage_saladbar` — task run, task revoke, queue purge

Every view uses `@login_required` + `@permission_required(..., raise_exception=True)`.

### URL Routes

All under `app_name = "saladbar"`:

| Pattern | Name | View | Permission |
|---------|------|------|------------|
| `/` | `dashboard` | Dashboard with all monitoring widgets | view |
| `/tasks/` | `task-list` | Periodic task list | view |
| `/tasks/<pk>/` | `task-detail` | Task detail with execution history | view |
| `/tasks/<task_name>/` | `task-detail-by-name` | Task detail by dotted task name | view |
| `/tasks/<pk>/run/` | `task-run` | POST: trigger task execution | manage |
| `/results/` | `result-list` | Task execution logs | view |
| `/results/<pk>/` | `result-detail` | Single result with traceback | view |
| `/revoke/<task_id>/` | `task-revoke` | POST: revoke/terminate task | manage |
| `/queue/purge/` | `queue-purge` | POST: purge all queued tasks | manage |
| `/api/task-status/<task_id>/` | `task-status` | JSON: task status + truncated result | view |
| `/metrics/` | `metrics` | Prometheus metrics (opt-in) | view or token |

### views.py Structure

The file is organized as:
1. **Helpers** (lines ~35-410): `_get_redis_client`, `_get_infra_cached`, `_get_redis_info`, `_get_worker_info`, `_get_in_flight_tasks`, `_expand_crontab`, `_get_expected_interval`, `_get_stale_tasks`, `_get_periodic_health`, `_get_error_groups`, `_parse_schedule_timeline`, `_parse_cron_field`
2. **Views** (lines ~410-980): `dashboard`, `task_list`, `task_detail`, `task_detail_by_name`, `_render_task_detail`, `task_run`, `task_revoke`, `result_list`, `result_detail`, `queue_purge`, `task_status`, `prometheus_metrics`

The `_ctx()` helper injects `saladbar_base_template` into every template context.

### Dependencies

Runtime: Django>=4.2, celery>=5.0, redis>=4.0, django-celery-beat>=2.5, django-celery-results>=2.5

The app reads from these django-celery models but does not define any Celery tasks itself.

## Testing

100+ tests in `tests/` using Django's test framework with SQLite in-memory DB:

- `test_helpers.py` — Pure logic tests for cron parsing, interval calculation, error grouping, stale detection, timeline parsing, crontab expansion, Redis connection pool
- `test_conf.py` — Settings resolution with `@override_settings` for all configurable settings
- `test_views.py` — Permission enforcement, view rendering, API response format, result truncation, empty-state rendering, server-side filtering (task list + result list), retry tracking, Prometheus metrics endpoint

Tests mock Celery inspector and Redis calls — no running services needed. Test settings in `tests/settings.py`.

## Security Notes

- **Task results are sensitive.** The dashboard, result detail, and API expose task results/tracebacks to users with `can_view_saladbar`. Grant carefully.
- **API result truncation.** `task_status` endpoint truncates results to 200 chars.
- **SRI hashes.** All CDN resources in `base.html` have `integrity` + `crossorigin="anonymous"`.
- **CSRF.** All POST forms use `{% csrf_token %}`.
- **XSS.** `|safe` is only used on `json.dumps()` output from server-side integer aggregations (chart data). All user-facing data uses Django auto-escaping.
- **Open redirects.** All `next` redirects validated with `url_has_allowed_host_and_scheme()`.

## CI/CD

- **`.github/workflows/ci.yml`** — Runs on push/PR to main. Tests Python 3.12, 3.13, 3.14. Builds, twine check, install, run tests.
- **`.github/workflows/publish.yml`** — Publishes to PyPI on `v*` tags via trusted publishing.

## Packaging

- `pyproject.toml` with setuptools build backend, src layout
- `MANIFEST.in` includes templates and static files
- `Dockerfile` builds, validates, tests in one image
- Versioned at `0.1.0` in `pyproject.toml`

## Gotchas

- **Template extends variable.** Templates use `{% extends saladbar_base_template %}` (a context variable), not a string literal. This is set by `_ctx()` in views.py via `conf.get_base_template()`. If you add a new template, wrap its context with `_ctx()`.
- **Chart.js is vendored.** Don't add CDN script tags for Chart.js. It's at `static/saladbar/js/chart.min.js` (v4.5.1). To update, download the new version and replace the file.
- **No database tables.** `SaladBarPermissions` is `managed = False`. The migration creates the permission entries but no table. Don't add `managed = True` or real fields.
- **The `_infra_cache` is process-local.** In multi-process deployments (gunicorn), each process has its own 30-second cache. This is intentional.
