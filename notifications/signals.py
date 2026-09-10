from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from orders.models import Order
from payments.models import Payment
from .models import Notification


def _notify(user, titre, message, type_notification, lien=""):
    return Notification.objects.create(
        utilisateur=user,
        titre=titre,
        message=message,
        type_notification=type_notification,
        lien=lien,
    )


@receiver(post_save, sender=Order)
def order_created_notification(sender, instance, created, **kwargs):
    if created:
        _notify(
            instance.utilisateur,
            "Commande enregistrée",
            f"Votre commande #{instance.id} a bien été enregistrée et est en cours de traitement.",
            "commande",
            f"/orders/{instance.id}/",
        )
        for user in User.objects.filter(profile__role__in=("vendeur", "admin")):
            _notify(user, "Nouvelle commande à traiter", f"La commande #{instance.id} attend une prise en charge.", "commande", f"/orders/{instance.id}/")


@receiver(pre_save, sender=Order)
def order_status_changed_notification(sender, instance, **kwargs):
    if instance.id:
        try:
            previous_instance = Order.objects.get(id=instance.id)
            if previous_instance.statut != instance.statut:
                statut_display = instance.get_statut_display()
                type_notification = "livraison" if instance.statut in ("expediee", "livree") else "commande"
                _notify(instance.utilisateur, f"Commande {statut_display.lower()}", f"Votre commande #{instance.id} est maintenant : {statut_display}.", type_notification, f"/orders/{instance.id}/")
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=Payment)
def payment_notification(sender, instance, created, **kwargs):
    if instance.statut == "paye" and getattr(instance, "_became_paid", created):
        _notify(instance.commande.utilisateur, "Paiement confirmé", f"Le paiement de la commande #{instance.commande.id} a été confirmé.", "paiement", f"/orders/{instance.commande.id}/")


@receiver(pre_save, sender=Payment)
def payment_status_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._became_paid = instance.statut == "paye"
        return
    previous = Payment.objects.filter(pk=instance.pk).values_list("statut", flat=True).first()
    instance._became_paid = previous != "paye" and instance.statut == "paye"
