from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils.translation import gettext
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
            gettext("Commande enregistrée"),
            gettext("Votre commande #%(id)s a bien été enregistrée et est en cours de traitement.") % {"id": instance.id},
            "commande",
            f"/orders/{instance.id}/",
        )
        for user in User.objects.filter(profile__role__in=("vendeur", "admin")):
            _notify(user, gettext("Nouvelle commande à traiter"), gettext("La commande #%(id)s attend une prise en charge.") % {"id": instance.id}, "commande", f"/orders/{instance.id}/")


@receiver(pre_save, sender=Order)
def order_status_changed_notification(sender, instance, **kwargs):
    if getattr(instance, "_delivery_notification_managed", False):
        return
    if instance.id:
        try:
            previous_instance = Order.objects.get(id=instance.id)
            if previous_instance.statut != instance.statut:
                statut_display = instance.get_statut_display()
                type_notification = "livraison" if instance.statut in ("expediee", "livree") else "commande"
                _notify(instance.utilisateur, gettext("Commande %(status)s") % {"status": statut_display.lower()}, gettext("Votre commande #%(id)s est maintenant : %(status)s.") % {"id": instance.id, "status": statut_display}, type_notification, f"/orders/{instance.id}/")
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=Payment)
def payment_notification(sender, instance, created, **kwargs):
    if instance.statut == "paye" and getattr(instance, "_became_paid", created):
        _notify(instance.commande.utilisateur, gettext("Paiement confirmé"), gettext("Le paiement de la commande #%(id)s a été confirmé.") % {"id": instance.commande.id}, "paiement", f"/orders/{instance.commande.id}/")


@receiver(pre_save, sender=Payment)
def payment_status_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._became_paid = instance.statut == "paye"
        return
    previous = Payment.objects.filter(pk=instance.pk).values_list("statut", flat=True).first()
    instance._became_paid = previous != "paye" and instance.statut == "paye"
