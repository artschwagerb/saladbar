import fnmatch
import json
import logging
import re
import time as _time
from collections import defaultdict
from datetime import timedelta

import redis
from celery import signature
from celery.result import AsyncResult
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult

from .conf import get_base_template, get_celery_app, get_queue_names

# In-memory cache for expensive Celery inspector + Redis calls
_infra_cache = {"data": None, "ts": 0}

logger = logging.getLogger("saladbar")


def _ctx(extra=None):
    """Return a context dict with the base template and any extras merged in."""
    ctx = {"saladbar_base_template": get_base_template()}
    if extra:
        ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_infra_cached(ttl=30):
    """Return cached (workers, redis_info) to avoid repeated inspector/Redis calls.

    Celery inspector issues 4 network RPCs (ping, active, reserved, stats)
    each with a 1s timeout — this is the single biggest latency source on
    the dashboard.  Cache the result for *ttl* seconds so back-to-back or
    auto-refresh page loads are fast.
    """
    now = _time.monotonic()
    if _infra_cache["data"] and (now - _infra_cache["ts"]) < ttl:
        return _infra_cache["data"]
    result = (_get_worker_info(), _get_redis_info())
    _infra_cache["data"] = result
    _infra_cache["ts"] = now
    return result


def _get_redis_info():
    """Get Redis broker info for queue inspection."""
    try:
        r = redis.from_url(settings.CELERY_BROKER_URL)
        info = r.info()
        # Check known Celery queue names directly instead of scanning all keys
        queue_lengths = {}
        for queue_name in get_queue_names():
            try:
                length = r.llen(queue_name)
                if length > 0:
                    queue_lengths[queue_name] = length
            except Exception:
                pass
        # Hit rate
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        hit_rate = round(hits / (hits + misses) * 100, 1) if (hits + misses) else None

        # Memory headroom
        maxmemory = info.get("maxmemory", 0)
        used_memory = info.get("used_memory", 0)
        maxmemory_human = info.get("maxmemory_human", "")
        if maxmemory and used_memory:
            memory_pct = round(used_memory / maxmemory * 100, 1)
        else:
            memory_pct = None

        return {
            "connected": True,
            "version": info.get("redis_version", ""),
            "used_memory_human": info.get("used_memory_human", ""),
            "used_memory_peak_human": info.get("used_memory_peak_human", ""),
            "maxmemory_human": maxmemory_human,
            "memory_pct": memory_pct,
            "connected_clients": info.get("connected_clients", 0),
            "maxclients": info.get("maxclients", 0),
            "uptime_days": info.get("uptime_in_days", 0),
            "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "hit_rate": hit_rate,
            "evicted_keys": info.get("evicted_keys", 0),
            "rejected_connections": info.get("rejected_connections", 0),
            "total_connections_received": info.get("total_connections_received", 0),
            "queue_lengths": queue_lengths,
            "total_queued": sum(queue_lengths.values()),
        }
    except Exception:
        return {"connected": False}


def _get_worker_info():
    """Get active Celery worker info via inspect."""
    celery_app = get_celery_app()
    try:
        inspector = celery_app.control.inspect(timeout=1)
        ping = inspector.ping() or {}
        if not ping:
            return []
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        stats = inspector.stats() or {}

        workers = []
        for name in set(list(active.keys()) + list(stats.keys()) + list(ping.keys())):
            w_stats = stats.get(name, {})
            pool = w_stats.get("pool", {})
            concurrency = pool.get("max-concurrency", 0) if isinstance(pool, dict) else 0
            active_count = len(active.get(name, []))
            utilization = round(active_count / concurrency * 100) if concurrency else 0
            workers.append({
                "name": name,
                "active_tasks": active_count,
                "active_task_list": active.get(name, []),
                "reserved_tasks": len(reserved.get(name, [])),
                "reserved_task_list": reserved.get(name, []),
                "concurrency": concurrency,
                "utilization": utilization,
                "pool_type": pool.get("implementation", "").rsplit(".", 1)[-1] if isinstance(pool, dict) else "",
                "prefetch_count": w_stats.get("prefetch_count", 0),
                "total_tasks": w_stats.get("total", {}) if isinstance(w_stats.get("total"), dict) else {},
                "online": name in ping,
            })
        return workers
    except Exception:
        return []


