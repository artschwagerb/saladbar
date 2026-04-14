from django.test import TestCase, override_settings

from saladbar.conf import (
    get_api_result_truncation,
    get_base_template,
    get_cache_ttl,
    get_celery_app,
    get_long_running_multiplier,
    get_max_result_records,
    get_max_runtime_records,
    get_on_schedule_multiplier,
    get_queue_names,
    get_stale_multiplier,
    get_task_history_limit,
)


class GetBaseTemplateTests(TestCase):
    def test_default(self):
        self.assertEqual(get_base_template(), "saladbar/base.html")

    @override_settings(SALADBAR_BASE_TEMPLATE="myapp/base.html")
    def test_override(self):
        self.assertEqual(get_base_template(), "myapp/base.html")


class GetCeleryAppTests(TestCase):
    def test_default_returns_current_app(self):
        app = get_celery_app()
        self.assertIsNotNone(app)

    @override_settings(SALADBAR_CELERY_APP="celery.Celery")
    def test_dotted_path(self):
        app = get_celery_app()
        # The resolved object should be the Celery class itself
        from celery import Celery

        self.assertIs(app, Celery)


class GetQueueNamesTests(TestCase):
    def test_default(self):
        self.assertEqual(get_queue_names(), ("celery", "default", "bulk"))

    @override_settings(SALADBAR_QUEUE_NAMES=("high", "low"))
    def test_override(self):
        self.assertEqual(get_queue_names(), ("high", "low"))


class GetCacheTtlTests(TestCase):
    def test_default(self):
        self.assertEqual(get_cache_ttl(), 30)

    @override_settings(SALADBAR_CACHE_TTL=60)
    def test_override(self):
        self.assertEqual(get_cache_ttl(), 60)


class GetStaleMultiplierTests(TestCase):
    def test_default(self):
        self.assertEqual(get_stale_multiplier(), 2.0)

    @override_settings(SALADBAR_STALE_MULTIPLIER=3.0)
    def test_override(self):
        self.assertEqual(get_stale_multiplier(), 3.0)


class GetOnScheduleMultiplierTests(TestCase):
    def test_default(self):
        self.assertEqual(get_on_schedule_multiplier(), 1.5)

    @override_settings(SALADBAR_ON_SCHEDULE_MULTIPLIER=2.0)
    def test_override(self):
        self.assertEqual(get_on_schedule_multiplier(), 2.0)


class GetLongRunningMultiplierTests(TestCase):
    def test_default(self):
        self.assertEqual(get_long_running_multiplier(), 3.0)

    @override_settings(SALADBAR_LONG_RUNNING_MULTIPLIER=5.0)
    def test_override(self):
        self.assertEqual(get_long_running_multiplier(), 5.0)


class GetMaxRuntimeRecordsTests(TestCase):
    def test_default(self):
        self.assertEqual(get_max_runtime_records(), 2000)

    @override_settings(SALADBAR_MAX_RUNTIME_RECORDS=500)
    def test_override(self):
        self.assertEqual(get_max_runtime_records(), 500)


class GetTaskHistoryLimitTests(TestCase):
    def test_default(self):
        self.assertEqual(get_task_history_limit(), 50)

    @override_settings(SALADBAR_TASK_HISTORY_LIMIT=100)
    def test_override(self):
        self.assertEqual(get_task_history_limit(), 100)


class GetMaxResultRecordsTests(TestCase):
    def test_default(self):
        self.assertEqual(get_max_result_records(), 5000)

    @override_settings(SALADBAR_MAX_RESULT_RECORDS=10000)
    def test_override(self):
        self.assertEqual(get_max_result_records(), 10000)


class GetApiResultTruncationTests(TestCase):
    def test_default(self):
        self.assertEqual(get_api_result_truncation(), 200)

    @override_settings(SALADBAR_API_RESULT_TRUNCATION=500)
    def test_override(self):
        self.assertEqual(get_api_result_truncation(), 500)
