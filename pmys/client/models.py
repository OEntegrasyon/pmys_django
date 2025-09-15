from django.db import models

class Client(models.Model):
    uuid = models.CharField(max_length=200, unique=True)
    ip_address = models.CharField(max_length=200, blank=True)
    mac_address = models.CharField(max_length=200, blank=True)
    hostname = models.CharField(max_length=200, blank=True)

    # NEW: LDAP yerleşimi
    organization_dn = models.CharField(max_length=512, blank=True, null=True, db_index=True)
    group_dn = models.CharField(max_length=512, blank=True, null=True, db_index=True)

    users_logged_in = models.ManyToManyField('user.User', related_name='clients', blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        # name alanı yoksa görünür bir şey döndürelim
        return self.hostname or self.uuid

class ClientLog(models.Model):
    client = models.ForeignKey(Client, related_name='logs', on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.client} - {self.action} at {self.timestamp}"