def _get_in_flight_tasks(workers):
    """Extract all active and reserved tasks across workers."""
    active = []
    reserved = []
    for w in workers:
        for t in w.get("active_task_list", []):
            t["worker_name"] = w["name"]
            active.append(t)
        for t in w.get("reserved_task_list", []):
            t["worker_name"] = w["name"]
            reserved.append(t)
    return active, reserved


def _get_expected_interval(task):
    """Return the expected run interval in seconds for a periodic task, or None.

    For crontab schedules, computes the smallest gap between consecutive
    scheduled times using the parsed minute and hour fields, so schedules
    like ``*/5 * * * *`` correctly return 300 (5 min) instead of 3600.
    """
    if task.interval:
        every = task.interval.every
        period = task.interval.period
        multipliers = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
        return every * multipliers.get(period, 60)
    elif task.crontab:
        ct = task.crontab
        try:
            hours = _parse_cron_field(ct.hour, 24)
            minutes = _parse_cron_field(ct.minute, 60)
        except Exception:
            return 3600  # Fallback

        # Build sorted list of all (hour, minute) pairs as minutes-from-midnight
        times = sorted(h * 60 + m for h in hours for m in minutes)
        if len(times) <= 1:
            return 86400  # Runs once a day or less

        # Smallest gap between consecutive runs (including wrap-around midnight)
        min_gap = min(times[i + 1] - times[i] for i in range(len(times) - 1))
        wrap_gap = (1440 - times[-1]) + times[0]  # midnight wrap
        min_gap = min(min_gap, wrap_gap)
        return min_gap * 60  # Convert minutes to seconds
    return None


def _get_stale_tasks(periodic_tasks, now):
    """Find enabled tasks that haven't run in 2x their schedule interval."""
    stale = []
    for task in periodic_tasks:
        if not task.enabled:
            continue
        if not task.last_run_at:
            if task.date_changed and (now - task.date_changed).total_seconds() > 86400:
                stale.append({"task": task, "reason": "Never executed", "overdue_hours": None})
            continue

        expected_seconds = _get_expected_interval(task)
        if expected_seconds:
            elapsed = (now - task.last_run_at).total_seconds()
            threshold = expected_seconds * 2
            if elapsed > threshold:
                overdue_hours = round((elapsed - expected_seconds) / 3600, 1)
                stale.append({"task": task, "reason": "Overdue", "overdue_hours": overdue_hours})

    return stale


def _get_periodic_health(periodic_tasks, now, last_24h):
    """Compute how many periodic tasks ran on schedule vs. missed in the last 24h."""
    on_schedule = 0
    missed = 0
    never_run = 0
    for task in periodic_tasks:
        if not task.enabled:
            continue
        if not task.last_run_at:
            never_run += 1
            continue
        expected_seconds = _get_expected_interval(task)
        if not expected_seconds:
            continue
        if task.last_run_at >= last_24h:
            elapsed = (now - task.last_run_at).total_seconds()
            if elapsed <= expected_seconds * 1.5:
                on_schedule += 1
            else:
                missed += 1
        else:
            missed += 1
    return on_schedule, missed, never_run


def _get_error_groups(failures):
    """Group failures by exception type parsed from traceback."""
    groups = defaultdict(lambda: {"count": 0, "latest": None, "latest_id": None, "task_names": set()})
    for f in failures:
        tb = f.get("traceback") or f.get("result") or ""
        # Parse exception class from last line of traceback
        exc_type = "Unknown Error"
        lines = tb.strip().splitlines() if tb else []
        if lines:
            last_line = lines[-1].strip()
            # Match "ExceptionClass: message" or just "ExceptionClass"
            match = re.match(r"^([\w.]+(?:Error|Exception|Warning|Timeout|Refused))", last_line)
            if match:
                exc_type = match.group(1)
            elif ":" in last_line:
                exc_type = last_line.split(":")[0].strip()

        groups[exc_type]["count"] += 1
        groups[exc_type]["task_names"].add(f.get("task_name", ""))
        if groups[exc_type]["latest"] is None or (f.get("date_done") and f["date_done"] > groups[exc_type]["latest"]):
            groups[exc_type]["latest"] = f.get("date_done")
            groups[exc_type]["latest_id"] = f.get("id")

    # Convert sets to counts and sort
    result = []
    for exc_type, data in groups.items():
        result.append({
            "exception": exc_type,
            "count": data["count"],
            "affected_tasks": len(data["task_names"]),
            "latest": data["latest"],
            "latest_id": data["latest_id"],
        })
    return sorted(result, key=lambda x: -x["count"])


