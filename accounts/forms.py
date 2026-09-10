from django import forms
from .models import Profile


class ProfileForm(forms.ModelForm):

    class Meta:

        model = Profile

        fields = [
            "telephone",
            "adresse",
            "ville",
            "code_postal",
            "photo",
        ]


        widgets = {

            "telephone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Téléphone"
                }
            ),


            "adresse": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Adresse",
                    "rows": 3
                }
            ),


            "ville": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ville"
                }
            ),


            "code_postal": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Code postal"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telephone"].label = "Téléphone"
        self.fields["adresse"].label = "Adresse de livraison"
        self.fields["ville"].label = "Ville"
        self.fields["code_postal"].label = "Code postal"
        self.fields["photo"].label = "Photo de profil"
