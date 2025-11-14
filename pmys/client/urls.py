from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientViewSet, ClientLogViewSet, ClientPolicyAssignmentLogViewSet
app_name='client'

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'client_logs', ClientLogViewSet)
router.register(r'client_policy_assignment_logs', ClientPolicyAssignmentLogViewSet, basename='client_policy_assignment_log')


urlpatterns = [
    path('', include(router.urls)),
]
