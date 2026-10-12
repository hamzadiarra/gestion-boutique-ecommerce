from django import forms


class SignatureForm(forms.Form):
    receptionnaire = forms.CharField(label="Nom du réceptionnaire", min_length=2, max_length=150)
    signature = forms.CharField(max_length=180000, widget=forms.HiddenInput)
    information_acceptee = forms.BooleanField(label="Le destinataire a lu la notice et confirme sa signature comme preuve de réception.")


class DerogationForm(forms.Form):
    receptionnaire = forms.CharField(label="Nom du réceptionnaire", min_length=2, max_length=150)
    motif = forms.CharField(min_length=10, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class RetourForm(forms.Form):
    type = forms.ChoiceField(choices=[("confirmation", "Je confirme la réception"), ("probleme", "Je signale un problème")])
    note = forms.TypedChoiceField(label="Note (facultative)", choices=[("", "Sans note")]+[(n, str(n)) for n in range(1, 6)], coerce=int, empty_value=None, required=False)
    commentaire = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class TarifForm(forms.Form):
    mode = forms.ChoiceField(label="Type de livraison", choices=[("standard", "Standard"), ("express", "Express")], widget=forms.Select(attrs={"class": "form-select"}))
    zone = forms.CharField(label="Ville ou zone de livraison", max_length=100, required=False, help_text="Saisissez la ville du checkout (ex. Bamako). Laissez vide pour toutes les villes.", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Bamako"}))
    montant = forms.DecimalField(label="Montant en FCFA", min_value=0, max_value=99999999.99, max_digits=10, decimal_places=2, widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "decimal", "placeholder": "Ex. 1500"}))


class DecisionTarifForm(forms.Form):
    statut = forms.ChoiceField(choices=[("approuve", "Approuver"), ("refuse", "Refuser"), ("desactive", "Désactiver")])
    motif = forms.CharField(label="Motif de la décision", min_length=5, max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Expliquez votre décision"}))
