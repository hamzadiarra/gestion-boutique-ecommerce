from django.utils.translation import gettext_lazy
from django import forms
from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["note", "commentaire"]
        widgets = {
            "note": forms.Select(attrs={"class": "form-select"}),
            "commentaire": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": gettext_lazy("Écrivez votre avis ici..."),
                "rows": 4
            }),
        }
