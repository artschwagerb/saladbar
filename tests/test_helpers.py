from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

import saladbar.views as views_module
from saladbar.views import (
    _get_error_groups,
    _get_expected_interval,
    _get_redis_client,
    _get_stale_tasks,
    _parse_cron_field,
    _parse_schedule_timeline,
)


class ParseCronFieldTests(TestCase):
    def test_wildcard(self):
        self.assertEqual(_parse_cron_field("*", 60), list(range(60)))

    def test_single_value(self):
        self.assertEqual(_parse_cron_field("5", 60), [5])

    def test_comma_separated(self):
        self.assertEqual(_parse_cron_field("1,15,30", 60), [1, 15, 30])

    def test_range(self):
        self.assertEqual(_parse_cron_field("1-5", 24), [1, 2, 3, 4, 5])

    def test_step(self):
        self.assertEqual(_parse_cron_field("*/5", 60), [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])

    def test_step_with_base(self):
        self.assertEqual(_parse_cron_field("10/15", 60), [10, 25, 40, 55])

    def test_zero(self):
        self.assertEqual(_parse_cron_field("0", 60), [0])

    def test_step_hours(self):
        self.assertEqual(_parse_cron_field("*/6", 24), [0, 6, 12, 18])

    # -- Bounds validation tests --

    def test_out_of_range_single_value(self):
        """A value >= max_val should be dropped."""
        self.assertEqual(_parse_cron_field("90", 24), [])

    def test_out_of_range_large_step(self):
        """*/500 with max_val=60 should return only [0]."""
        self.assertEqual(_parse_cron_field("*/500", 60), [0])

    def test_range_partially_out_of_bounds(self):
        """25-30 with max_val=24 should return only values < 24."""
        self.assertEqual(_parse_cron_field("22-30", 24), [22, 23])

    def test_negative_value_dropped(self):
        """Negative values should be dropped."""
        self.assertEqual(_parse_cron_field("-1", 60), [])

    def test_comma_with_mixed_valid_invalid(self):
        """Valid and invalid values in a comma list; only valid ones kept."""
        self.assertEqual(_parse_cron_field("5,70,10", 60), [5, 10])

    def test_zero_step_skipped(self):
        """A step of 0 should not cause an infinite loop."""
        self.assertEqual(_parse_cron_field("*/0", 60), [])

    def test_valid_inputs_unchanged(self):
        """Existing valid inputs should not be affected by bounds checking."""
        self.assertEqual(_parse_cron_field("0", 60), [0])
        self.assertEqual(_parse_cron_field("59", 60), [59])
        self.assertEqual(_parse_cron_field("0-23", 24), list(range(24)))
        self.assertEqual(_parse_cron_field("*/15", 60), [0, 15, 30, 45])


class GetExpectedIntervalTests(TestCase):
    def test_interval_minutes(self):
        task = MagicMock()
        task.interval = MagicMock()
        task.interval.every = 5
        task.interval.period = "minutes"
        task.crontab = None
        self.assertEqual(_get_expected_interval(task), 300)

    def test_interval_hours(self):
        task = MagicMock()
        task.interval = MagicMock()
        task.interval.every = 1
        task.interval.period = "hours"
        task.crontab = None
        self.assertEqual(_get_expected_interval(task), 3600)

    def test_crontab_every_5_min(self):
        task = MagicMock()
        task.interval = None
        task.crontab = MagicMock()
        task.crontab.minute = "*/5"
        task.crontab.hour = "*"
        self.assertEqual(_get_expected_interval(task), 300)

    def test_crontab_hourly(self):
        task = MagicMock()
        task.interval = None
        task.crontab = MagicMock()
        task.crontab.minute = "0"
        task.crontab.hour = "*"
        self.assertEqual(_get_expected_interval(task), 3600)

    def test_crontab_once_daily(self):
        task = MagicMock()
        task.interval = None
        task.crontab = MagicMock()
        task.crontab.minute = "0"
        task.crontab.hour = "3"
        self.assertEqual(_get_expected_interval(task), 86400)

    def test_no_schedule(self):
        task = MagicMock()
        task.interval = None
        task.crontab = None
        self.assertIsNone(_get_expected_interval(task))


