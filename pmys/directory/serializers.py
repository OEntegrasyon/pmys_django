from rest_framework import serializers
from .models import LdapUser, LdapGroup, LdapOrganization

class LdapGroupSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source='ldaporganization.name', read_only=True)

    class Meta:
        model = LdapGroup
        fields = '__all__'

    def get_user_count(self, obj):
        return obj.users.count()

class LdapUserSerializer(serializers.ModelSerializer):
    groups = LdapGroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=LdapGroup.objects.all(),
        source='groups',
        write_only=True
    )
    
    class Meta:
        model = LdapUser
        fields = '__all__'

class LdapOrganizationSerializer(serializers.ModelSerializer):
    group_count = serializers.SerializerMethodField()

    class Meta:
        model = LdapOrganization
        fields = '__all__'

    def get_group_count(self, obj):
        return obj.ldapgroups.count()