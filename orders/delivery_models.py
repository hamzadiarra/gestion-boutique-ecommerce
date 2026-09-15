from django.utils.translation import gettext_lazy
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

STATUTS = [("a_affecter", gettext_lazy("À affecter")), ("affectee", gettext_lazy("Affectée")), ("acceptee", gettext_lazy("Acceptée")),
           ("en_preparation", gettext_lazy("En préparation")), ("prete", gettext_lazy("Prête")), ("en_route", gettext_lazy("En route")),
           ("arrive", gettext_lazy("Arrivé")), ("livree", gettext_lazy("Livrée")), ("echec", gettext_lazy("Échec de livraison")), ("annulee", gettext_lazy("Annulée"))]
MOTIFS = [("client_absent", gettext_lazy("Client absent")), ("adresse_introuvable", gettext_lazy("Adresse introuvable")),
          ("client_injoignable", gettext_lazy("Client injoignable")), ("refus_client", gettext_lazy("Refus client")), ("autre", gettext_lazy("Autre"))]
TERMINAUX = {"livree", "echec", "annulee"}


class TraceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(gettext_lazy("Utilisez les services de livraison."))

    def delete(self):
        raise ValidationError(gettext_lazy("L'historique de livraison est conservé."))


class TraceModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    objects = TraceQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(gettext_lazy("Trace immuable : utilisez une action métier."))
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(gettext_lazy("Aucune suppression de livraison ou de discussion."))


class Livraison(TraceModel):
    STATUTS = STATUTS
    reference = models.CharField(max_length=45, unique=True, editable=False)
    commande = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="livraison")
    livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="livraisons_affectees")
    statut = models.CharField(max_length=20, choices=STATUTS, default="a_affecter")
    date_affectation = models.DateTimeField(null=True, blank=True)
    date_acceptation = models.DateTimeField(null=True, blank=True)
    date_prete = models.DateTimeField(null=True, blank=True)
    date_depart = models.DateTimeField(null=True, blank=True)
    date_arrivee = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    motif_echec = models.CharField(max_length=30, choices=MOTIFS, blank=True)
    commentaire_echec = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["livreur", "statut"], name="livraison_livreur_statut_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(statut__in=[s[0] for s in STATUTS]), name="livraison_statut_valide")]

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.reference = f"TMP-{uuid.uuid4().hex}"
            self.statut = "a_affecter"
            self.livreur = None
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"LIV-{timezone.localtime(self.created_at).year}-{self.pk:06d}"
            models.QuerySet(model=type(self), using=self._state.db).filter(pk=self.pk).update(reference=self.reference)

    def __str__(self):
        return self.reference

    @property
    def terminee(self):
        return self.statut in TERMINAUX


class HistoriqueLivraison(TraceModel):
    livraison = models.ForeignKey(Livraison, on_delete=models.PROTECT, related_name="historique")
    ancien_statut = models.CharField(max_length=20, choices=STATUTS, blank=True)
    nouveau_statut = models.CharField(max_length=20, choices=STATUTS)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="actions_livraison")
    ancien_livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="anciennes_affectations")
    nouveau_livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="nouvelles_affectations")
    commentaire = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]


class MessageLivraison(TraceModel):
    livraison = models.ForeignKey(Livraison, on_delete=models.PROTECT, related_name="messages")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="messages_livraison")
    message = models.CharField(max_length=1000)
    cle_envoi = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ["created_at", "pk"]

    def clean(self):
        self.message = self.message.strip()
        if not self.message:
            raise ValidationError({"message": gettext_lazy("Écrivez un message non vide.")})


class LectureLivraison(models.Model):
    livraison = models.ForeignKey(Livraison, on_delete=models.CASCADE, related_name="lectures")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lectures_livraison")
    dernier_message_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["livraison", "utilisateur"], name="lecture_unique_livraison_user")]