def _parse_schedule_timeline(periodic_tasks):
    """Parse crontab schedules into a 24-hour timeline for visualization.

    High-frequency tasks (>2 runs per hour) are collapsed into a single
    entry per hour with a frequency label instead of one box per execution.
    """
    timeline = []
    for task in periodic_tasks:
        if not task.enabled or not task.crontab:
            continue
        ct = task.crontab
        try:
            hours = _parse_cron_field(ct.hour, 24)
            minutes = _parse_cron_field(ct.minute, 60)
        except Exception:
            continue

        runs_per_hour = len(minutes)
        if runs_per_hour > 2:
            # Collapse high-frequency tasks into one entry per hour
            minute_field = str(ct.minute).strip()
            if minute_field == "*":
                freq_label = "every min"
            elif "/" in minute_field:
                step = minute_field.split("/")[1]
                freq_label = f"every {step} min"
            else:
                freq_label = f"{runs_per_hour}x/hr"

            for h in hours:
                timeline.append({
                    "name": task.name,
                    "task": task.task,
                    "pk": task.pk,
                    "hour": h,
                    "minute": 0,
                    "time_minutes": h * 60,
                    "collapsed": True,
                    "freq_label": freq_label,
                })
        else:
            for h in hours:
                for m in minutes:
                    timeline.append({
                        "name": task.name,
                        "task": task.task,
                        "pk": task.pk,
                        "hour": h,
                        "minute": m,
                        "time_minutes": h * 60 + m,
                        "collapsed": False,
                    })
    return sorted(timeline, key=lambda x: x["time_minutes"])


