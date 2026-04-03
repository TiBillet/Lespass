"""
Tests pour RapportBilletterieService.
/ Tests for RapportBilletterieService.

Utilise la base dev existante avec tenant_context.
Cree des donnees de test fraiches pour chaque fixture.
/ Uses the existing dev database with tenant_context.
Creates fresh test data for each fixture.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from BaseBillet.models import (
    Event,
    Ticket,
    LigneArticle,
    Product,
    Price,
    PriceSold,
    ProductSold,
    Reservation,
    PaymentMethod,
    SaleOrigin,
    PromotionalCode,
)
from BaseBillet.reports import RapportBilletterieService


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def event_vide(tenant):
    """
    Un evenement sans aucune vente ni reservation.
    / An event with no sales or reservations.
    """
    from django_tenants.utils import tenant_context

    with tenant_context(tenant):
        event = Event.objects.create(
            name="Test Bilan Vide",
            datetime=timezone.now() + timedelta(days=30),
            jauge_max=100,
        )
        yield event
        # Nettoyage — force SQL delete pour eviter les signals stdimage
        # / Cleanup — force SQL delete to avoid stdimage signals
        Event.objects.filter(pk=event.pk).delete()


@pytest.fixture
def event_jauge_zero(tenant):
    """
    Un evenement avec jauge_max = 0 (pas de division par zero).
    / An event with jauge_max = 0 (no division by zero).
    """
    from django_tenants.utils import tenant_context

    with tenant_context(tenant):
        event = Event.objects.create(
            name="Test Jauge Zero",
            datetime=timezone.now() + timedelta(days=30),
            jauge_max=0,
        )
        yield event
        Event.objects.filter(pk=event.pk).delete()


@pytest.fixture
def event_avec_ventes(tenant):
    """
    Un evenement avec des reservations, tickets, lignes d'articles.
    Cree toutes les donnees necessaires pour tester les 8 methodes.
    / An event with reservations, tickets, article lines.
    Creates all necessary data to test the 8 methods.
    """
    from django_tenants.utils import tenant_context
    from AuthBillet.models import TibilletUser

    with tenant_context(tenant):
        # Creer un user pour les reservations / Create a user for reservations
        user, _ = TibilletUser.objects.get_or_create(
            email="test-rapport-billet@tibillet.test",
            defaults={"username": "test_rapport_billet"},
        )

        # Creer un evenement / Create an event
        event = Event.objects.create(
            name="Test Bilan Complet",
            datetime=timezone.now() + timedelta(days=14),
            jauge_max=200,
        )

        # Creer un produit billet / Create a ticket product
        product = Product.objects.create(
            name="Entree Test Rapport",
            categorie_article=Product.BILLET,
            publish=True,
        )

        # Creer un tarif / Create a rate
        price = Price.objects.create(
            product=product,
            name="Tarif Normal Test",
            prix=Decimal("15.00"),
        )

        # Creer un 2e tarif / Create a 2nd rate
        price_reduit = Price.objects.create(
            product=product,
            name="Tarif Reduit Test",
            prix=Decimal("10.00"),
        )

        # Creer les ProductSold / Create ProductSold instances
        product_sold = ProductSold.objects.create(
            product=product,
            event=event,
        )

        # Creer les PriceSold / Create PriceSold instances
        pricesold_normal = PriceSold.objects.create(
            productsold=product_sold,
            price=price,
            prix=Decimal("15.00"),
        )

        pricesold_reduit = PriceSold.objects.create(
            productsold=product_sold,
            price=price_reduit,
            prix=Decimal("10.00"),
        )

        # -- Reservation 1 : paiement CB, 3 billets tarif normal --
        # / Reservation 1: CC payment, 3 tickets normal rate
        resa1 = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.VALID,
        )

        tickets_resa1 = []
        for i in range(3):
            ticket = Ticket.objects.create(
                reservation=resa1,
                pricesold=pricesold_normal,
                status=Ticket.NOT_SCANNED,
                first_name=f"Normal{i}",
                last_name="Test",
                sale_origin=SaleOrigin.LESPASS,
                payment_method=PaymentMethod.STRIPE_NOFED,
            )
            tickets_resa1.append(ticket)

        # Lignes d'articles pour resa1 (3 x 1500 centimes = 4500)
        # / Article lines for resa1 (3 x 1500 cents = 4500)
        for i in range(3):
            LigneArticle.objects.create(
                pricesold=pricesold_normal,
                reservation=resa1,
                amount=1500,
                qty=1,
                vat=Decimal("0"),
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.LESPASS,
                payment_method=PaymentMethod.STRIPE_NOFED,
            )

        # -- Reservation 2 : paiement especes, 2 billets tarif reduit, canal ADMIN --
        # / Reservation 2: cash payment, 2 tickets reduced rate, ADMIN channel
        resa2 = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.VALID,
        )

        for i in range(2):
            Ticket.objects.create(
                reservation=resa2,
                pricesold=pricesold_reduit,
                status=Ticket.SCANNED,
                first_name=f"Reduit{i}",
                last_name="Test",
                sale_origin=SaleOrigin.ADMIN,
                payment_method=PaymentMethod.CASH,
                scanned_at=timezone.now() - timedelta(hours=1, minutes=15 * i),
            )

        for i in range(2):
            LigneArticle.objects.create(
                pricesold=pricesold_reduit,
                reservation=resa2,
                amount=1000,
                qty=1,
                vat=Decimal("0"),
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
                payment_method=PaymentMethod.CASH,
            )

        # -- 1 billet offert (FREE) --
        resa3 = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.VALID,
        )

        Ticket.objects.create(
            reservation=resa3,
            pricesold=pricesold_normal,
            status=Ticket.NOT_SCANNED,
            first_name="Offert",
            last_name="Test",
            sale_origin=SaleOrigin.LESPASS,
            payment_method=PaymentMethod.FREE,
        )

        LigneArticle.objects.create(
            pricesold=pricesold_normal,
            reservation=resa3,
            amount=0,
            qty=1,
            vat=Decimal("0"),
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.LESPASS,
            payment_method=PaymentMethod.FREE,
        )

        # -- 1 billet annule --
        resa4 = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.CANCELED,
        )

        Ticket.objects.create(
            reservation=resa4,
            pricesold=pricesold_normal,
            status=Ticket.CANCELED,
            first_name="Annule",
            last_name="Test",
        )

        # -- 1 ligne remboursee --
        LigneArticle.objects.create(
            pricesold=pricesold_normal,
            reservation=resa1,
            amount=1500,
            qty=1,
            vat=Decimal("0"),
            status=LigneArticle.REFUNDED,
            sale_origin=SaleOrigin.LESPASS,
            payment_method=PaymentMethod.STRIPE_NOFED,
        )

        yield {
            "event": event,
            "user": user,
            "product": product,
            "price": price,
            "price_reduit": price_reduit,
            "product_sold": product_sold,
            "pricesold_normal": pricesold_normal,
            "pricesold_reduit": pricesold_reduit,
            "reservations": [resa1, resa2, resa3, resa4],
        }

        # Nettoyage dans l'ordre inverse des FK (queryset.delete pour eviter signals stdimage)
        # / Cleanup in reverse FK order (queryset.delete to avoid stdimage signals)
        LigneArticle.objects.filter(reservation__event=event).delete()
        Ticket.objects.filter(reservation__event=event).delete()
        Reservation.objects.filter(event=event).delete()
        PriceSold.objects.filter(
            pk__in=[pricesold_normal.pk, pricesold_reduit.pk]
        ).delete()
        ProductSold.objects.filter(pk=product_sold.pk).delete()
        Event.objects.filter(pk=event.pk).delete()
        Price.objects.filter(pk__in=[price.pk, price_reduit.pk]).delete()
        Product.objects.filter(pk=product.pk).delete()


@pytest.fixture
def event_avec_promo(tenant):
    """
    Un evenement avec un code promo utilise.
    / An event with a used promotional code.
    """
    from django_tenants.utils import tenant_context
    from AuthBillet.models import TibilletUser

    with tenant_context(tenant):
        user, _ = TibilletUser.objects.get_or_create(
            email="test-rapport-promo@tibillet.test",
            defaults={"username": "test_rapport_promo"},
        )

        event = Event.objects.create(
            name="Test Promo Bilan",
            datetime=timezone.now() + timedelta(days=21),
            jauge_max=50,
        )

        product = Product.objects.create(
            name="Entree Promo Test",
            categorie_article=Product.BILLET,
            publish=True,
        )

        price = Price.objects.create(
            product=product,
            name="Tarif Promo Test",
            prix=Decimal("20.00"),
        )

        promo_code = PromotionalCode.objects.create(
            name="PROMO_RAPPORT_TEST",
            discount_rate=Decimal("25.00"),
            product=product,
        )

        product_sold = ProductSold.objects.create(
            product=product,
            event=event,
        )

        pricesold = PriceSold.objects.create(
            productsold=product_sold,
            price=price,
            prix=Decimal("15.00"),  # prix apres reduction / after discount
        )

        resa = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.VALID,
        )

        # 2 lignes avec code promo (paye 1500 au lieu de 2000 catalogue)
        # / 2 lines with promo code (paid 1500 instead of 2000 catalog)
        for i in range(2):
            Ticket.objects.create(
                reservation=resa,
                pricesold=pricesold,
                status=Ticket.NOT_SCANNED,
                first_name=f"Promo{i}",
                last_name="Test",
                payment_method=PaymentMethod.STRIPE_NOFED,
            )
            LigneArticle.objects.create(
                pricesold=pricesold,
                reservation=resa,
                amount=1500,
                qty=1,
                vat=Decimal("0"),
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.LESPASS,
                payment_method=PaymentMethod.STRIPE_NOFED,
                promotional_code=promo_code,
            )

        yield {
            "event": event,
            "promo_code": promo_code,
        }

        # Nettoyage (queryset.delete pour eviter signals stdimage)
        # / Cleanup (queryset.delete to avoid stdimage signals)
        LigneArticle.objects.filter(reservation__event=event).delete()
        Ticket.objects.filter(reservation__event=event).delete()
        Reservation.objects.filter(event=event).delete()
        PriceSold.objects.filter(pk=pricesold.pk).delete()
        ProductSold.objects.filter(pk=product_sold.pk).delete()
        Event.objects.filter(pk=event.pk).delete()
        PromotionalCode.objects.filter(pk=promo_code.pk).delete()
        Price.objects.filter(pk=price.pk).delete()
        Product.objects.filter(pk=product.pk).delete()


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestRapportBilletterieService:
    """Tests pour RapportBilletterieService."""

    # --- 1. Synthese event sans ventes ---
    def test_synthese_event_sans_ventes(self, tenant, event_vide):
        """
        Un event vide doit retourner tous les compteurs a 0.
        / An empty event must return all counters at 0.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_vide)
            synthese = service.calculer_synthese()

            assert synthese["jauge_max"] == 100
            assert synthese["billets_vendus"] == 0
            assert synthese["billets_scannes"] == 0
            assert synthese["billets_annules"] == 0
            assert synthese["no_show"] == 0
            assert synthese["ca_ttc"] == 0
            assert synthese["remboursements"] == 0
            assert synthese["ca_net"] == 0
            assert synthese["taux_remplissage"] == 0.0

    # --- 2. Synthese event avec ventes ---
    def test_synthese_event_avec_ventes(self, tenant, event_avec_ventes):
        """
        Verifier les totaux de la synthese avec les donnees de test.
        / Verify summary totals with test data.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            synthese = service.calculer_synthese()

            # 3 NOT_SCANNED (resa1) + 2 SCANNED (resa2) + 1 NOT_SCANNED (offert) = 6 vendus
            assert synthese["billets_vendus"] == 6
            # 2 SCANNED (resa2)
            assert synthese["billets_scannes"] == 2
            # 1 annule (resa4)
            assert synthese["billets_annules"] == 1
            # no_show = 6 - 2 = 4
            assert synthese["no_show"] == 4
            # CA TTC = 3*1500 + 2*1000 + 0 = 6500 centimes
            assert synthese["ca_ttc"] == 6500
            # 1 remboursement de 1500
            assert synthese["remboursements"] == 1500
            # CA net = 6500 - 1500 = 5000
            assert synthese["ca_net"] == 5000
            # Taux remplissage = 6/200 * 100 = 3.0
            assert synthese["taux_remplissage"] == 3.0

    # --- 3. Ventes par tarif ---
    def test_ventes_par_tarif(self, tenant, event_avec_ventes):
        """
        Verifier les cles presentes et la coherence des totaux.
        / Verify keys are present and totals are consistent.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            tarifs = service.calculer_ventes_par_tarif()

            assert isinstance(tarifs, list)
            assert len(tarifs) >= 2  # au moins 2 tarifs / at least 2 rates

            # Verifier les cles de chaque tarif / Verify keys of each rate
            cles_attendues = {
                "nom",
                "price_uuid",
                "vendus",
                "offerts",
                "ca_ttc",
                "ca_ht",
                "tva",
                "taux_tva",
                "rembourses",
            }
            for tarif in tarifs:
                assert cles_attendues.issubset(tarif.keys())

            # Le total CA TTC des tarifs doit correspondre a la synthese
            # / Total rate revenue must match the summary
            total_ca_tarifs = sum(t["ca_ttc"] for t in tarifs)
            synthese = service.calculer_synthese()
            assert total_ca_tarifs == synthese["ca_ttc"]

    # --- 4. Par moyen de paiement ---
    def test_par_moyen_paiement(self, tenant, event_avec_ventes):
        """
        Le total des montants par moyen doit egaler le CA TTC.
        / Total amounts by payment method must equal gross revenue.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            moyens = service.calculer_par_moyen_paiement()

            assert isinstance(moyens, list)
            assert len(moyens) >= 2  # au moins CB + especes / at least CC + cash

            total_montant = sum(m["montant"] for m in moyens)
            synthese = service.calculer_synthese()
            assert total_montant == synthese["ca_ttc"]

            # Verifier les cles / Verify keys
            for moyen in moyens:
                assert "code" in moyen
                assert "label" in moyen
                assert "montant" in moyen
                assert "pourcentage" in moyen
                assert "nb_billets" in moyen

    # --- 5. Par canal masque si canal unique ---
    def test_par_canal_masque_si_canal_unique(self, tenant, event_vide):
        """
        Un event sans ventes retourne None (pas de canal).
        / An event without sales returns None (no channel).
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_vide)
            canaux = service.calculer_par_canal()
            assert canaux is None

    # --- 5b. Par canal avec 2 canaux ---
    def test_par_canal_avec_deux_canaux(self, tenant, event_avec_ventes):
        """
        Un event avec 2 canaux (LESPASS + ADMIN) retourne une liste.
        / An event with 2 channels (LESPASS + ADMIN) returns a list.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            canaux = service.calculer_par_canal()

            # On a des lignes LESPASS et ADMIN => 2 canaux
            assert canaux is not None
            assert isinstance(canaux, list)
            assert len(canaux) >= 2

    # --- 6. Scans basique ---
    def test_scans_basique(self, tenant, event_avec_ventes):
        """
        Verifier les compteurs de scan.
        / Verify scan counters.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            scans = service.calculer_scans()

            assert scans["scannes"] == 2
            assert scans["non_scannes"] == 4  # 3 resa1 + 1 offert
            assert scans["annules"] == 1

            # Les 2 tickets scannes ont scanned_at => tranches_horaires non None
            assert scans["tranches_horaires"] is not None
            assert "labels" in scans["tranches_horaires"]
            assert "data" in scans["tranches_horaires"]

    # --- 7. Codes promo retourne None si aucun ---
    def test_codes_promo_retourne_none_si_aucun(self, tenant, event_vide):
        """
        Un event sans code promo retourne None.
        / An event without promo code returns None.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_vide)
            promos = service.calculer_codes_promo()
            assert promos is None

    # --- 7b. Codes promo avec donnees ---
    def test_codes_promo_avec_donnees(self, tenant, event_avec_promo):
        """
        Un event avec code promo retourne une liste avec manque_a_gagner.
        / An event with promo code returns a list with revenue shortfall.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_promo["event"]
            service = RapportBilletterieService(event)
            promos = service.calculer_codes_promo()

            assert promos is not None
            assert len(promos) == 1

            promo = promos[0]
            assert promo["nom"] == "PROMO_RAPPORT_TEST"
            assert promo["taux_reduction"] == 25.0
            assert promo["utilisations"] == 2
            # manque_a_gagner = (2 * 2000) - (2 * 1500) = 1000 centimes
            assert promo["manque_a_gagner"] == 1000

    # --- 8. Remboursements sans donnees ---
    def test_remboursements_sans_donnees(self, tenant, event_vide):
        """
        Un event sans remboursements retourne nombre=0, taux=0.
        / An event without refunds returns count=0, rate=0.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_vide)
            remb = service.calculer_remboursements()

            assert remb["nombre"] == 0
            assert remb["montant_total"] == 0
            assert remb["taux"] == 0.0

    # --- 8b. Remboursements avec donnees ---
    def test_remboursements_avec_donnees(self, tenant, event_avec_ventes):
        """
        Verifier le taux de remboursement.
        / Verify refund rate.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            remb = service.calculer_remboursements()

            assert remb["nombre"] == 1
            assert remb["montant_total"] == 1500
            # 6 valides + 1 rembourse = 7, taux = 1/7 * 100 ≈ 14.3
            assert remb["taux"] == pytest.approx(14.3, abs=0.1)

    # --- 9. Courbe de ventes ---
    def test_courbe_ventes(self, tenant, event_avec_ventes):
        """
        Verifier que les donnees de la courbe sont cumulees.
        / Verify that curve data is cumulative.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            event = event_avec_ventes["event"]
            service = RapportBilletterieService(event)
            courbe = service.calculer_courbe_ventes()

            assert "labels" in courbe
            assert "datasets" in courbe
            assert len(courbe["datasets"]) == 1

            donnees = courbe["datasets"][0]["data"]
            # Les donnees doivent etre croissantes (cumulees)
            # / Data must be increasing (cumulative)
            for i in range(1, len(donnees)):
                assert donnees[i] >= donnees[i - 1]

            # Le dernier cumul = CA TTC total
            if donnees:
                synthese = service.calculer_synthese()
                assert donnees[-1] == synthese["ca_ttc"]

    # --- 10. Courbe ventes event vide ---
    def test_courbe_ventes_event_vide(self, tenant, event_vide):
        """
        Event sans ventes retourne des listes vides.
        / Event without sales returns empty lists.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_vide)
            courbe = service.calculer_courbe_ventes()

            assert courbe["labels"] == []
            assert courbe["datasets"][0]["data"] == []

    # --- 11. Synthese jauge zero ---
    def test_synthese_jauge_zero(self, tenant, event_jauge_zero):
        """
        Pas de division par zero quand jauge_max = 0.
        / No division by zero when jauge_max = 0.
        """
        from django_tenants.utils import tenant_context

        with tenant_context(tenant):
            service = RapportBilletterieService(event_jauge_zero)
            synthese = service.calculer_synthese()

            assert synthese["jauge_max"] == 0
            assert synthese["taux_remplissage"] == 0.0
