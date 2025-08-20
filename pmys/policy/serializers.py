from rest_framework import serializers
from .models import PolicyType, Policy, PolicyAssignment, PolicyLog
from user.models import User 

class PolicyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyType
        fields = '__all__'

class PolicySerializer(serializers.ModelSerializer):
    policy_type_name = serializers.CharField(source='policy_type.name', read_only=True)
    policy_type_parameters = serializers.JSONField(source='policy_type.parameters', read_only=True)

    class Meta:
        model = Policy
        fields = '__all__'

class PolicyAssignmentSerializer(serializers.ModelSerializer):
    policy_id = serializers.PrimaryKeyRelatedField(
        source='policy', queryset=Policy.objects.all(), write_only=True
    )
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        source='assigned_to', queryset=User.objects.all(), write_only=True
    )

    policy = PolicySerializer(read_only=True)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = PolicyAssignment
        fields = [
            'id',
            'policy_id',
            'assigned_to_id',
            'policy',
            'assigned_to_username',
            'created_at'
        ]

class PolicyLogSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = PolicyLog
        fields = '__all__'
