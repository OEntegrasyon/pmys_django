from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ClientsListView, ClientSecretByKeyView, ClientRotateByKeyView,
    ClientsBulkRotateView, ClientHistoryByKeyView, GrantCreateView,
    PolicyViewSet, LogsListView,
    client_accounts, client_effective_policy, create_assignment, list_assignments, delete_assignment
)

router = DefaultRouter()
router.register(r'policies', PolicyViewSet, basename='laps-policy')

urlpatterns = [
    path('clients/', ClientsListView.as_view()),
    path('clients/<str:key>/secret/', ClientSecretByKeyView.as_view()),
    path('clients/<str:key>/rotate/', ClientRotateByKeyView.as_view()),
    path('clients/<str:key>/history/', ClientHistoryByKeyView.as_view()),
    path('clients/bulk-rotate/', ClientsBulkRotateView.as_view()),

    path('clients/<str:key>/accounts/', client_accounts),
    path('clients/<str:key>/effective-policy/', client_effective_policy),
    path('assignments/', create_assignment),        
    path('assignments/list/', list_assignments),      
    path('assignments/<int:pk>/', delete_assignment), 
    path('logs/', LogsListView.as_view()),
    path('grants/', GrantCreateView.as_view()),
]

urlpatterns += router.urls
