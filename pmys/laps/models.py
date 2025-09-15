from django.db import models
import uuid as _uuid

class LapsPolicy(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    account_name = models.CharField(max_length=120, default="Administrator")
    length = models.PositiveIntegerField(default=16)
    use_upper = models.BooleanField(default=True)
    use_lower = models.BooleanField(default=True)
    use_digits = models.BooleanField(default=True)
    use_symbols = models.BooleanField(default=True)

    rotation_days = models.PositiveIntegerField(default=30)
    view_ttl_seconds = models.PositiveIntegerField(default=15)
    history_keep = models.PositiveIntegerField(default=10)

    BACKUP_CHOICES = (("db", "Server DB"), ("none", "Disabled"))
    backup_directory = models.CharField(max_length=10, choices=BACKUP_CHOICES, default="db")

    POST_AUTH_CHOICES = (
        ("none", "None"), ("reset", "ResetPassword"),
        ("logoff", "Logoff"), ("reboot", "Reboot"), ("shutdown", "Shutdown"),
    )
    post_auth_action = models.CharField(max_length=12, choices=POST_AUTH_CHOICES, default="none")
    post_auth_delay_minutes = models.PositiveIntegerField(default=0)

    enforce_max_age = models.BooleanField(default=True)
    rotate_on_unlock = models.BooleanField(default=False)
    allow_plaintext_backup = models.BooleanField(default=False)
    rename_admin = models.BooleanField(default=False)
    rename_admin_to = models.CharField(max_length=120, blank=True, default="")

    readers = models.JSONField(default=list, blank=True)

    disabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LapsAssignment(models.Model):
    TARGET_CHOICES = (("client","Client"),("group","Group"),("org","Organization"))
    target_type = models.CharField(max_length=10, choices=TARGET_CHOICES)
    target_id = models.CharField(max_length=128)
    policy = models.ForeignKey(LapsPolicy, on_delete=models.CASCADE, related_name="assignments")
    account_name_override = models.CharField(max_length=120, blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["target_type", "target_id"])]
        unique_together = ("target_type", "target_id", "policy", "account_name_override")

    def __str__(self):
        return f"{self.target_type}:{self.target_id} -> {self.policy.name}"


class LapsSecret(models.Model):
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="laps_secrets")
    account_name = models.CharField(max_length=120, default="Administrator")
    password_encrypted = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    last_rotated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    policy = models.ForeignKey(LapsPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="secrets")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("client", "account_name")]

    def __str__(self):
        return f"{self.client_id}::{self.account_name} v{self.version}"


class LapsSecretHistory(models.Model):
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="laps_secret_history")
    account_name = models.CharField(max_length=120, default="Administrator")
    password_encrypted = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    rotated_at = models.DateTimeField(auto_now_add=True)


class LapsAccessLog(models.Model):
    ACTIONS = (
        ("rotate", "rotate"),
        ("view", "view"),
        ("report", "report"),
        ("bulk_rotate", "bulk_rotate"),
        ("error", "error"),
    )
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="laps_logs")
    secret = models.ForeignKey("laps.LapsSecret", null=True, blank=True, on_delete=models.SET_NULL, related_name="access_logs")
    action = models.CharField(max_length=32, choices=ACTIONS)
    requested_by = models.CharField(max_length=120, blank=True, default="")
    result = models.CharField(max_length=200, blank=True, default="")
    # ── yeni alanlar
    reason = models.TextField(blank=True, default="")
    ticket = models.CharField(max_length=120, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

class LapsAccessGrant(models.Model):
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="laps_grants")
    def generate_token():
        return _uuid.uuid4().hex
    
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    actor = models.CharField(max_length=120, blank=True, default="")     # request.user ya da X-Actor
    reason = models.TextField(blank=True, default="")
    ticket = models.CharField(max_length=120, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self, now=None):
        from django.utils import timezone as djtz
        now = now or djtz.now()
        return (self.used_at is None) and (self.expires_at >= now)