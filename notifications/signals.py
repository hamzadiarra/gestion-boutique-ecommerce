from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from orders.models import Order
from payments.models import Payment
from .models import Notification


@receiver(post_save, sender=Order)
def order_created_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            utilisateur=instance.utilisateur,
            message=f"Votre commande #{instance.id} a été enregistrée avec succès ! 📦 Elle est en cours de traitement."
        )


@receiver(pre_save, sender=Order)
def order_status_changed_notification(sender, instance, **kwargs):
    if instance.id:
        try:
            previous_instance = Order.objects.get(id=instance.id)
            if previous_instance.statut != instance.statut:
                # Le statut a changé
                statut_display = instance.get_statut_display()
                Notification.objects.create(
                    utilisateur=instance.utilisateur,
                    message=f"Le statut de votre commande #{instance.id} a changé : « {statut_display} ». 🚚"
                )
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=Payment)
def payment_notification(sender, instance, created, **kwargs):
    # Si le paiement passe au statut payé
    if instance.statut == "paye":
        Notification.objects.create(
            utilisateur=instance.commande.utilisateur,
            message=f"Paiement de {instance.montant} FCFA validé pour la commande #{instance.commande.id}. Merci de votre confiance ! 💳"
        )