class GetErrorGroupsTests(TestCase):
    def test_groups_by_exception_type(self):
        failures = [
            {"traceback": "Traceback ...\nValueError: bad value", "task_name": "a", "date_done": timezone.now(), "id": 1, "result": ""},
            {"traceback": "Traceback ...\nValueError: other", "task_name": "b", "date_done": timezone.now(), "id": 2, "result": ""},
            {"traceback": "Traceback ...\nKeyError: 'x'", "task_name": "c", "date_done": timezone.now(), "id": 3, "result": ""},
        ]
        groups = _get_error_groups(failures)
        by_exc = {g["exception"]: g for g in groups}
        self.assertEqual(by_exc["ValueError"]["count"], 2)
        self.assertEqual(by_exc["KeyError"]["count"], 1)

    def test_empty_failures(self):
        self.assertEqual(_get_error_groups([]), [])

    def test_no_traceback(self):
        failures = [
            {"traceback": "", "result": "", "task_name": "a", "date_done": timezone.now(), "id": 1},
        ]
        groups = _get_error_groups(failures)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["exception"], "Unknown Error")


class GetStaleTasksTests(TestCase):
    def test_overdue_task(self):
        now = timezone.now()
        task = MagicMock()
        task.enabled = True
        task.last_run_at = now - timedelta(hours=3)
        task.interval = MagicMock()
        task.interval.every = 1
        task.interval.period = "hours"
        task.crontab = None
        task.date_changed = now - timedelta(days=2)

        stale = _get_stale_tasks([task], now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["reason"], "Overdue")

    def test_on_schedule_task(self):
        now = timezone.now()
        task = MagicMock()
        task.enabled = True
        task.last_run_at = now - timedelta(minutes=30)
        task.interval = MagicMock()
        task.interval.every = 1
        task.interval.period = "hours"
        task.crontab = None

        stale = _get_stale_tasks([task], now)
        self.assertEqual(len(stale), 0)

    def test_disabled_task_ignored(self):
        now = timezone.now()
        task = MagicMock()
        task.enabled = False
        stale = _get_stale_tasks([task], now)
        self.assertEqual(len(stale), 0)

    def test_never_run_old_task(self):
        now = timezone.now()
        task = MagicMock()
        task.enabled = True
        task.last_run_at = None
        task.date_changed = now - timedelta(days=2)

        stale = _get_stale_tasks([task], now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["reason"], "Never executed")


class ParseScheduleTimelineTests(TestCase):
    def test_simple_crontab(self):
        task = MagicMock()
        task.enabled = True
        task.crontab = MagicMock()
        task.crontab.minute = "0"
        task.crontab.hour = "6,12"
        task.name = "test-task"
        task.task = "app.tasks.test"
        task.pk = 1

        timeline = _parse_schedule_timeline([task])
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["hour"], 6)
        self.assertEqual(timeline[1]["hour"], 12)

    def test_high_frequency_collapsed(self):
        task = MagicMock()
        task.enabled = True
        task.crontab = MagicMock()
        task.crontab.minute = "*/5"
        task.crontab.hour = "0"
        task.name = "frequent-task"
        task.task = "app.tasks.frequent"
        task.pk = 2

        timeline = _parse_schedule_timeline([task])
        self.assertEqual(len(timeline), 1)
        self.assertTrue(timeline[0]["collapsed"])
        self.assertEqual(timeline[0]["freq_label"], "every 5 min")

    def test_disabled_task_excluded(self):
        task = MagicMock()
        task.enabled = False
        task.crontab = MagicMock()
        timeline = _parse_schedule_timeline([task])
        self.assertEqual(len(timeline), 0)

    def test_no_crontab_excluded(self):
        task = MagicMock()
        task.enabled = True
        task.crontab = None
        timeline = _parse_schedule_timeline([task])
        self.assertEqual(len(timeline), 0)


class RedisConnectionPoolTests(TestCase):
    def setUp(self):
        # Reset the module-level pool before each test
        self._original_pool = views_module._redis_pool
        views_module._redis_pool = None

    def tearDown(self):
        views_module._redis_pool = self._original_pool

    @patch("saladbar.views.redis.ConnectionPool.from_url")
    def test_pool_created_on_first_call(self, mock_from_url):
        mock_pool = MagicMock()
        mock_from_url.return_value = mock_pool

        client = _get_redis_client()
        mock_from_url.assert_called_once()
        self.assertIsNotNone(views_module._redis_pool)

    @patch("saladbar.views.redis.ConnectionPool.from_url")
    def test_pool_reused_on_second_call(self, mock_from_url):
        mock_pool = MagicMock()
        mock_from_url.return_value = mock_pool

        _get_redis_client()
        _get_redis_client()
        # from_url should only be called once — the pool is reused
        mock_from_url.assert_called_once()

    @patch("saladbar.views.redis.ConnectionPool.from_url")
    def test_client_uses_shared_pool(self, mock_from_url):
        mock_pool = MagicMock()
        mock_from_url.return_value = mock_pool

        client1 = _get_redis_client()
        client2 = _get_redis_client()
        # Both clients should use the same pool
        self.assertIs(client1.connection_pool, client2.connection_pool)
