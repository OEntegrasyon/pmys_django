from rest_framework import serializers
from .models import User, Group, Organization

class GroupSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = Group
        fields = '__all__'

    def get_user_count(self, obj):
        return obj.users.count()

class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        source='groups',
        write_only=True
    )
    
    class Meta:
        model = User
        fields = '__all__'

class OrganizationSerializer(serializers.ModelSerializer):
    group_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = '__all__'

    def get_group_count(self, obj):
        return obj.groups.count()