def _parse_cron_field(field, max_val):
    """Parse a crontab field like '0', '*/5', '1,15', '1-5' into a list of ints."""
    field = str(field).strip()
    if field == "*":
        return list(range(max_val))

    values = set()
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            start = 0 if base == "*" else int(base)
            values.update(range(start, max_val, step))
        elif "-" in part:
            start, end = part.split("-", 1)
            values.update(range(int(start), int(end) + 1))
        else:
            values.add(int(part))
    return sorted(values)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def dashboard(request):
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_1h = now - timedelta(hours=1)

    # Base querysets (lazy — no DB hit until evaluated)
    results_24h = TaskResult.objects.filter(date_done__gte=last_24h)
    results_7d = TaskResult.objects.filter(date_done__gte=last_7d)

    # -- Consolidated 24h stats (1 query instead of 4) --
    stats_24h = results_24h.aggregate(
        total=Count("id"),
        successes=Count("id", filter=Q(status="SUCCESS")),
        failures=Count("id", filter=Q(status="FAILURE")),
    )
    total_24h = stats_24h["total"]
    success_24h = stats_24h["successes"]
    failure_24h = stats_24h["failures"]
    success_rate_24h = round((success_24h / total_24h * 100), 1) if total_24h else 0

    # Throughput: tasks/minute over the last hour
    total_1h = TaskResult.objects.filter(date_done__gte=last_1h).count()
    throughput = round(total_1h / 60, 1)

    # -- Runtime data (1 query — reused for avg runtime, slowest tasks, long-running) --
    task_runtimes = {}
    all_runtimes = []
    for created, done, name in (
        results_24h.filter(
            status="SUCCESS",
            date_created__isnull=False,
            date_done__isnull=False,
        )
        .order_by("-date_done")
        .values_list("date_created", "date_done", "task_name")[:2000]
    ):
        if done and created:
            secs = (done - created).total_seconds()
            task_runtimes.setdefault(name, []).append(secs)
            all_runtimes.append(secs)
    avg_runtime_s = round(sum(all_runtimes) / len(all_runtimes), 1) if all_runtimes else 0

    slowest_tasks = sorted(
        [
            {"task_name": name, "avg_seconds": round(sum(times) / len(times), 1), "count": len(times)}
            for name, times in task_runtimes.items()
        ],
        key=lambda x: -x["avg_seconds"],
    )[:10]

    # -- Hourly volume chart (reused for queue depth chart) --
    hourly_volume = list(
        results_24h
        .annotate(hour=TruncHour("date_done"))
        .values("hour")
        .annotate(
            total=Count("id"),
            successes=Count("id", filter=Q(status="SUCCESS")),
            failures=Count("id", filter=Q(status="FAILURE")),
        )
        .order_by("hour")
    )
    chart_labels, chart_success, chart_failure = [], [], []
    hourly_completed_map = {}
    for entry in hourly_volume:
        label = entry["hour"].strftime("%H:%M")
        chart_labels.append(label)
        chart_success.append(entry["successes"])
        chart_failure.append(entry["failures"])
        hourly_completed_map[entry["hour"]] = entry["total"]

    # Queue depth: queued (by date_created) vs completed (reuse hourly_volume)
    hourly_queued_map = dict(
        results_24h
        .filter(date_created__isnull=False)
        .annotate(hour=TruncHour("date_created"))
        .values("hour")
        .annotate(queued=Count("id"))
        .order_by("hour")
        .values_list("hour", "queued")
    )
    all_hours = sorted(set(list(hourly_queued_map.keys()) + list(hourly_completed_map.keys())))
    queue_depth_labels = []
    queue_depth_queued = []
    queue_depth_completed = []
    for h in all_hours:
        queue_depth_labels.append(h.strftime("%H:%M"))
        queue_depth_queued.append(hourly_queued_map.get(h, 0))
        queue_depth_completed.append(hourly_completed_map.get(h, 0))

    # Daily volume chart (7d)
    daily_volume = (
        results_7d
        .annotate(day=TruncDate("date_done"))
        .values("day")
        .annotate(
            successes=Count("id", filter=Q(status="SUCCESS")),
            failures=Count("id", filter=Q(status="FAILURE")),
        )
        .order_by("day")
    )
    daily_labels, daily_success, daily_failure = [], [], []
    for entry in daily_volume:
        daily_labels.append(entry["day"].strftime("%b %d"))
        daily_success.append(entry["successes"])
        daily_failure.append(entry["failures"])

    # -- Top tasks with trend (2 queries: current 24h + prior 24h) --
    top_tasks_qs = (
        results_24h
        .values("task_name")
        .annotate(
            count=Count("id"),
            failures=Count("id", filter=Q(status="FAILURE")),
        )
        .order_by("-count")[:10]
    )
    prior_24h_start = now - timedelta(hours=48)
    prior_task_stats = {}
    for row in (
        TaskResult.objects.filter(date_done__gte=prior_24h_start, date_done__lt=last_24h)
        .values("task_name")
        .annotate(count=Count("id"), failures=Count("id", filter=Q(status="FAILURE")))
    ):
        if row["count"]:
            prior_task_stats[row["task_name"]] = round(row["failures"] / row["count"] * 100, 1)

    top_tasks = []
    for t in top_tasks_qs:
        current_rate = round(t["failures"] / t["count"] * 100, 1) if t["count"] else 0
        prior_rate = prior_task_stats.get(t["task_name"])
        if prior_rate is not None:
            if current_rate > prior_rate + 2:
                t["trend"] = "worsening"
            elif current_rate < prior_rate - 2:
                t["trend"] = "improving"
            else:
                t["trend"] = "stable"
        else:
            t["trend"] = "new"
        top_tasks.append(t)

    # -- Recent failures + error grouping (1 query) --
    recent_failure_qs = list(
        TaskResult.objects.filter(status="FAILURE", date_done__gte=last_24h)
        .order_by("-date_done")[:100]
        .values("id", "task_name", "date_done", "result", "traceback")
    )
    error_groups = _get_error_groups(recent_failure_qs)
    recent_failures = recent_failure_qs[:10]

    # Failure rate by task (7d)
    failure_by_task = (
        results_7d
        .values("task_name")
        .annotate(
            total=Count("id"),
            failures=Count("id", filter=Q(status="FAILURE")),
        )
        .filter(failures__gt=0)
        .order_by("-failures")[:10]
    )

    # Retry tracking — not available in this version of django-celery-results
    retry_tasks = []

    # -- Per-queue stats (1 query, Python-side grouping) --
    queue_routing = getattr(settings, "CELERY_TASK_ROUTES", {})
    _queue_cache = {}

    def _resolve_queue(task_name):
        if task_name in _queue_cache:
            return _queue_cache[task_name]
        for pattern, route in queue_routing.items():
            if fnmatch.fnmatch(task_name, pattern):
                q = route.get("queue", "default") if isinstance(route, dict) else "default"
                _queue_cache[task_name] = q
                return q
        _queue_cache[task_name] = "default"
        return "default"

    queue_stats = defaultdict(lambda: {"total": 0, "success": 0, "failure": 0, "runtimes": []})
    for name, created, done, status in results_24h.values_list(
        "task_name", "date_created", "date_done", "status"
    )[:5000]:
        if not name:
            continue
        queue = _resolve_queue(name)
        queue_stats[queue]["total"] += 1
        if status == "SUCCESS":
            queue_stats[queue]["success"] += 1
        elif status == "FAILURE":
            queue_stats[queue]["failure"] += 1
        if created and done and status == "SUCCESS":
            queue_stats[queue]["runtimes"].append((done - created).total_seconds())

    queue_summary = []
    for q_name, q_data in sorted(queue_stats.items()):
        rt = q_data["runtimes"]
        queue_summary.append({
            "name": q_name,
            "total": q_data["total"],
            "success": q_data["success"],
            "failure": q_data["failure"],
            "success_rate": round(q_data["success"] / q_data["total"] * 100, 1) if q_data["total"] else 0,
            "avg_runtime": round(sum(rt) / len(rt), 1) if rt else 0,
        })

    # -- Periodic tasks (1 query, all in-memory after this) --
    periodic_tasks = list(
        PeriodicTask.objects.select_related("interval", "crontab").order_by("name")
    )
    enabled_count = sum(1 for t in periodic_tasks if t.enabled)
    disabled_count = sum(1 for t in periodic_tasks if not t.enabled)

    stale_tasks = _get_stale_tasks(periodic_tasks, now)
    periodic_on_schedule, periodic_missed, periodic_never_run = _get_periodic_health(
        periodic_tasks, now, last_24h
    )

    schedule_timeline = _parse_schedule_timeline(periodic_tasks)
    timeline_by_hour = defaultdict(list)
    for entry in schedule_timeline:
        timeline_by_hour[entry["hour"]].append(entry)
    timeline_hours = []
    for h in range(24):
        timeline_hours.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "tasks": timeline_by_hour.get(h, []),
            "count": len(timeline_by_hour.get(h, [])),
        })

    # -- Infrastructure (cached — avoids 1-4s of Celery inspector RPCs) --
    workers, redis_info = _get_infra_cached(ttl=30)
    active_tasks, reserved_tasks = _get_in_flight_tasks(workers)

    # Long-running task detection (3x avg runtime)
    for t in active_tasks:
        task_name = t.get("name") or t.get("type", "")
        avg_times = task_runtimes.get(task_name)
        time_start = t.get("time_start")
        if avg_times and time_start:
            avg_secs = sum(avg_times) / len(avg_times)
            running_secs = now.timestamp() - time_start
            t["running_seconds"] = round(running_secs, 1)
            t["avg_runtime"] = round(avg_secs, 1)
            if running_secs > avg_secs * 3 and avg_secs > 5:
                t["long_running"] = True

    context = _ctx({
        # Stats
        "total_24h": total_24h,
        "success_24h": success_24h,
        "failure_24h": failure_24h,
        "success_rate_24h": success_rate_24h,
        "avg_runtime_s": avg_runtime_s,
        "throughput": throughput,
        # Periodic tasks
        "periodic_task_count": len(periodic_tasks),
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        # Charts
        "chart_labels": json.dumps(chart_labels),
        "chart_success": json.dumps(chart_success),
        "chart_failure": json.dumps(chart_failure),
        "has_hourly_data": bool(chart_labels),
        "daily_labels": json.dumps(daily_labels),
        "daily_success": json.dumps(daily_success),
        "daily_failure": json.dumps(daily_failure),
        "has_daily_data": bool(daily_labels),
        # Tables
        "top_tasks": top_tasks,
        "slowest_tasks": slowest_tasks,
        "recent_failures": recent_failures,
        "failure_by_task": failure_by_task,
        "error_groups": error_groups,
        "retry_tasks": retry_tasks,
        "queue_summary": queue_summary,
        # Queue depth chart
        "queue_depth_labels": json.dumps(queue_depth_labels),
        "queue_depth_queued": json.dumps(queue_depth_queued),
        "queue_depth_completed": json.dumps(queue_depth_completed),
        "has_queue_depth_data": bool(queue_depth_labels),
        # Stale / Schedule
        "stale_tasks": stale_tasks,
        "schedule_timeline": schedule_timeline,
        "timeline_hours": timeline_hours,
        "current_hour": now.hour,
        # Periodic health
        "periodic_on_schedule": periodic_on_schedule,
        "periodic_missed": periodic_missed,
        "periodic_never_run": periodic_never_run,
        # Infrastructure
        "workers": workers,
        "active_tasks": active_tasks,
        "reserved_tasks": reserved_tasks,
        "redis_info": redis_info,
    })
    return render(request, "saladbar/dashboard.html", context)


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def task_list(request):
    tasks = list(
        PeriodicTask.objects.select_related("interval", "crontab").order_by("name")
    )

    # Bulk-fetch latest result and run history to avoid N+1 queries
    task_names = {task.task for task in tasks}
    latest_results = {}
    run_histories = defaultdict(list)

    if task_names:
        for result in (
            TaskResult.objects.filter(task_name__in=task_names)
            .order_by("task_name", "-date_done")
        ):
            name = result.task_name
            if name not in latest_results:
                latest_results[name] = result
            if len(run_histories[name]) < 10:
                run_histories[name].append(result.status)

    for task in tasks:
        task.latest_result = latest_results.get(task.task)
        task.run_history = run_histories.get(task.task, [])

    return render(request, "saladbar/task_list.html", _ctx({"tasks": tasks}))


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def task_detail(request, pk):
    task = get_object_or_404(PeriodicTask.objects.select_related("interval", "crontab"), pk=pk)
    return _render_task_detail(request, task)


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def task_detail_by_name(request, task_name):
    task = get_object_or_404(PeriodicTask.objects.select_related("interval", "crontab"), task=task_name)
    return _render_task_detail(request, task)


