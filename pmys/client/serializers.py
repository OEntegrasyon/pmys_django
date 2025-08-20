from rest_framework import serializers
from .models import Client, ClientLog

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class ClientLogSerializer(serializers.ModelSerializer):
    client_uuid = serializers.CharField(source='client.uuid', read_only=True)
    client_hostname = serializers.CharField(source='client.hostname', read_only=True)

    class Meta:
        model = ClientLog
        fields = '__all__'
        read_only_fields = ['client_uuid', 'client_hostname']
