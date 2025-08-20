from rest_framework import viewsets
from .models import PolicyType, Policy, PolicyAssignment, PolicyLog
from .serializers import PolicyTypeSerializer, PolicySerializer, PolicyAssignmentSerializer, PolicyLogSerializer

class PolicyTypeViewSet(viewsets.ModelViewSet):
    queryset = PolicyType.objects.all().order_by('name')
    serializer_class = PolicyTypeSerializer

class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all().order_by('name')
    serializer_class = PolicySerializer

class PolicyAssignmentViewSet(viewsets.ModelViewSet):
    queryset = PolicyAssignment.objects.all().order_by('-created_at') # başına '-' koyunca descending oluyormuş yav, sübhanallah
    serializer_class = PolicyAssignmentSerializer

class PolicyLogViewSet(viewsets.ModelViewSet):
    queryset = PolicyLog.objects.all().order_by('-timestamp')
    serializer_class = PolicyLogSerializer