def _render_task_detail(request, task):
    results = list(
        TaskResult.objects.filter(task_name=task.task)
        .order_by("-date_done")[:50]
    )

    # Runtime stats + chart data
    runtimes = []
    runtime_chart_labels = []
    runtime_chart_data = []
    runtime_chart_colors = []
    for r in reversed(results):  # Oldest first for chart
        if r.date_created and r.date_done and r.status == "SUCCESS":
            secs = round((r.date_done - r.date_created).total_seconds(), 1)
            runtimes.append(secs)
            runtime_chart_labels.append(r.date_done.strftime("%m/%d %H:%M"))
            runtime_chart_data.append(secs)
            runtime_chart_colors.append("#10b981")
        elif r.status == "FAILURE":
            runtime_chart_labels.append(r.date_done.strftime("%m/%d %H:%M") if r.date_done else "?")
            runtime_chart_data.append(None)  # Gap in line
            runtime_chart_colors.append("#ef4444")

    avg_runtime = round(sum(runtimes) / len(runtimes), 1) if runtimes else 0
    min_runtime = round(min(runtimes), 1) if runtimes else 0
    max_runtime = round(max(runtimes), 1) if runtimes else 0

    success_count = sum(1 for r in results if r.status == "SUCCESS")
    failure_count = sum(1 for r in results if r.status == "FAILURE")
    retry_count = 0

    return render(request, "saladbar/task_detail.html", _ctx({
        "task": task,
        "results": results,
        "avg_runtime": avg_runtime,
        "min_runtime": min_runtime,
        "max_runtime": max_runtime,
        "success_count": success_count,
        "failure_count": failure_count,
        "retry_count": retry_count,
        "runtime_chart_labels": json.dumps(runtime_chart_labels),
        "runtime_chart_data": json.dumps(runtime_chart_data),
    }))


