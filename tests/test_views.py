from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask
from django_celery_results.models import TaskResult

from saladbar.models import SaladBarPermissions

User = get_user_model()


def _get_or_create_permissions():
    """Ensure saladbar permissions exist for tests."""
    ct, _ = ContentType.objects.get_or_create(app_label="saladbar", model="saladbarpermissions")
    view_perm, _ = Permission.objects.get_or_create(
        codename="can_view_saladbar",
        content_type=ct,
        defaults={"name": "Can view Salad Bar dashboard"},
    )
    manage_perm, _ = Permission.objects.get_or_create(
        codename="can_manage_saladbar",
        content_type=ct,
        defaults={"name": "Can manage tasks and purge queues"},
    )
    return view_perm, manage_perm


class ViewPermissionTests(TestCase):
    def setUp(self):
        self.view_perm, self.manage_perm = _get_or_create_permissions()
        self.user = User.objects.create_user(username="viewer", password="testpass")
        self.admin = User.objects.create_user(username="admin", password="testpass")
        self.admin.user_permissions.add(self.view_perm, self.manage_perm)
        self.anon_user = None

    def test_dashboard_requires_login(self):
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_dashboard_requires_permission(self):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 403)

    @patch("saladbar.views._get_infra_cached", return_value=([], {"connected": False}))
    def test_dashboard_accessible_with_permission(self, mock_infra):
        self.user.user_permissions.add(self.view_perm)
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 200)

    def test_task_list_requires_login(self):
        response = self.client.get("/saladbar/tasks/")
        self.assertEqual(response.status_code, 302)

    def test_task_list_requires_permission(self):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/tasks/")
        self.assertEqual(response.status_code, 403)

    def test_result_list_requires_permission(self):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/results/")
        self.assertEqual(response.status_code, 403)

    def test_queue_purge_requires_manage_permission(self):
        self.user.user_permissions.add(self.view_perm)
        self.client.login(username="viewer", password="testpass")
        response = self.client.post("/saladbar/queue/purge/")
        self.assertEqual(response.status_code, 403)

    @patch("saladbar.views.get_celery_app")
    def test_queue_purge_allowed_with_manage_permission(self, mock_app):
        mock_app.return_value = MagicMock()
        self.client.login(username="admin", password="testpass")
        response = self.client.post("/saladbar/queue/purge/")
        self.assertEqual(response.status_code, 302)

    def test_task_run_get_redirects(self):
        self.client.login(username="admin", password="testpass")
        response = self.client.get("/saladbar/tasks/999/run/")
        self.assertEqual(response.status_code, 302)

    @patch("saladbar.views.get_celery_app")
    def test_task_status_api_requires_permission(self, mock_app):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/api/task-status/fake-id/")
        self.assertEqual(response.status_code, 403)

    @patch("saladbar.views.get_celery_app")
    def test_task_status_api_returns_json(self, mock_app):
        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.result = "done"
        mock_app.return_value = MagicMock()

        with patch("saladbar.views.AsyncResult", return_value=mock_result):
            self.user.user_permissions.add(self.view_perm)
            self.client.login(username="viewer", password="testpass")
            response = self.client.get("/saladbar/api/task-status/fake-id/")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "SUCCESS")
            self.assertEqual(data["task_id"], "fake-id")

    @patch("saladbar.views.get_celery_app")
    def test_task_status_result_truncated(self, mock_app):
        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.result = "x" * 500
        mock_app.return_value = MagicMock()

        with patch("saladbar.views.AsyncResult", return_value=mock_result):
            self.user.user_permissions.add(self.view_perm)
            self.client.login(username="viewer", password="testpass")
            response = self.client.get("/saladbar/api/task-status/fake-id/")
            data = response.json()
            self.assertLessEqual(len(data["result"]), 200)


