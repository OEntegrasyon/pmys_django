from rest_framework import serializers
from policy.models import Policy
from policy.serializers import PolicySerializer
from .models import Client, ClientLog

class ClientSerializer(serializers.ModelSerializer):
    policies = PolicySerializer(many=True, read_only=True)
    policy_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Policy.objects.all(),
        source='policies',
        write_only=True,
        required=False 
    )
    class Meta:
        model = Client
        fields = [
            'id', 'uuid', 'ip_address', 'mac_address', 'hostname',
            'organization_dn', 'group_dn', 'user_dn', 'users_logged_in',
            'description', 'last_seen', 'created_at', 'is_active',
            'policies', 'policy_ids' 
        ]
        read_only_fields = ['created_at']

class ClientLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "uuid", "hostname", "is_active", "last_seen"]

class ClientLogSerializer(serializers.ModelSerializer):
    client_uuid = serializers.CharField(source='client.uuid', read_only=True)
    client_hostname = serializers.CharField(source='client.hostname', read_only=True)

    class Meta:
        model = ClientLog
        fields = '__all__'
        read_only_fields = ['client_uuid', 'client_hostname', 'timestamp']
