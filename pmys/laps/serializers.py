from rest_framework import serializers
from client.models import Client, ClientLog
from .models import LapsPolicy, LapsAssignment,LapsAccessLog

class LapsPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = LapsPolicy
        fields = "__all__"

class LapsAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LapsAssignment
        fields = ["id", "target_type", "target_id", "policy", "account_name_override", "enabled", "created_at"]

class ClientLiteSerializer(serializers.ModelSerializer):
    last_seen = serializers.SerializerMethodField()
    has_secret = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id","uuid","hostname","ip_address","mac_address",
            "is_active","created_at","last_seen","has_secret","expires_at",
        ]

    def get_last_seen(self, obj: Client):
        log = ClientLog.objects.filter(client=obj).order_by("-timestamp").first()
        return log.timestamp if log else None

    def get_has_secret(self, obj: Client):
        try:
            from .models import LapsSecret
            return LapsSecret.objects.filter(client=obj).exists()
        except Exception:
            return False

    def get_expires_at(self, obj: Client):
        try:
            from .models import LapsSecret
            s = LapsSecret.objects.filter(client=obj).order_by("-version").first()
            return s.expires_at if s else None
        except Exception:
            return None


class LapsPolicySlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = LapsPolicy
        fields = [
            "id","name","description","account_name","length","use_upper","use_lower","use_digits","use_symbols",
            "rotation_days","view_ttl_seconds","history_keep","backup_directory","post_auth_action",
            "post_auth_delay_minutes","enforce_max_age","rotate_on_unlock","allow_plaintext_backup",
            "rename_admin","rename_admin_to","readers","disabled","created_at"
        ]

class LapsAccessLogSerializer(serializers.ModelSerializer):
    client_id = serializers.IntegerField(source="client.id", read_only=True)
    client_uuid = serializers.CharField(source="client.uuid", read_only=True)
    client_hostname = serializers.CharField(source="client.hostname", read_only=True)

    account_name = serializers.SerializerMethodField()
    secret_version = serializers.SerializerMethodField()

    class Meta:
        model = LapsAccessLog
        fields = [
            "id",
            "action",
            "requested_by",
            "result",
            "created_at",
            "client_id",
            "client_uuid",
            "client_hostname",
            "account_name",
            "secret_version",
            "reason",
            "ticket",
            "ip",
            "user_agent",
        ]

    def get_account_name(self, obj):
        return getattr(getattr(obj, "secret", None), "account_name", "")

    def get_secret_version(self, obj):
        return getattr(getattr(obj, "secret", None), "version", None)