class DashboardEmptyStateTests(TestCase):
    """Test that the dashboard renders gracefully with no task data."""

    def setUp(self):
        self.view_perm, self.manage_perm = _get_or_create_permissions()
        self.user = User.objects.create_user(username="viewer", password="testpass")
        self.user.user_permissions.add(self.view_perm)

    @patch("saladbar.views._get_infra_cached", return_value=([], {"connected": False}))
    def test_dashboard_empty_state_no_chart_js_errors(self, mock_infra):
        """Dashboard with zero TaskResults should not render chart canvases."""
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Chart canvases should NOT be rendered when there's no data
        self.assertNotIn('id="hourlyChart"', content)
        self.assertNotIn('id="dailyChart"', content)
        self.assertNotIn('id="queueDepthChart"', content)

    @patch("saladbar.views._get_infra_cached", return_value=([], {"connected": False}))
    def test_dashboard_empty_state_shows_no_data_messages(self, mock_infra):
        """Dashboard with zero TaskResults should show empty-state placeholders."""
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No task data in the last 24 hours")
        self.assertContains(response, "No task data in the last 7 days")
        self.assertContains(response, "No queue data in the last 24 hours")

    @patch("saladbar.views._get_infra_cached", return_value=([], {"connected": False}))
    def test_dashboard_empty_state_stats_show_zero(self, mock_infra):
        """Stat cards should show 0 values, not blank, when there's no data."""
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context["total_24h"], 0)
        self.assertEqual(context["success_rate_24h"], 0)
        self.assertEqual(context["failure_24h"], 0)
        self.assertEqual(context["avg_runtime_s"], 0)
        self.assertEqual(context["throughput"], 0.0)

    @patch("saladbar.views._get_infra_cached", return_value=([], {"connected": False}))
    def test_dashboard_empty_state_context_flags(self, mock_infra):
        """Context should include has_*_data flags set to False when empty."""
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/")
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertFalse(context["has_hourly_data"])
        self.assertFalse(context["has_daily_data"])
        self.assertFalse(context["has_queue_depth_data"])


class TaskListViewTests(TestCase):
    def setUp(self):
        self.view_perm, self.manage_perm = _get_or_create_permissions()
        self.user = User.objects.create_user(username="viewer", password="testpass")
        self.user.user_permissions.add(self.view_perm)

    def test_task_list_renders(self):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Periodic Tasks")

    def test_result_list_renders(self):
        self.client.login(username="viewer", password="testpass")
        response = self.client.get("/saladbar/results/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Task Logs")


