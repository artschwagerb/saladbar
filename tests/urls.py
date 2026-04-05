from django.urls import include, path

urlpatterns = [
    path("saladbar/", include("saladbar.urls")),
]
