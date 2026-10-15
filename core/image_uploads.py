"""Normalize newly uploaded public raster images before storage."""
import io
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 20_000_000
FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
OUTPUTS = {'JPEG': ('.jpg', 'image/jpeg'), 'PNG': ('.png', 'image/png'), 'WEBP': ('.webp', 'image/webp')}


def normalize_image_upload(uploaded):
    """Return fresh pixel-only data; never rewrite a previously stored photo."""
    suffix = Path(uploaded.name).suffix.lower()
    if suffix not in FORMATS:
        raise ValidationError('Formats acceptés : JPG, JPEG, PNG et WebP.')
    if not 0 < uploaded.size <= MAX_IMAGE_BYTES:
        raise ValidationError('L’image doit peser entre 1 octet et 5 Mo.')
    try:
        uploaded.seek(0)
        raw = uploaded.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValidationError('L’image doit peser 5 Mo maximum.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                fmt = source.format
                if fmt != FORMATS[suffix]:
                    raise ValidationError('Le format réel de l’image ne correspond pas à son extension.')
                if max(source.size) > MAX_IMAGE_SIDE or source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValidationError('L’image dépasse 8192 pixels par côté ou 20 millions de pixels.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValidationError('Les images animées ne sont pas acceptées.')
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = 'RGB' if fmt == 'JPEG' else 'RGBA'
                pixels = oriented.convert(mode)
                # A new image carries no EXIF, ICC, comments or appended bytes.
                clean = Image.frombytes(mode, pixels.size, pixels.tobytes())
                output = io.BytesIO()
                options = {'quality': 95} if fmt == 'JPEG' else {'lossless': True} if fmt == 'WEBP' else {}
                clean.save(output, format=fmt, **options)
        data = output.getvalue()
        if len(data) > MAX_IMAGE_BYTES:
            raise ValidationError('L’image normalisée dépasse 5 Mo. Réduisez sa résolution.')
        extension, content_type = OUTPUTS[fmt]
        return SimpleUploadedFile(uuid4().hex + extension, data, content_type=content_type)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('Le fichier envoyé n’est pas une image valide.') from exc
    finally:
        uploaded.seek(0)
