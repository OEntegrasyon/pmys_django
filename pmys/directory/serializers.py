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

# ----- Import payload şeması -----
class ImportUserSerializer(serializers.Serializer):
    uid = serializers.CharField()
    dn = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    targetDn = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    primaryGroup = serializers.CharField(required=False, allow_blank=True)
    groups = serializers.ListField(child=serializers.CharField(), required=False)
    givenName = serializers.CharField(required=False, allow_blank=True)
    sn = serializers.CharField(required=False, allow_blank=True)
    mail = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    userPassword = serializers.CharField(required=False, allow_blank=True)
    uidNumber = serializers.IntegerField(required=False)
    gidNumber = serializers.IntegerField(required=False)
    homeDirectory = serializers.CharField(required=False, allow_blank=True)
    loginShell = serializers.CharField(required=False, allow_blank=True)
    isActive = serializers.BooleanField(required=False, default=True)

class ImportGroupSerializer(serializers.Serializer):
    cn = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    dn = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    members = serializers.ListField(child=serializers.CharField(), required=False)
    memberUids = serializers.ListField(child=serializers.CharField(), required=False)

    def validate(self, data):
        if not data.get("cn"):
            dn = data.get("dn")
            if data.get("name"):
                data["cn"] = data["name"]
            elif isinstance(dn, str) and dn.lower().startswith("cn="):
                data["cn"] = dn.split(",", 1)[0].split("=", 1)[1]
            else:
                raise serializers.ValidationError("cn/name/dn alanlarından en az biri gerekli")
        return data

class ImportOrganizationSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    groups = ImportGroupSerializer(many=True, required=False)
    users = ImportUserSerializer(many=True, required=False)

class ImportPayloadSerializer(serializers.Serializer):
    organizations = ImportOrganizationSerializer(many=True)

class ImportOptionsSerializer(serializers.Serializer):
    autoCreateMissingGroups = serializers.BooleanField(required=False, default=False)
    lockMethodOverride = serializers.ChoiceField(choices=["ppolicy","shadow"], required=False)
    dryRun = serializers.BooleanField(required=False, default=True)
    preserveExistingDn = serializers.BooleanField(required=False, default=False)

class ValidateRequestSerializer(serializers.Serializer):
    payload = ImportPayloadSerializer(required=False)
    jobId = serializers.CharField(required=False)
    options = ImportOptionsSerializer(required=False)

class ApplyRequestSerializer(serializers.Serializer):
    applyToken = serializers.CharField()
    options = serializers.DictField(required=False)
