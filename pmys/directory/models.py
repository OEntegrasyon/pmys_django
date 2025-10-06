from django.db import models
from policy import models as policy_models

class LdapUser(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    policies = models.ManyToManyField(policy_models.Policy, related_name='ldapusers', blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

class LdapGroup(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    users = models.ManyToManyField(LdapUser, related_name='ldapgroups', blank=True)
    organization = models.ForeignKey('LdapOrganization', related_name='ldapgroups', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class LdapOrganization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    