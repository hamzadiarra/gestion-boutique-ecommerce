from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.security_models import SecurityEvent


class Command(BaseCommand):
    help = "Purge les événements de connexion anciens ; conserve les audits et les preuves de suspension. Simulation par défaut."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        if options["days"] < 30:
            raise CommandError("La durée minimale est 30 jours.")
        events = SecurityEvent.objects.filter(created_at__lt=timezone.now()-timedelta(days=options["days"]), kind__in=["login", "logout", "login_failed"], accountsuspension__isnull=True)
        count = events.count()
        if options["execute"]:
            events.delete()
        self.stdout.write(f"{count} événements {'supprimés' if options['execute'] else 'éligibles (simulation)'}. Les audits administratifs sont conservés.")
