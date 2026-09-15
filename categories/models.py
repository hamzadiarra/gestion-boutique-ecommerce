from django.utils.translation import gettext_lazy, get_language
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    nom_en = models.CharField(max_length=100, blank=True, default="")
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    active = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Catégorie")
        verbose_name_plural = gettext_lazy("Catégories")
        ordering = ['nom']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom

    @property
    def localized_name(self):
        return self.nom_en.strip() if get_language() == "en" and self.nom_en.strip() else self.nom

    @property
    def localized_description(self):
        return self.description_en.strip() if get_language() == "en" and self.description_en.strip() else self.description
