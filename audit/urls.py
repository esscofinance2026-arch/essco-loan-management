from django.urls import path
from . import views as essco

urlpatterns = [
    path("audit-log/", essco.logs, name="logs"),
    path('audit/log/<str:pk>/', essco.logsview, name='logsview'),
]