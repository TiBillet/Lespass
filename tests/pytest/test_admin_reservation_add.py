"""
Test DB-only : formulaire admin d'ajout de reservation (ReservationAddAdmin).
/ DB-only test: admin reservation add form (ReservationAddAdmin).

Couvre :
1. Sentry 7574740199 : le champ "email" est un EmailField (saisie texte) et
   save() retrouve/cree l'utilisateur via get_or_create_user.
2. Le champ tarif liste UNE OPTION PAR COUPLE (evenement, tarif), valeur
   "event_uuid:price_uuid". Un meme tarif (Product/Price) peut etre partage par
   plusieurs evenements (ex "Reservation gratuite") : chaque evenement a alors sa
   propre option, et la reservation est creee sur le BON evenement.
3. save() materialise le ProductSold + PriceSold au besoin.

On verifie aussi le montant de la ligne comptable (LigneArticle) :
- tarif gratuit (FREERES + Offert) -> amount = 0
- tarif payant (BILLET + Especes) -> amount = prix * quantite * 100 (centimes)

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_admin_reservation_add.py -v
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def test_admin_reservation_add_tarif_gratuit_cree_reservation_et_ligne(tenant):
    """
    Cas GRATUIT : l'admin saisit un email, choisit un tarif FREERES en "Offert",
    quantite 2. La reservation, l'utilisateur, 2 billets et UNE ligne comptable
    a 0 sont crees — sans crash. Le PriceSold est materialise par save().
    / FREE case: typed email + FREERES rate "Offered" + qty 2 -> reservation,
      user, 2 tickets and ONE accounting line at 0. PriceSold materialized.
    """
    with tenant_context(tenant):
        from Administration.admin_tenant import ReservationAddAdmin
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import (
            Event, Product, ProductSold, PriceSold,
            Reservation, Ticket, LigneArticle, PaymentMethod, SaleOrigin,
        )

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"Soiree_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        product = Product.objects.create(
            name=f"Resa_gratuite_{suffix}",
            categorie_article=Product.FREERES,
        )
        event.products.add(product)
        # Le signal post_save_Product cree automatiquement un Price gratuit.
        # / The post_save_Product signal auto-creates a free Price.
        price = product.prices.filter(prix=0).first()
        assert price is not None, "Le signal FREERES doit avoir cree un tarif gratuit"
        assert not PriceSold.objects.filter(price=price).exists()

        email_saisi = f"resa_gratuite_{suffix}@example.com"
        assert not TibilletUser.objects.filter(email=email_saisi).exists()

        form_data = {
            "email": email_saisi,
            "price": f"{event.uuid}:{price.uuid}",
            "payment_method": PaymentMethod.FREE,  # "NA" = Offert / Offered
            "quantity": 2,
        }
        form = ReservationAddAdmin(data=form_data)

        with patch("Administration.admin_tenant.send_sale_to_laboutik.delay") as mock_laboutik, \
             patch("Administration.admin_tenant.ticket_celery_mailer.delay") as mock_mailer:
            assert form.is_valid(), form.errors
            reservation = form.save()

        user = TibilletUser.objects.get(email=email_saisi)
        assert reservation.user_commande == user
        assert tenant in user.client_achat.all()
        assert reservation.status == Reservation.VALID
        assert reservation.event == event

        pricesold = PriceSold.objects.get(price=price)
        assert pricesold.productsold.event == event

        assert Ticket.objects.filter(reservation=reservation).count() == 2

        ligne = LigneArticle.objects.get(reservation=reservation)
        assert ligne.amount == 0
        assert int(ligne.qty) == 2
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.FREE
        assert ligne.sale_origin == SaleOrigin.ADMIN
        assert ligne.pricesold == pricesold
        # L'email de l'acheteur est lisible sur la ligne comptable.
        # / The buyer email is readable on the accounting line.
        assert ligne.user_email() == email_saisi

        mock_laboutik.assert_called_once()
        mock_mailer.assert_called_once()

        Ticket.objects.filter(reservation=reservation).delete()
        ligne.delete()
        reservation.delete()
        pricesold.delete()


def test_admin_reservation_add_tarif_payant_calcule_le_montant_en_centimes(tenant):
    """
    Cas PAYANT : tarif BILLET a 12,00 EUR, paiement Especes, quantite 3.
    La ligne comptable porte amount = 12,00 * 3 * 100 = 3600 centimes.
    / PAID case: BILLET rate at 12.00 EUR, Cash, qty 3 -> line amount = 3600 cents.
    """
    with tenant_context(tenant):
        from Administration.admin_tenant import ReservationAddAdmin
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import (
            Event, Product, Price, ProductSold, PriceSold,
            Reservation, Ticket, LigneArticle, PaymentMethod, SaleOrigin,
        )

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"Concert_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        product = Product.objects.create(
            name=f"Billet_{suffix}",
            categorie_article=Product.BILLET,
        )
        event.products.add(product)
        price = Price.objects.create(
            product=product, name=f"Plein_{suffix}", prix=Decimal("12.00"),
        )
        assert not PriceSold.objects.filter(price=price).exists()

        email_saisi = f"resa_payante_{suffix}@example.com"

        form_data = {
            "email": email_saisi,
            "price": f"{event.uuid}:{price.uuid}",
            "payment_method": PaymentMethod.CASH,  # "CA" = Especes / Cash
            "quantity": 3,
        }
        form = ReservationAddAdmin(data=form_data)

        with patch("Administration.admin_tenant.send_sale_to_laboutik.delay") as mock_laboutik, \
             patch("Administration.admin_tenant.ticket_celery_mailer.delay") as mock_mailer:
            assert form.is_valid(), form.errors
            reservation = form.save()

        assert Ticket.objects.filter(reservation=reservation).count() == 3

        pricesold = PriceSold.objects.get(price=price)
        assert pricesold.productsold.event == event

        ligne = LigneArticle.objects.get(reservation=reservation)
        assert ligne.amount == 3600
        assert int(ligne.qty) == 3
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.CASH
        assert ligne.sale_origin == SaleOrigin.ADMIN
        assert ligne.pricesold == pricesold
        assert ligne.user_email() == email_saisi

        mock_laboutik.assert_called_once()
        mock_mailer.assert_called_once()

        Ticket.objects.filter(reservation=reservation).delete()
        ligne.delete()
        reservation.delete()
        pricesold.delete()
        TibilletUser.objects.filter(email=email_saisi).delete()


def test_admin_reservation_add_tarif_partage_entre_deux_events(tenant):
    """
    Coeur du fix : un meme tarif (Product/Price) partage par 2 evenements doit
    donner 2 options distinctes dans le select, et reserver sur le BON evenement.
    Avant, le select listait les Price (une seule option) et reservait toujours
    sur le premier evenement -> les autres etaient invisibles/inaccessibles.
    / Core fix: a rate shared by 2 events must yield 2 distinct options and book
      on the RIGHT event.
    """
    with tenant_context(tenant):
        from Administration.admin_tenant import ReservationAddAdmin
        from BaseBillet.models import (
            Event, Product, Reservation, Ticket, LigneArticle, PaymentMethod, PriceSold,
        )

        suffix = uuid.uuid4().hex[:8]

        # Un seul produit/tarif gratuit, partage par DEUX evenements.
        # / One single free product/rate, shared by TWO events.
        product = Product.objects.create(
            name=f"Resa_partagee_{suffix}",
            categorie_article=Product.FREERES,
        )
        price = product.prices.filter(prix=0).first()
        event_1 = Event.objects.create(
            name=f"EventUn_{suffix}", datetime=timezone.now() + timedelta(days=5),
        )
        event_2 = Event.objects.create(
            name=f"EventDeux_{suffix}", datetime=timezone.now() + timedelta(days=6),
        )
        event_1.products.add(product)
        event_2.products.add(product)

        # Le select propose une option distincte pour CHAQUE evenement.
        # / The select offers a distinct option for EACH event.
        form = ReservationAddAdmin()
        valeurs = [valeur for valeur, libelle in form.fields["price"].choices]
        assert f"{event_1.uuid}:{price.uuid}" in valeurs
        assert f"{event_2.uuid}:{price.uuid}" in valeurs

        # On reserve explicitement sur le DEUXIEME evenement.
        # / Book explicitly on the SECOND event.
        form_data = {
            "email": f"partage_{suffix}@example.com",
            "price": f"{event_2.uuid}:{price.uuid}",
            "payment_method": PaymentMethod.FREE,
            "quantity": 1,
        }
        form = ReservationAddAdmin(data=form_data)
        with patch("Administration.admin_tenant.send_sale_to_laboutik.delay"), \
             patch("Administration.admin_tenant.ticket_celery_mailer.delay"):
            assert form.is_valid(), form.errors
            reservation = form.save()

        # La reservation est bien sur event_2, PAS event_1.
        # / The reservation is on event_2, NOT event_1.
        assert reservation.event == event_2

        Ticket.objects.filter(reservation=reservation).delete()
        LigneArticle.objects.filter(reservation=reservation).delete()
        reservation.delete()
        PriceSold.objects.filter(price=price).delete()


def test_admin_reservation_add_champs_email_et_tarif():
    """
    Garde-fou : "email" reste un EmailField (saisie texte, cf. Sentry 7574740199)
    et "price" est un ChoiceField (une option par couple evenement/tarif).
    / Guard: "email" stays an EmailField and "price" is a ChoiceField.
    """
    from django import forms

    from Administration.admin_tenant import ReservationAddAdmin

    champ_email = ReservationAddAdmin.base_fields["email"]
    assert isinstance(champ_email, forms.EmailField), (
        "Le champ email doit etre un EmailField — cf. Sentry 7574740199."
    )

    champ_price = ReservationAddAdmin.base_fields["price"]
    assert isinstance(champ_price, forms.ChoiceField), (
        "Le champ tarif doit etre un ChoiceField (une option par couple evenement/tarif)."
    )
    assert not isinstance(champ_price, forms.ModelChoiceField), (
        "Le champ tarif ne doit PAS etre un ModelChoiceField : un tarif partage "
        "entre evenements rendrait des evenements invisibles."
    )
