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
    mode = forms.ChoiceField(choices=[("standard", "Standard"), ("express", "Express")])
    zone = forms.CharField(label="Ville (vide pour toutes les villes)", max_length=100, required=False)
    montant = forms.DecimalField(label="Montant en FCFA", min_value=0, max_value=99999999.99, max_digits=10, decimal_places=2)
