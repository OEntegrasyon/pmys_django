from rest_framework import viewsets
from .models import PolicyType, Policy, PolicyAssignment, PolicyLog
from .serializers import PolicyTypeSerializer, PolicySerializer, PolicyAssignmentSerializer, PolicyLogSerializer
from utils.pagination import OptionalPagination

class PolicyTypeViewSet(viewsets.ModelViewSet):
    queryset = PolicyType.objects.all().order_by('name')
    serializer_class = PolicyTypeSerializer
    pagination_class = OptionalPagination
    
class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all().order_by('name')
    serializer_class = PolicySerializer
    pagination_class = OptionalPagination

class PolicyAssignmentViewSet(viewsets.ModelViewSet):
    queryset = PolicyAssignment.objects.select_related('policy', 'assigned_to').all().order_by('-created_at')
    serializer_class = PolicyAssignmentSerializer

class PolicyLogViewSet(viewsets.ModelViewSet):
    queryset = PolicyLog.objects.all().order_by('-timestamp')
    serializer_class = PolicyLogSerializer