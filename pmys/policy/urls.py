from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PolicyTypeViewSet, PolicyViewSet, PolicyAssignmentViewSet, PolicyLogViewSet, ClientPolicyLogViewSet
app_name='policy'

router = DefaultRouter()
router.register(r'policy_types', PolicyTypeViewSet)
router.register(r'policies', PolicyViewSet)
router.register(r'policy_assignments', PolicyAssignmentViewSet)
router.register(r'policy_logs', PolicyLogViewSet)
router.register(r'client_policy_logs', ClientPolicyLogViewSet, basename='client_policy_log')

urlpatterns = [
    path('', include(router.urls)),
]
