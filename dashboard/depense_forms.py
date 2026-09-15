from django.utils.translation import gettext_lazy
from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from .models import CategorieDepense, Depense


class DepenseForm(forms.ModelForm):
    class Meta:
        model = Depense
        fields = ["date_depense", "categorie", "libelle", "montant", "moyen_paiement", "beneficiaire", "description", "justificatif"]
        labels = {"date_depense": "Date de dépense", "categorie": "Catégorie", "libelle": "Libellé", "montant": "Montant", "moyen_paiement": "Moyen de paiement", "beneficiaire": "Bénéficiaire", "description": "Description", "justificatif": "Justificatif"}
        widgets = {
            "date_depense": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "montant": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "justificatif": forms.FileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.webp"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = Q(actif=True)
        if self.instance.pk:
            categories |= Q(pk=self.instance.categorie_id)
        self.fields["categorie"].queryset = CategorieDepense.objects.filter(categories)
        self.fields["justificatif"].help_text = gettext_lazy("PDF, JPG/JPEG, PNG ou WebP, 5 Mo maximum. Téléchargement réservé au comptable et à l'administrateur.")
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"


class CategorieDepenseForm(forms.ModelForm):
    class Meta:
        model = CategorieDepense
        fields = ["nom", "description", "actif"]
        labels = {"nom": "Nom", "description": "Description", "actif": "Catégorie active"}
        widgets = {"nom": forms.TextInput(attrs={"class": "form-control"}), "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}), "actif": forms.CheckboxInput(attrs={"class": "form-check-input"})}


class DepenseFiltreForm(forms.Form):
    q = forms.CharField(required=False, max_length=200, label=gettext_lazy("Recherche"), widget=forms.TextInput(attrs={"placeholder": gettext_lazy("Référence, libellé, bénéficiaire...")}))
    date_debut = forms.DateField(required=False, label=gettext_lazy("Du"), widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(required=False, label=gettext_lazy("Au"), widget=forms.DateInput(attrs={"type": "date"}))
    categorie = forms.ModelChoiceField(required=False, queryset=CategorieDepense.objects.all(), label=gettext_lazy("Catégorie"), empty_label=gettext_lazy("Toutes les catégories"))
    moyen_paiement = forms.ChoiceField(required=False, choices=[("", gettext_lazy("Tous les moyens"))] + Depense.MOYENS_PAIEMENT, label=gettext_lazy("Moyen de paiement"))
    statut = forms.ChoiceField(required=False, choices=[("", gettext_lazy("Tous les statuts"))] + Depense.STATUTS, label=gettext_lazy("Statut"))
    cree_par = forms.ModelChoiceField(required=False, queryset=User.objects.none(), label=gettext_lazy("Créateur"), empty_label=gettext_lazy("Tous les créateurs"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cree_par"].queryset = User.objects.filter(depenses_creees__isnull=False).distinct().order_by("username")
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_debut"), cleaned.get("date_fin")
        if start and end and start > end:
            raise forms.ValidationError(gettext_lazy("La date de début doit précéder la date de fin."))
        return cleaned
