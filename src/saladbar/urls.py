from django.urls import path

from . import views

app_name = "saladbar"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.task_list, name="task-list"),
    path("tasks/<int:pk>/", views.task_detail, name="task-detail"),
    path("tasks/<str:task_name>/", views.task_detail_by_name, name="task-detail-by-name"),
    path("tasks/<int:pk>/run/", views.task_run, name="task-run"),
    path("results/", views.result_list, name="result-list"),
    path("results/<int:pk>/", views.result_detail, name="result-detail"),
    path("revoke/<str:task_id>/", views.task_revoke, name="task-revoke"),
    path("queue/purge/", views.queue_purge, name="queue-purge"),
    path("api/task-status/<str:task_id>/", views.task_status, name="task-status"),
    path("metrics/", views.prometheus_metrics, name="metrics"),
]
