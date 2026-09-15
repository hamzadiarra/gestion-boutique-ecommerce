from django.utils.translation import gettext_lazy
from django import forms
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from .finance_forms import StyledForm
from .finance_models import TYPES_COMPTE
from .models import ClotureFinanciere, CompteFinancier


class PrivateClotureFileInput(forms.ClearableFileInput):
    template_name = "dashboard/clotures/_private_file_input.html"

    def is_initial(self, value):
        # Private storage deliberately has no public URL. Never resolve value.url.
        return bool(value)

    def _render(self, template_name, context, renderer=None):
        # Use the project template loader without changing every form renderer.
        return mark_safe(render_to_string(template_name, context))


class ClotureForm(StyledForm, forms.ModelForm):
    class Meta:
        model = ClotureFinanciere
        fields = ["compte", "date_cloture", "solde_constate", "commentaire", "justificatif"]
        widgets = {"date_cloture": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "commentaire": forms.Textarea(attrs={"rows": 4}),
                   "justificatif": PrivateClotureFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.webp"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compte"].queryset = CompteFinancier.objects.order_by("-actif", "nom", "pk")
        self.fields["compte"].label_from_instance = lambda account: f"{account.nom} ({account.devise})" + (" - inactif, historique" if not account.actif else "")
        self.fields["justificatif"].help_text = gettext_lazy("PDF ou image vérifiée, 5 Mo maximum, stockage privé.")

    def clean_date_cloture(self):
        day = self.cleaned_data["date_cloture"]
        if day > timezone.localdate():
            raise forms.ValidationError(gettext_lazy("La date de clôture ne peut pas être dans le futur."))
        return day


class ClotureFiltreForm(StyledForm, forms.Form):
    compte = forms.ModelChoiceField(queryset=CompteFinancier.objects.all(), required=False)
    type_compte = forms.ChoiceField(choices=[("", gettext_lazy("Tous les types"))] + TYPES_COMPTE, required=False)
    date_debut = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    statut = forms.ChoiceField(choices=[("", gettext_lazy("Tous les statuts"))] + ClotureFinanciere.STATUTS, required=False)
    ecart = forms.ChoiceField(choices=[("", gettext_lazy("Tous les écarts")), ("conforme", gettext_lazy("Conforme")), ("positif", gettext_lazy("Excédent constaté")), ("negatif", gettext_lazy("Manquant constaté"))], required=False)

    def clean(self):
        data = super().clean()
        if data.get("date_debut") and data.get("date_fin") and data["date_debut"] > data["date_fin"]:
            raise forms.ValidationError(gettext_lazy("Période invalide."))
        return data
