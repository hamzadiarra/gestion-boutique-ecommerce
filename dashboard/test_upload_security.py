import io
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from categories.models import Category
from products.models import Product
from dashboard.models import BoutiqueSettings


def upload(name='photo.png', fmt='PNG', size=(24, 16), tail=b'', orientation=None):
    stream = io.BytesIO()
    picture = Image.new('RGBA' if fmt == 'PNG' else 'RGB', size, (20, 40, 60, 80) if fmt == 'PNG' else (20, 40, 60))
    options = {}
    if orientation:
        exif = Image.Exif(); exif[274] = orientation
        options['exif'] = exif
    picture.save(stream, fmt, **options)
    return SimpleUploadedFile(name, stream.getvalue()+tail, content_type='image/png' if fmt == 'PNG' else 'image/jpeg')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class UploadSecurityTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.setting = override_settings(MEDIA_ROOT=self.directory.name)
        self.setting.enable(); self.addCleanup(self.setting.disable)
        self.user = User.objects.create_user('upload-admin', is_superuser=True, is_staff=True)
        self.client.force_login(self.user)
        self.seller = User.objects.create_user('upload-seller')
        self.seller.profile.role = 'vendeur'; self.seller.profile.save()
        self.category = Category.objects.create(nom='Upload tests')

    def product_post(self, image, product=None):
        self.client.force_login(self.seller)
        data = {'nom':'Produit sécurisé', 'prix':'1000', 'stock':'5', 'categorie':self.category.pk, 'actif':'on'}
        if image is not None: data['image'] = image
        return self.client.post(reverse('vendeur_modifier_produit', args=[product.pk]) if product else reverse('vendeur_ajouter_produit'), data)

    def test_product_html_extension_rejected(self):
        response = self.product_post(upload('attack.html', tail=b'<script>test</script>'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_product_normalized_and_existing_photo_preserved(self):
        self.assertEqual(self.product_post(upload(tail=b'<script>test</script>')).status_code, 302)
        product = Product.objects.get()
        self.assertRegex(Path(product.image.name).name, r'^[0-9a-f]{32}\.png$')
        original = product.image.read(); product.image.close()
        self.assertNotIn(b'<script>', original)
        self.assertEqual(Image.open(io.BytesIO(original)).getpixel((0,0))[3], 80)
        previous = product.image.name
        self.assertEqual(self.product_post(None, product).status_code, 302)
        product.refresh_from_db(); self.assertEqual(product.image.name, previous)
        self.assertEqual(self.product_post(upload('bad.html'), product).status_code, 200)
        product.refresh_from_db(); self.assertEqual(product.image.name, previous)

    def test_logo_html_rejected_and_png_normalized(self):
        data = {'nom':'Boutique', 'devise':'FCFA', 'seuil_stock_faible':'4', 'logo':upload('logo.html')}
        self.assertEqual(self.client.post(reverse('admin_parametres'), data).status_code, 200)
        self.assertFalse(BoutiqueSettings.objects.get().logo)
        data['logo'] = upload('logo.png', tail=b'<script>test</script>')
        self.assertEqual(self.client.post(reverse('admin_parametres'), data).status_code, 302)
        logo = BoutiqueSettings.objects.get().logo
        self.assertRegex(Path(logo.name).name, r'^[0-9a-f]{32}\.png$')
        self.assertNotIn(b'<script>', logo.read()); logo.close()

    def test_admin_form_normalizes_new_upload(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/'); request.user = self.user
        form_type = admin.site._registry[Product].get_form(request)
        form = form_type(data={'nom':'Admin produit', 'slug':'admin-produit', 'categorie':self.category.pk, 'prix':'1200', 'stock':'2'}, files={'image':upload(tail=b'<script>test</script>')})
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertRegex(Path(product.image.name).name, r'^[0-9a-f]{32}\.png$')
        self.assertNotIn(b'<script>', product.image.read()); product.image.close()

    def test_helper_orientation_and_validation(self):
        from core.image_uploads import normalize_image_upload
        from django.core.exceptions import ValidationError
        clean = normalize_image_upload(upload('oriented.jpg', 'JPEG', orientation=6))
        picture = Image.open(clean)
        self.assertEqual(picture.size, (16,24))
        self.assertFalse(picture.getexif())
        for item in [upload('wrong.jpg'), upload(size=(8193,1)), SimpleUploadedFile('huge.png', b'x'*(5*1024*1024+1), content_type='image/png'), upload('image.gif', 'GIF')]:
            with self.subTest(name=item.name), self.assertRaises(ValidationError):
                normalize_image_upload(item)

    def test_webp_preserves_transparency_and_ignores_untrusted_mime(self):
        from core.image_uploads import normalize_image_upload
        stream = io.BytesIO()
        Image.new('RGBA', (12, 14), (20, 40, 60, 80)).save(stream, 'WEBP', lossless=True)
        item = SimpleUploadedFile('photo.webp', stream.getvalue()+b'<script>test</script>', content_type='text/html')
        clean = normalize_image_upload(item)
        self.assertEqual(clean.content_type, 'image/webp')
        self.assertNotIn(b'<script>', clean.read()); clean.seek(0)
        self.assertEqual(Image.open(clean).getpixel((0,0)), (20,40,60,80))

    def test_animated_png_and_malformed_data_are_rejected(self):
        from core.image_uploads import normalize_image_upload
        from django.core.exceptions import ValidationError
        stream = io.BytesIO()
        Image.new('RGB',(12,12),'red').save(stream, 'PNG', save_all=True,
            append_images=[Image.new('RGB',(12,12),'blue')], duration=100, loop=0)
        for raw in (stream.getvalue(), b'not an image'):
            with self.assertRaises(ValidationError):
                normalize_image_upload(SimpleUploadedFile('photo.png', raw, content_type='image/png'))

    def test_admin_existing_photo_preserved_and_new_mismatch_rejected(self):
        from products.admin import ProductAdminForm
        product = Product.objects.create(nom='Existing', slug='existing', categorie=self.category, prix=100, stock=2, image=upload())
        old_name = product.image.name
        data = {'nom':'Existing edit', 'slug':'existing', 'categorie':self.category.pk, 'prix':'100', 'stock':'2', 'quantite_vendue':'0'}
        form = ProductAdminForm(data=data, instance=product)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().image.name, old_name)
        for name in ('attack.html', 'wrong.jpg', 'photo.gif'):
            form = ProductAdminForm(data=data, files={'image':upload(name)}, instance=product)
            self.assertFalse(form.is_valid())
            self.assertIn('image', form.errors)
