from django.utils.translation import gettext_lazy
"""Private storage and bounded validation for expense attachments."""
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.utils.deconstruct import deconstructible


MAX_JUSTIFICATIF_BYTES = 5 * 1024 * 1024
FILE_TYPES = {
    ".pdf": ("application/pdf", None),
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
    ".webp": ("image/webp", "WEBP"),
}


@deconstructible
class PrivateExpenseStorage(FileSystemStorage):
    @property
    def base_location(self):
        return getattr(settings, "PRIVATE_EXPENSE_ROOT", settings.BASE_DIR / "private_media")

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Les justificatifs sont accessibles uniquement par la vue protégée.")


def justificatif_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"depenses/justificatifs/{timezone.localdate():%Y/%m}/{uuid4().hex}{suffix}"


def validate_justificatif(uploaded):
    if not uploaded:
        return
    suffix = Path(uploaded.name).suffix.lower()
    if suffix not in FILE_TYPES:
        raise ValidationError(gettext_lazy("Formats acceptés : PDF, JPG/JPEG, PNG et WebP."))
    if uploaded.size <= 0 or uploaded.size > MAX_JUSTIFICATIF_BYTES:
        raise ValidationError(gettext_lazy("Le justificatif doit peser entre 1 octet et 5 Mo."))
    expected_type, expected_format = FILE_TYPES[suffix]
    content_type = getattr(uploaded, "content_type", None)
    if content_type is None:
        content_type = getattr(getattr(uploaded, "file", None), "content_type", None)
    if content_type and content_type != expected_type:
        raise ValidationError(gettext_lazy("Le type du fichier ne correspond pas à son extension."))
    try:
        uploaded.seek(0)
        if suffix == ".pdf":
            if not uploaded.read(8).startswith(b"%PDF-"):
                raise ValidationError(gettext_lazy("Le fichier envoyé n'est pas un PDF."))
            uploaded.seek(max(0, uploaded.size - 1024))
            if b"%%EOF" not in uploaded.read():
                raise ValidationError(gettext_lazy("Le fichier PDF est incomplet."))
        else:
            with Image.open(uploaded) as image:
                if image.format != expected_format:
                    raise ValidationError(gettext_lazy("L'image ne correspond pas à son extension."))
                image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValidationError(gettext_lazy("Le justificatif est illisible ou invalide.")) from exc
    finally:
        uploaded.seek(0)