class TaskListFilterTests(TestCase):
    def setUp(self):
        self.view_perm, _ = _get_or_create_permissions()
        self.user = User.objects.create_user(username="viewer", password="testpass")
        self.user.user_permissions.add(self.view_perm)
        self.client.login(username="viewer", password="testpass")

        interval = IntervalSchedule.objects.create(every=10, period="seconds")
        crontab = CrontabSchedule.objects.create(minute="*/5", hour="*")

        self.task_a = PeriodicTask.objects.create(
            name="Task A", task="app.task_a", enabled=True, interval=interval,
        )
        self.task_b = PeriodicTask.objects.create(
            name="Task B", task="app.task_b", enabled=False, crontab=crontab,
        )
        self.task_c = PeriodicTask.objects.create(
            name="Cleanup Job", task="app.cleanup", enabled=True, interval=interval,
        )

    def test_no_filters_returns_all(self):
        response = self.client.get("/saladbar/tasks/")
        self.assertEqual(response.status_code, 200)
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 3)

    def test_filter_enabled_true(self):
        response = self.client.get("/saladbar/tasks/", {"enabled": "true"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t.enabled for t in tasks))

    def test_filter_enabled_false(self):
        response = self.client.get("/saladbar/tasks/", {"enabled": "false"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Task B")

    def test_filter_search(self):
        response = self.client.get("/saladbar/tasks/", {"search": "cleanup"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Cleanup Job")

    def test_filter_search_case_insensitive(self):
        response = self.client.get("/saladbar/tasks/", {"search": "TASK"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 2)

    def test_filter_type_interval(self):
        response = self.client.get("/saladbar/tasks/", {"type": "interval"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t.interval is not None for t in tasks))

    def test_filter_type_crontab(self):
        response = self.client.get("/saladbar/tasks/", {"type": "crontab"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Task B")

    def test_combined_filters(self):
        response = self.client.get("/saladbar/tasks/", {"enabled": "true", "type": "interval"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 2)

    def test_filters_passed_to_context(self):
        response = self.client.get("/saladbar/tasks/", {"enabled": "true", "search": "foo", "type": "crontab"})
        self.assertEqual(response.context["filter_enabled"], "true")
        self.assertEqual(response.context["filter_search"], "foo")
        self.assertEqual(response.context["filter_type"], "crontab")

    def test_empty_result_with_filters(self):
        response = self.client.get("/saladbar/tasks/", {"search": "nonexistent"})
        tasks = response.context["tasks"]
        self.assertEqual(len(tasks), 0)
        self.assertContains(response, "No periodic tasks")


class ResultListFilterTests(TestCase):
    def setUp(self):
        self.view_perm, _ = _get_or_create_permissions()
        self.user = User.objects.create_user(username="viewer", password="testpass")
        self.user.user_permissions.add(self.view_perm)
        self.client.login(username="viewer", password="testpass")

        now = timezone.now()
        TaskResult.objects.create(
            task_id="id-1", task_name="app.send_email", status="SUCCESS",
            date_done=now - timedelta(hours=1), date_created=now - timedelta(hours=1, minutes=5),
        )
        TaskResult.objects.create(
            task_id="id-2", task_name="app.send_email", status="FAILURE",
            date_done=now - timedelta(hours=2), date_created=now - timedelta(hours=2, minutes=5),
        )
        TaskResult.objects.create(
            task_id="id-3", task_name="app.process_order", status="SUCCESS",
            date_done=now - timedelta(days=3), date_created=now - timedelta(days=3, minutes=10),
        )

    def test_no_filters_returns_all(self):
        response = self.client.get("/saladbar/results/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["results"]), 3)

    def test_filter_status_success(self):
        response = self.client.get("/saladbar/results/", {"status": "SUCCESS"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.status == "SUCCESS" for r in results))

    def test_filter_status_failure(self):
        response = self.client.get("/saladbar/results/", {"status": "FAILURE"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].task_id, "id-2")

    def test_filter_task_name(self):
        response = self.client.get("/saladbar/results/", {"task_name": "send_email"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 2)

    def test_filter_task_name_case_insensitive(self):
        response = self.client.get("/saladbar/results/", {"task_name": "PROCESS"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 1)

    def test_filter_date_from_excludes_old(self):
        # A date_from in the future should exclude everything
        future = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        response = self.client.get("/saladbar/results/", {"date_from": future})
        results = list(response.context["results"])
        self.assertEqual(len(results), 0)

    def test_filter_date_to_excludes_recent(self):
        # A date_to far in the past should exclude everything
        distant_past = (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        response = self.client.get("/saladbar/results/", {"date_to": distant_past})
        results = list(response.context["results"])
        self.assertEqual(len(results), 0)

    def test_filter_date_range_includes_all(self):
        # A broad date range should include everything
        past = (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        future = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        response = self.client.get("/saladbar/results/", {"date_from": past, "date_to": future})
        results = list(response.context["results"])
        self.assertEqual(len(results), 3)

    def test_combined_filters(self):
        response = self.client.get("/saladbar/results/", {"status": "SUCCESS", "task_name": "send_email"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].task_id, "id-1")

    def test_filters_passed_to_context(self):
        response = self.client.get("/saladbar/results/", {
            "status": "FAILURE", "task_name": "foo", "date_from": "2024-01-01", "date_to": "2024-12-31",
        })
        self.assertEqual(response.context["filter_status"], "FAILURE")
        self.assertEqual(response.context["filter_task_name"], "foo")
        self.assertEqual(response.context["filter_date_from"], "2024-01-01")
        self.assertEqual(response.context["filter_date_to"], "2024-12-31")

    def test_empty_result_with_filters(self):
        response = self.client.get("/saladbar/results/", {"task_name": "nonexistent"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 0)
        self.assertContains(response, "No task results.")

    def test_invalid_status_returns_empty(self):
        response = self.client.get("/saladbar/results/", {"status": "INVALID"})
        results = list(response.context["results"])
        self.assertEqual(len(results), 0)
