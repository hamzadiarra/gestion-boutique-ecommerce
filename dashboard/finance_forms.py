from django.utils.translation import gettext_lazy
from decimal import Decimal
from django import forms
from django.utils import timezone
from .finance_models import CompteFinancier, SENS, TYPES_COMPTE, TYPES_MOUVEMENT


class StyledForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control")


class CompteForm(StyledForm, forms.ModelForm):
    class Meta:
        model = CompteFinancier
        fields = ["nom", "type_compte", "devise", "solde_initial", "actif", "est_par_defaut", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class OperationForm(StyledForm, forms.Form):
    montant = forms.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    date = forms.DateTimeField(initial=timezone.now, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    motif = forms.CharField(max_length=255, widget=forms.Textarea(attrs={"rows": 3}))
    jeton = forms.CharField(widget=forms.HiddenInput)


class TransfertForm(OperationForm):
    compte_source = forms.ModelChoiceField(queryset=CompteFinancier.objects.filter(actif=True))
    compte_destination = forms.ModelChoiceField(queryset=CompteFinancier.objects.filter(actif=True))

    def clean(self):
        data = super().clean()
        source, destination = data.get("compte_source"), data.get("compte_destination")
        if source and destination and (source.pk == destination.pk or source.devise != destination.devise):
            raise forms.ValidationError(gettext_lazy("Choisissez deux comptes distincts de même devise."))
        return data


class AjustementForm(OperationForm):
    compte = forms.ModelChoiceField(queryset=CompteFinancier.objects.filter(actif=True))
    sens = forms.ChoiceField(choices=SENS)


class MouvementFiltreForm(StyledForm, forms.Form):
    q = forms.CharField(required=False, label=gettext_lazy("Recherche"))
    compte = forms.ModelChoiceField(queryset=CompteFinancier.objects.all(), required=False)
    type_compte = forms.ChoiceField(choices=[("", gettext_lazy("Tous les types de compte"))] + TYPES_COMPTE, required=False)
    type_mouvement = forms.ChoiceField(choices=[("", gettext_lazy("Tous les mouvements"))] + TYPES_MOUVEMENT, required=False)
    sens = forms.ChoiceField(choices=[("", gettext_lazy("Entrées et sorties"))] + SENS, required=False)
    date_debut = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if data.get("date_debut") and data.get("date_fin") and data["date_debut"] > data["date_fin"]:
            raise forms.ValidationError(gettext_lazy("La date de fin doit suivre la date de début."))
        return data
