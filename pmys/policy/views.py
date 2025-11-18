from rest_framework import viewsets
from .models import PolicyType, Policy, PolicyAssignment, PolicyLog
from .serializers import PolicyTypeSerializer, PolicySerializer, PolicyAssignmentSerializer, PolicyLogSerializer
from utils.pagination import OptionalPagination
from django.db.models import Q

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

class PolicyLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PolicyLog.objects.exclude(
        details__source='client'
    ).order_by('-timestamp')
    serializer_class = PolicyLogSerializer

class ClientPolicyLogViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = PolicyLog.objects.filter(
        details__source='client'
    ).order_by('-timestamp')
    serializer_class = PolicyLogSerializer