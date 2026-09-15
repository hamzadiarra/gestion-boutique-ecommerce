from django.utils.translation import gettext_lazy
from django import forms
from django.core.exceptions import ValidationError
from pathlib import Path
from PIL import Image
from .models import Profile


MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_profile_photo(uploaded_photo):
    if not uploaded_photo:
        return
    if uploaded_photo.size > MAX_PROFILE_PHOTO_BYTES:
        raise ValidationError(gettext_lazy("La photo doit peser 5 Mo maximum."))
    if Path(uploaded_photo.name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValidationError(
            gettext_lazy("Format non accepté. Utilisez une image JPG, JPEG, PNG ou WebP.")
        )
    if getattr(uploaded_photo, "content_type", "") not in ALLOWED_PROFILE_PHOTO_TYPES:
        raise ValidationError(gettext_lazy("Format non accepté. Utilisez une image JPG, JPEG, PNG ou WebP."))
    try:
        with Image.open(uploaded_photo) as image:
            image.verify()
        uploaded_photo.seek(0)
    except (OSError, Image.UnidentifiedImageError):
        raise ValidationError(gettext_lazy("Le fichier envoyé n'est pas une image valide."))


class ProfileForm(forms.ModelForm):

    first_name = forms.CharField(label=gettext_lazy("Prénom"), max_length=150)
    last_name = forms.CharField(label=gettext_lazy("Nom"), max_length=150)
    email = forms.EmailField(label=gettext_lazy("Adresse e-mail"))

    class Meta:

        model = Profile

        fields = [
            "first_name",
            "last_name",
            "email",
            "telephone",
            "adresse",
            "ville",
            "code_postal",
            "date_naissance",
            "genre",
            "photo",
        ]


        widgets = {

            "telephone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": gettext_lazy("Téléphone")
                }
            ),


            "adresse": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": gettext_lazy("Adresse"),
                    "rows": 3
                }
            ),


            "ville": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": gettext_lazy("Ville")
                }
            ),


            "code_postal": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": gettext_lazy("Ex. Porte 12 ou repère visible")
                }
            ),
            "photo": forms.FileInput(attrs={
                "class": "profile-photo-input",
                "accept": "image/jpeg,image/png,image/webp",
            }),
            "date_naissance": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "lieu_naissance": forms.TextInput(attrs={"class": "form-control", "placeholder": gettext_lazy("Ville ou localité")}),
            "genre": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.instance.utilisateur.first_name
        self.fields["last_name"].initial = self.instance.utilisateur.last_name
        self.fields["email"].initial = self.instance.utilisateur.email
        for name in ("first_name", "last_name", "email"):
            self.fields[name].widget.attrs.update({"class": "form-control"})
        self.fields["telephone"].label = gettext_lazy("Téléphone")
        self.fields["adresse"].label = gettext_lazy("Quartier / Rue / Avenue")
        self.fields["ville"].label = gettext_lazy("Ville")
        self.fields["code_postal"].label = gettext_lazy("Repère")
        self.fields["photo"].label = gettext_lazy("Photo de profil")
        self.fields["photo"].validators.append(validate_profile_photo)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        queryset = self.instance.utilisateur.__class__.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.utilisateur_id)
        if queryset.exists():
            raise ValidationError(
                gettext_lazy("Cette adresse e-mail est déjà utilisée.")
            )
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.utilisateur
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["first_name", "last_name", "email"])
            profile.save()
        return profile
