from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class VerificationToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=128, unique=True)
    verified = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.user} - {self.verified}"

class SentMessage(models.Model):
    esp = models.CharField(max_length=100)
    message_id = models.CharField(max_length=100, null=True, blank=True)
    email = models.CharField(max_length=100)
    subject = models.CharField(max_length=250)
    body = models.TextField(max_length=5000)
    status = models.CharField(max_length=100)
    timestamp = models.DateTimeField()
    