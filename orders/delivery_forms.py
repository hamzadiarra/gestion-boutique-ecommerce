from django.utils.translation import gettext_lazy
from django import forms
from django.contrib.auth.models import User
from .delivery_models import STATUTS, MOTIFS


class AdresseLivraisonForm(forms.Form):
    numero_rue = forms.IntegerField(required=False, min_value=0, max_value=1000)
    numero_porte = forms.IntegerField(required=False, min_value=0, max_value=1000)
    telephone_livraison = forms.CharField(required=False, max_length=20)


class AffectationForm(forms.Form):
    livreur = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True, profile__role="livreur").order_by("username"))
    commentaire = forms.CharField(required=False, max_length=1000)


class MessageLivraisonForm(forms.Form):
    message = forms.CharField(max_length=1000, strip=True, widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1000, "class": "form-control"}))
    jeton = forms.CharField(widget=forms.HiddenInput)


class ActionLivraisonForm(forms.Form):
    action = forms.ChoiceField(choices=STATUTS)
    motif_echec = forms.ChoiceField(choices=[("", gettext_lazy("Choisir un motif"))] + MOTIFS, required=False)
    commentaire = forms.CharField(required=False, max_length=1000)


class FiltreLivraisonForm(forms.Form):
    statut = forms.ChoiceField(choices=[("", gettext_lazy("Tous les statuts"))] + STATUTS, required=False)
    livreur = forms.ModelChoiceField(queryset=User.objects.filter(profile__role="livreur").order_by("username"), required=False)
    date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    q = forms.CharField(required=False, max_length=150)
    section = forms.ChoiceField(required=False, choices=[("", gettext_lazy("Toutes")), ("a_accepter", gettext_lazy("À accepter")), ("a_affecter", gettext_lazy("À affecter")), ("en_cours", gettext_lazy("En cours")), ("terminees", gettext_lazy("Terminées")), ("echecs", gettext_lazy("Échecs")), ("livrees_jour", gettext_lazy("Livrées aujourd'hui"))])
