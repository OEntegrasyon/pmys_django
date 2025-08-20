from django.db import models

class Client(models.Model):
    uuid = models.CharField(max_length=200)
    ip_address = models.CharField(max_length=200, blank=True)
    mac_address = models.CharField(max_length=200, blank=True)
    hostname = models.CharField(max_length=200, blank=True)
    users_logged_in = models.ManyToManyField('user.User', related_name='clients', blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class ClientLog(models.Model):
    client = models.ForeignKey(Client, related_name='logs', on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.client.name} - {self.action} at {self.timestamp}"