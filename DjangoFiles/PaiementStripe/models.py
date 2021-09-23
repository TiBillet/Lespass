from django.db import models
import uuid
# Create your models here.


class Paiement_stripe(models.Model):
    """
    La commande
    """
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    id_stripe = models.CharField(max_length=20, blank=True, null=True)

    order_date = models.DateTimeField(auto_now=True, verbose_name="Date")

    NON, OPEN, PENDING, PAID, VALID, CANCELED = 'N', 'O', 'W', 'P', 'V', 'C'
    STATUT_CHOICES = (
        (NON, 'Lien de paiement non crée'),
        (OPEN, 'Envoyée a Stripe'),
        (PENDING, 'En attente de paiement'),
        (PAID, 'Payée'),
        (VALID, 'Payée et validée'),  # envoyé sur serveur cashless
        (CANCELED, 'Annulée'),
    )
    status = models.CharField(max_length=1, choices=STATUT_CHOICES, default=NON, verbose_name="Statut de la commande")

    # a remplir par default sur le front par User.email.
    email_billet = models.CharField(max_length=30, verbose_name="Email de récéption des billets", blank=True)

    # def total(self):
    #     total = 0
    #     for article in ArticleCommande.objects.filter(commande=self):
    #         total += article.total()
    #
    #     return total

    def __str__(self):
        return self.status