@login_required
@permission_required("saladbar.can_manage_saladbar", raise_exception=True)
def task_run(request, pk):
    if request.method != "POST":
        return redirect("saladbar:dashboard")

    task = get_object_or_404(PeriodicTask, pk=pk)
    try:
        args = json.loads(task.args or "[]")
        kwargs = json.loads(task.kwargs or "{}")
        sig = signature(task.task, args=args, kwargs=kwargs)
        sig.apply_async()
        messages.success(request, f"Task '{task.name}' has been queued.")
    except Exception as e:
        messages.error(request, f"Failed to queue task: {e}")

    next_url = request.POST.get("next", "")
    if not next_url or not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect("saladbar:task-list")
    return redirect(next_url)


@login_required
@permission_required("saladbar.can_manage_saladbar", raise_exception=True)
def task_revoke(request, task_id):
    """Revoke a running or queued task."""
    if request.method != "POST":
        return redirect("saladbar:dashboard")
    celery_app = get_celery_app()
    terminate = request.POST.get("terminate") == "1"
    try:
        celery_app.control.revoke(task_id, terminate=terminate)
        messages.success(request, f"Task {task_id[:12]}... has been revoked{' (terminated)' if terminate else ''}.")
    except Exception as e:
        messages.error(request, f"Failed to revoke task: {e}")

    next_url = request.POST.get("next", "")
    if not next_url or not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect("saladbar:dashboard")
    return redirect(next_url)


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def result_list(request):
    limit = 1000
    if request.GET.get("all"):
        limit = 5000
    results = TaskResult.objects.order_by("-date_done")[:limit]
    return render(request, "saladbar/result_list.html", _ctx({"results": results, "limit": limit}))


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def result_detail(request, pk):
    result = get_object_or_404(TaskResult, pk=pk)

    duration = None
    if result.date_created and result.date_done:
        delta = result.date_done - result.date_created
        total_secs = delta.total_seconds()
        if total_secs >= 60:
            mins = int(total_secs // 60)
            secs = round(total_secs % 60, 1)
            duration = f"{mins}m {secs}s"
        else:
            duration = f"{round(total_secs, 2)}s"

    result_pretty = result.result
    try:
        result_pretty = json.dumps(json.loads(result.result), indent=2)
    except (json.JSONDecodeError, TypeError):
        pass

    return render(request, "saladbar/result_detail.html", _ctx({
        "result": result,
        "duration": duration,
        "result_pretty": result_pretty,
    }))


@login_required
@permission_required("saladbar.can_manage_saladbar", raise_exception=True)
def queue_purge(request):
    if request.method != "POST":
        return redirect("saladbar:dashboard")
    celery_app = get_celery_app()
    try:
        celery_app.control.purge()
        messages.success(request, "Celery queue has been purged.")
    except Exception as e:
        messages.error(request, f"Failed to purge queue: {e}")
    return redirect("saladbar:dashboard")


@login_required
@permission_required("saladbar.can_view_saladbar", raise_exception=True)
def task_status(request, task_id):
    celery_app = get_celery_app()
    result = AsyncResult(task_id, app=celery_app)
    return JsonResponse({
        "task_id": task_id,
        "status": result.status,
        "result": str(result.result)[:200] if result.result else None,
    })
