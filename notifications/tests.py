from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from notifications.models import Notification
from orders.models import Order


class NotificationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123", email="client@example.com")
        self.client.login(username="client", password="secret123")

    def test_order_creation_creates_typed_notification(self):
        order = Order.objects.create(utilisateur=self.user)
        notification = Notification.objects.get(utilisateur=self.user)
        self.assertEqual(notification.type_notification, "commande")
        self.assertIn(str(order.id), notification.lien)

    def test_read_actions_require_post_and_are_scoped(self):
        notification = Notification.objects.create(utilisateur=self.user, titre="Test", message="Message")
        self.client.get(reverse("mark_as_read", args=[notification.id]))
        notification.refresh_from_db()
        self.assertFalse(notification.lu)
        self.client.post(reverse("mark_as_read", args=[notification.id]))
        notification.refresh_from_db()
        self.assertTrue(notification.lu)

    def test_notification_list_paginates(self):
        Notification.objects.bulk_create([
            Notification(utilisateur=self.user, titre=f"Info {i}", message="Message") for i in range(11)
        ])
        response = self.client.get(reverse("notification_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b"notification-card"), 10)

    def test_mark_all_as_read_is_post_only(self):
        Notification.objects.create(utilisateur=self.user, titre="Test", message="Message")
        self.client.get(reverse("mark_all_as_read"))
        self.assertTrue(Notification.objects.filter(utilisateur=self.user, lu=False).exists())
        self.client.post(reverse("mark_all_as_read"))
        self.assertFalse(Notification.objects.filter(utilisateur=self.user, lu=False).exists())
