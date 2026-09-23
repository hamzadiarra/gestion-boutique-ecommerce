import io

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.middleware.csrf import get_token

from .models import Profile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ProfilePhotoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile-owner",
            password="secret123",
            first_name="Hamza",
            last_name="Diarra",
            email="hamza@example.com",
        )
        self.client.login(username="profile-owner", password="secret123")
        # Execute commit callbacks after each request, as in production.
        original_post = self.client.post
        def post_with_commit(*args, **kwargs):
            with self.captureOnCommitCallbacks(execute=True):
                return original_post(*args, **kwargs)
        self.client.post = post_with_commit


    @staticmethod
    def image(name="avatar.png", color="blue", image_format="PNG"):
        stream = io.BytesIO()
        Image.new("RGB", (12, 12), color=color).save(stream, format=image_format)
        return SimpleUploadedFile(
            name, stream.getvalue(), content_type=f"image/{'jpeg' if image_format == 'JPEG' else image_format.lower()}"
        )

    def profile_data(self):
        return {
            "first_name": "Hamza",
            "last_name": "Diarra",
            "email": "hamza@example.com",
            "telephone": "76000000",
            "adresse": "Rue 1",
            "ville": "Bamako",
            "code_postal": "0000",
            "date_naissance": "1990-01-01",
            "genre": "homme",
        }

    def upload(self, name="avatar.png", color="blue", image_format="PNG"):
        data = self.profile_data()
        data["photo"] = self.image(name, color, image_format)
        response = self.client.post(reverse("profile_edit"), data)
        self.assertRedirects(response, reverse("profile"))
        return Profile.objects.get(utilisateur=self.user)

    def test_delete_photo_removes_storage_file_and_renders_initials(self):
        profile = self.upload()
        old_name = profile.photo.name
        storage = profile.photo.storage
        self.assertTrue(storage.exists(old_name))

        response = self.client.post(reverse("delete_profile_photo"))

        self.assertRedirects(response, reverse("profile"))
        profile.refresh_from_db()
        self.assertFalse(profile.photo)
        self.assertFalse(storage.exists(old_name))
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "HD")
        self.assertNotContains(page, "Supprimer la photo")
        home = self.client.get(reverse("home"))
        self.assertContains(home, "HD")
        refreshed = self.client.get(reverse("profile"))
        self.assertContains(refreshed, "HD")

    def test_delete_photo_is_post_only_and_empty_delete_is_safe(self):
        self.assertEqual(
            self.client.get(reverse("delete_profile_photo")).status_code,
            405,
        )
        response = self.client.post(reverse("delete_profile_photo"))
        self.assertRedirects(response, reverse("profile"))

    def test_delete_photo_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse("delete_profile_photo"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('delete_profile_photo')}",
        )

    def test_photo_replacement_deletes_only_old_file_after_valid_save(self):
        profile = self.upload("photo1.png", "blue")
        old_name = profile.photo.name
        storage = profile.photo.storage

        profile = self.upload("photo2.jpg", "red", "JPEG")
        new_name = profile.photo.name
        self.assertNotEqual(old_name, new_name)
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(new_name))

    def test_invalid_replacement_keeps_old_photo(self):
        profile = self.upload("photo1.png", "blue")
        old_name = profile.photo.name
        storage = profile.photo.storage
        data = self.profile_data()
        data["photo"] = SimpleUploadedFile(
            "malware.exe", b"not-an-image", content_type="application/octet-stream"
        )

        response = self.client.post(reverse("profile_edit"), data)

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.photo.name, old_name)
        self.assertTrue(storage.exists(old_name))

    def test_supported_png_jpeg_and_webp_uploads(self):
        for name, image_format in (
            ("photo.png", "PNG"),
            ("photo.jpg", "JPEG"),
            ("photo.webp", "WEBP"),
        ):
            profile = self.upload(name, "purple", image_format)
            self.assertTrue(profile.photo.name.endswith(name))

    def test_oversized_and_forbidden_photo_are_rejected(self):
        profile = self.upload("current.png")
        old_name = profile.photo.name

        oversized = self.profile_data()
        oversized["photo"] = SimpleUploadedFile(
            "large.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        response = self.client.post(reverse("profile_edit"), oversized)
        self.assertEqual(response.status_code, 200)

        forbidden = self.profile_data()
        forbidden["photo"] = SimpleUploadedFile(
            "avatar.exe", b"x", content_type="application/octet-stream"
        )
        response = self.client.post(reverse("profile_edit"), forbidden)
        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.photo.name, old_name)

    def test_csrf_is_required_for_photo_deletion(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.upload("csrf.png")
        response = csrf_client.post(reverse("delete_profile_photo"))
        self.assertEqual(response.status_code, 403)

        page = csrf_client.get(reverse("profile"))
        # The token is present in the rendered profile form; obtain a valid
        # token through Django's test helper rather than trusting user input.
        from django.middleware.csrf import get_token
        token = get_token(page.wsgi_request)
        response = csrf_client.post(
            reverse("delete_profile_photo"),
            {"csrfmiddlewaretoken": token},
        )
        self.assertRedirects(response, reverse("profile"))

    def test_csrf_protects_profile_edit_and_photo_upload(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        page = csrf_client.get(reverse("profile_edit"))
        token = get_token(page.wsgi_request)

        data = self.profile_data()
        data["csrfmiddlewaretoken"] = token
        response = csrf_client.post(reverse("profile_edit"), data)
        self.assertRedirects(response, reverse("profile"))

        data = self.profile_data()
        data["csrfmiddlewaretoken"] = token
        data["photo"] = self.image("csrf-upload.png")
        response = csrf_client.post(reverse("profile_edit"), data)
        self.assertRedirects(response, reverse("profile"))

    def test_photo_delete_cannot_touch_another_users_file(self):
        owner_profile = self.upload("owner.png")
        other = User.objects.create_user("other", password="secret123")
        other_profile = Profile.objects.get(utilisateur=other)
        other_profile.photo = self.image("other.png", "green")
        other_profile.save(update_fields=["photo"])
        other_name = other_profile.photo.name
        storage = other_profile.photo.storage

        self.client.post(reverse("delete_profile_photo"))

        self.assertFalse(Profile.objects.get(pk=owner_profile.pk).photo)
        self.assertTrue(storage.exists(other_name))

    def test_empty_profile_exposes_add_photo_action(self):
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "Ajouter une photo")
        self.assertContains(page, "HD")
        self.assertNotContains(page, "Supprimer la photo")

    def test_uploaded_photo_is_rendered_in_header_and_profile(self):
        profile = self.upload()
        page = self.client.get(reverse("profile"))
        self.assertContains(page, profile.photo.url, count=3)
        self.assertContains(page, "Modifier la photo")
        self.assertContains(page, "Supprimer la photo")

    def test_shared_photo_is_preserved_on_delete_and_replace(self):
        for replace in (False, True):
            profile = self.upload()
            old_name = profile.photo.name
            other = User.objects.create_user("shared-" + str(replace))
            Profile.objects.filter(utilisateur=other).update(photo=old_name)
            if replace:
                self.upload("replacement.png")
            else:
                self.client.post(reverse("delete_profile_photo"))
            self.assertTrue(profile.photo.storage.exists(old_name))
            self.assertEqual(Profile.objects.get(utilisateur=other).photo.name, old_name)

    def test_default_photo_is_never_deleted(self):
        from django.core.files.base import ContentFile
        field = Profile._meta.get_field("photo")
        name = field.storage.save("defaults/avatar.png", ContentFile(b"default"))
        Profile.objects.filter(utilisateur=self.user).update(photo=name)
        self.client.post(reverse("delete_profile_photo"))
        self.assertTrue(field.storage.exists(name))

    def test_delete_database_failure_preserves_file(self):
        from unittest.mock import patch
        profile = self.upload()
        old_name = profile.photo.name
        with patch.object(Profile, "save", side_effect=RuntimeError("save failed")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("delete_profile_photo"))
        self.assertTrue(profile.photo.storage.exists(old_name))

    def test_failed_replacement_does_not_leave_new_file(self):
        from unittest.mock import patch
        from django.db.models import Model
        profile = self.upload("original.png")
        before = profile.photo.storage.listdir("profiles")
        original = Model.save
        def fail_profile(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            if isinstance(instance, Profile):
                raise RuntimeError("save failed after file write")
            return result
        data = self.profile_data()
        data["photo"] = self.image("failed.png")
        with patch.object(Model, "save", fail_profile):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("profile_edit"), data)
        profile.refresh_from_db()
        self.assertTrue(profile.photo.name.endswith("original.png"))
        self.assertEqual(profile.photo.storage.listdir("profiles"), before)

    def test_photo_actions_are_translated_in_english(self):
        self.client.cookies["django_language"] = "en"
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "Add photo")
        self.upload()
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "Change photo")
        self.assertContains(page, "Remove photo")

    def test_upload_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        data = self.profile_data()
        data["photo"] = self.image()
        self.assertEqual(client.post(reverse("profile_edit"), data).status_code, 403)
        self.assertFalse(Profile.objects.get(utilisateur=self.user).photo)

    def test_storage_cleanup_failure_does_not_break_saved_profile(self):
        from unittest.mock import patch
        profile = self.upload()
        with patch.object(profile.photo.storage, "delete", side_effect=OSError("storage unavailable")):
            with self.assertLogs(level="ERROR"):
                response = self.client.post(reverse("delete_profile_photo"))
        self.assertRedirects(response, reverse("profile"))
        profile.refresh_from_db()
        self.assertFalse(profile.photo)
