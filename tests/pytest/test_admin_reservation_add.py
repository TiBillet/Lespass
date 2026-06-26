"""
Test DB-only : formulaire admin d'ajout de reservation (ReservationAddAdmin).
/ DB-only test: admin reservation add form (ReservationAddAdmin).

Couvre deux corrections :
1. Sentry 7574740199 : le champ "email" est un EmailField (saisie texte) et
   save() retrouve/cree l'utilisateur via get_or_create_user (plus de crash
   'TibilletUser' object has no attribute 'lower').
2. Le champ tarif liste les Price des evenements a venir (et non les PriceSold,
   qui n'existent qu'apres une premiere vente). save() materialise le
   ProductSold + PriceSold au besoin.
/ Covers two fixes: (1) email is an EmailField; (2) the rate field lists Price
  of upcoming events, save() materializes ProductSold + PriceSold.

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

        # --- Donnees : un evenement futur avec un tarif gratuit (FREERES) ---
        # / Future event with a free booking rate (FREERES).
        event = Event.objects.create(
            name=f"Soiree_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        product = Product.objects.create(
            name=f"Resa_gratuite_{suffix}",
            categorie_article=Product.FREERES,
        )
        # Le tarif est rattache a l'evenement via le M2M Event.products.
        # / The rate is linked to the event via the Event.products M2M.
        event.products.add(product)
        # Le signal post_save_Product cree automatiquement un Price gratuit
        # pour les produits FREERES : on le reutilise.
        # / The post_save_Product signal auto-creates a free Price for FREERES.
        price = product.prices.filter(prix=0).first()
        assert price is not None, "Le signal FREERES doit avoir cree un tarif gratuit"

        # Aucune vente encore : pas de PriceSold, mais le tarif est proposable.
        # / No sale yet: no PriceSold, but the rate is selectable.
        assert not PriceSold.objects.filter(price=price).exists()

        # --- L'admin saisit une adresse email encore inconnue ---
        # / Admin types an email that does not exist yet.
        email_saisi = f"resa_gratuite_{suffix}@example.com"
        assert not TibilletUser.objects.filter(email=email_saisi).exists()

        form_data = {
            "email": email_saisi,
            "price": str(price.pk),
            "payment_method": PaymentMethod.FREE,  # "NA" = Offert / Offered
            "quantity": 2,
        }
        form = ReservationAddAdmin(data=form_data)

        # save() declenche deux taches Celery : on les mocke pour rester DB-only.
        # / save() triggers two Celery tasks: mock them to stay DB-only.
        with patch("Administration.admin_tenant.send_sale_to_laboutik.delay") as mock_laboutik, \
             patch("Administration.admin_tenant.ticket_celery_mailer.delay") as mock_mailer:
            assert form.is_valid(), form.errors
            reservation = form.save()

        # --- Verifications ---
        # 1. L'utilisateur a ete cree a partir de l'email saisi, rattache au tenant
        # / User created from the typed email, linked to the tenant.
        user = TibilletUser.objects.get(email=email_saisi)
        assert reservation.user_commande == user
        assert tenant in user.client_achat.all()

        # 2. La reservation est en VALID et liee au bon evenement
        # / Reservation is VALID and linked to the right event.
        assert reservation.status == Reservation.VALID
        assert reservation.event == event

        # 3. Le PriceSold a bien ete materialise par save()
        # / The PriceSold was materialized by save().
        pricesold = PriceSold.objects.get(price=price)
        assert pricesold.productsold.event == event

        # 4. Deux billets crees (quantity=2)
        # / Two tickets created (quantity=2).
        assert Ticket.objects.filter(reservation=reservation).count() == 2

        # 5. UNE ligne comptable (LigneArticle), entierement renseignee, a 0
        # / Exactly ONE accounting line, fully set, at 0.
        # Le .get() leve si 0 (DoesNotExist) ou >1 (MultipleObjectsReturned).
        ligne = LigneArticle.objects.get(reservation=reservation)
        assert ligne.amount == 0
        assert int(ligne.qty) == 2
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.FREE
        assert ligne.sale_origin == SaleOrigin.ADMIN
        assert ligne.pricesold == pricesold

        # 6. L'email de l'acheteur est lisible sur la ligne comptable
        # (colonne "user_email" de l'admin LigneArticle, via la reservation).
        # / The buyer email is readable on the line (admin "user_email" column).
        assert ligne.user_email() == email_saisi

        # 7. Les taches Celery ont bien ete declenchees une fois
        # / Celery tasks triggered once.
        mock_laboutik.assert_called_once()
        mock_mailer.assert_called_once()

        # Nettoyage minimal (la base dev est partagee entre les tests)
        # / Minimal cleanup (the dev DB is shared across tests).
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

        # --- Donnees : un evenement futur avec un tarif BILLET payant ---
        # / Future event with a paid BILLET rate.
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
            "price": str(price.pk),
            "payment_method": PaymentMethod.CASH,  # "CA" = Especes / Cash
            "quantity": 3,
        }
        form = ReservationAddAdmin(data=form_data)

        with patch("Administration.admin_tenant.send_sale_to_laboutik.delay") as mock_laboutik, \
             patch("Administration.admin_tenant.ticket_celery_mailer.delay") as mock_mailer:
            assert form.is_valid(), form.errors
            reservation = form.save()

        # 3 billets pour quantity=3
        # / 3 tickets for quantity=3.
        assert Ticket.objects.filter(reservation=reservation).count() == 3

        # Le PriceSold materialise pointe vers notre tarif et notre evenement
        # / The materialized PriceSold points to our rate and event.
        pricesold = PriceSold.objects.get(price=price)
        assert pricesold.productsold.event == event

        # UNE ligne comptable : amount = 12,00 * 3 * 100 = 3600 centimes
        # / ONE accounting line: amount = 3600 cents.
        ligne = LigneArticle.objects.get(reservation=reservation)
        assert ligne.amount == 3600
        assert int(ligne.qty) == 3
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.CASH
        assert ligne.sale_origin == SaleOrigin.ADMIN
        assert ligne.pricesold == pricesold

        # L'email de l'acheteur est lisible sur la ligne comptable.
        # / The buyer email is readable on the accounting line.
        assert ligne.user_email() == email_saisi

        mock_laboutik.assert_called_once()
        mock_mailer.assert_called_once()

        # Nettoyage minimal
        # / Minimal cleanup.
        Ticket.objects.filter(reservation=reservation).delete()
        ligne.delete()
        reservation.delete()
        pricesold.delete()
        TibilletUser.objects.filter(email=email_saisi).delete()


def test_admin_reservation_add_propose_les_tarifs_des_events_futurs_jamais_vendus(tenant):
    """
    Coeur du fix : un tarif d'un evenement a venir JAMAIS vendu (donc sans
    PriceSold) doit apparaitre dans le select. Avant, le champ listait les
    PriceSold et ces tarifs etaient invisibles.
    / Core of the fix: a rate of an upcoming event never sold (no PriceSold)
      must appear in the select.
    """
    with tenant_context(tenant):
        from Administration.admin_tenant import ReservationAddAdmin
        from BaseBillet.models import Event, Product, Price, PriceSold

        suffix = uuid.uuid4().hex[:8]
        event = Event.objects.create(
            name=f"Futur_{suffix}",
            datetime=timezone.now() + timedelta(days=5),
        )
        product = Product.objects.create(
            name=f"Billet_{suffix}",
            categorie_article=Product.BILLET,
        )
        event.products.add(product)
        price = Price.objects.create(
            product=product, name=f"Plein_{suffix}", prix=Decimal("10.00"),
        )

        # Aucune vente -> aucun PriceSold, mais le tarif doit etre proposable.
        # / No sale -> no PriceSold, but the rate must be selectable.
        assert not PriceSold.objects.filter(price=price).exists()

        form = ReservationAddAdmin()
        queryset_du_select = form.fields["price"].queryset
        assert queryset_du_select.filter(pk=price.pk).exists(), (
            "Un tarif d'un evenement futur jamais vendu doit apparaitre dans le select."
        )

        # Et le libelle affiche bien la date, l'evenement et le prix.
        # / And the label shows date, event and price.
        libelle = form.fields["price"].label_from_instance(price)
        assert event.name in libelle
        assert price.name in libelle

        price.delete()


def test_admin_reservation_add_email_field_est_un_emailfield():
    """
    Garde-fou : le champ "email" du formulaire doit rester un EmailField.
    S'il redevient un ModelChoiceField, save() repasse un objet TibilletUser a
    get_or_create_user et le crash Sentry 7574740199 revient.
    / Guard: the form "email" field must stay an EmailField.
    """
    from django import forms

    from Administration.admin_tenant import ReservationAddAdmin
    from BaseBillet.models import Price

    champ_email = ReservationAddAdmin.base_fields["email"]
    assert isinstance(champ_email, forms.EmailField), (
        "Le champ email doit etre un EmailField (saisie texte), "
        "pas un ModelChoiceField — cf. Sentry 7574740199."
    )

    # Le champ tarif doit lister des Price (et non des PriceSold).
    # / The rate field must list Price objects (not PriceSold).
    champ_price = ReservationAddAdmin.base_fields["price"]
    assert champ_price.queryset.model is Price, (
        "Le champ tarif doit lister les Price des events futurs, pas les PriceSold."
    )
