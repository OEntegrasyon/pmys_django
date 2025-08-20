from django.db import models

class PolicyType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    parameters = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Policy(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    policy_type = models.ForeignKey(PolicyType, related_name='policies', on_delete=models.CASCADE)
    parameters = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PolicyAssignment(models.Model):
    policy = models.ForeignKey(Policy, related_name='assignments', on_delete=models.CASCADE)
    assigned_to = models.ForeignKey('user.User', related_name='policy_assignments', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.policy.name} assigned to {self.assigned_to.username} on {self.created_at}"

class PolicyLog(models.Model):
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.policy.name} - {self.action} at {self.timestamp}"
