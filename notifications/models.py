from django.db import models
from django.contrib.auth.models import User


class Notification(models.Model):
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    message = models.TextField()

    lu = models.BooleanField(
        default=False
    )

    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Notification pour {self.utilisateur.username} : {self.message[:30]}..."
