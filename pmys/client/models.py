from django.db import models

from policy.models import Policy

class Client(models.Model):
    uuid = models.CharField(max_length=200, unique=True)
    ip_address = models.CharField(max_length=200, blank=True)
    mac_address = models.CharField(max_length=200, blank=True)
    hostname = models.CharField(max_length=200, blank=True)

    organization_dn = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    group_dn        = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    user_dn         = models.CharField(max_length=512, null=True, blank=True, db_index=True)

    policies= models.ManyToManyField(Policy, related_name='clients', blank=True)

    users_logged_in = models.ManyToManyField('user.User', related_name='clients', blank=True)
    description = models.TextField(blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization_dn"]),
            models.Index(fields=["group_dn"]),
            models.Index(fields=["user_dn"]),
            models.Index(fields=["last_seen"]),
        ]

    def __str__(self):
        return getattr(self, "hostname", None) or str(getattr(self, "uuid", "")) or f"Client#{self.pk}"

class ClientLog(models.Model):
    client = models.ForeignKey(Client, related_name='logs', on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.client} - {self.action} at {self.timestamp}"
