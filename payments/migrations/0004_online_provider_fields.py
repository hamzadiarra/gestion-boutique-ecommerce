from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0003_payment_date_paiement_payment_reference_and_more")]
    operations = [
        migrations.AddField("payment", "provider", models.CharField(blank=True, default="", max_length=40)),
        migrations.AddField("payment", "provider_reference", models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField("payment", "provider_status", models.CharField(blank=True, default="", max_length=40)),
        migrations.AddField("payment", "provider_payload", models.JSONField(blank=True, null=True)),
        migrations.AddField("payment", "date_confirmation", models.DateTimeField(blank=True, null=True)),
        migrations.AlterField("payment", "methode", models.CharField(choices=[("especes", "Espèces"), ("orange_money", "Orange Money"), ("wave", "Wave"), ("carte", "Carte bancaire"), ("moov_money", "Moov Money"), ("online", "Paiement en ligne")], max_length=50)),
    ]
