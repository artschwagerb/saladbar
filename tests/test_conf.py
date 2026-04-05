from django.test import TestCase, override_settings

from saladbar.conf import get_base_template, get_celery_app, get_queue_names


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
