from django.core.management.base import BaseCommand
from django.db import models, transaction
from datetime import timedelta
from orders.proof_services import retention_days
from django.utils import timezone
from orders.proof_models import PreuveLivraison, DemandeDerogation


class Command(BaseCommand):
    help = "Prévisualise les preuves expirées ; --apply efface leurs données privées."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        with transaction.atomic():
            qs = models.QuerySet(model=PreuveLivraison).filter(expire_at__lte=now, purged_at__isnull=True)
            ids = list(qs.values_list("livraison_id", flat=True))
            requests = models.QuerySet(model=DemandeDerogation).filter(
                created_at__lte=now-timedelta(days=retention_days())).filter(
                models.Q(livraison__preuve__isnull=True) | models.Q(livraison__preuve__expire_at__lte=now))
            self.stdout.write(f"Preuves expirées : {len(ids)} ; dérogations anciennes : {requests.count()}")
            if options["apply"]:
                requests.filter(decision="attente").update(decision="refusee", decided_at=now)
                requests.update(receptionnaire="", motif="", motif_decision="")
                qs.update(signature=None, receptionnaire="", empreinte="", motif="", purged_at=now)
                models.QuerySet(model=DemandeDerogation).filter(livraison_id__in=ids).update(receptionnaire="", motif="", motif_decision="")
                self.stdout.write("Données privées effacées ; références et chronologie conservées.")
            else:
                self.stdout.write("Prévisualisation uniquement ; utilisez --apply pour effacer.")
