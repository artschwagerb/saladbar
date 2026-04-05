from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory

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
