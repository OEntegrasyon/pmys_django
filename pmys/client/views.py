from rest_framework import viewsets
from .models import Client, ClientLog
from .serializers import ClientSerializer, ClientLogSerializer
from django.db.models import Q

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('hostname')
    serializer_class = ClientSerializer

class ClientLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClientLog.objects.select_related('client').exclude(
        Q(action="policy_assigned") | Q(action="policy_removed")
    ).order_by('-timestamp')
    serializer_class = ClientLogSerializer

class ClientPolicyAssignmentLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Sadece istemci politika atama/kaldırma loglarını
    (policy_assigned, policy_removed) döndürür.
    """
    queryset = ClientLog.objects.select_related('client').filter(
        Q(action="policy_assigned") | Q(action="policy_removed")
    ).order_by('-timestamp')
    serializer_class = ClientLogSerializer
