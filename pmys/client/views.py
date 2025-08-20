from rest_framework import viewsets
from .models import Client, ClientLog
from .serializers import ClientSerializer, ClientLogSerializer

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('hostname')
    serializer_class = ClientSerializer

class ClientLogViewSet(viewsets.ModelViewSet):
    queryset = ClientLog.objects.all().order_by('-timestamp')
    serializer_class = ClientLogSerializer

