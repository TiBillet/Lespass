"""
Tests pour comptabilite/services.py — RapportComptableService.
/ Tests for comptabilite/services.py — RapportComptableService.

LOCALISATION : tests/pytest/test_comptabilite_service.py

Meme pattern que test_comptabilite_admin.py : live dev DB, fixtures
django_db_setup + _enable_db_access. Necessaire car django-tenants
requiert un schema reel pour les modeles TENANT_APPS.
/ Same pattern as test_comptabilite_admin.py: live dev DB.
"""
import uuid
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


# ---------------------------------------------------------------------------
# Live dev DB pattern (same as test_comptabilite_admin.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    """No test DB creation — use the existing dev DB."""
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    """Disable pytest-django's DB access blocker for the session."""
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers : fixture pour creer des LigneArticle de test rapidement
# / Helper: fixture to quickly create test LigneArticle rows
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_lespass():
    """Retourne le tenant 'lespass' (ou le premier non-public)."""
    from Customers.models import Client
    t = Client.objects.exclude(schema_name="public").first()
    assert t is not None, "Aucun tenant disponible pour le test"
    return t


@pytest.fixture
def periode_test():
    """Fenetre de 5 minutes autour de maintenant (eligible aux tests)."""
    fin = timezone.now() + timedelta(seconds=10)
    debut = fin - timedelta(minutes=5)
    return debut, fin


def _creer_ligne(tenant, **kwargs):
    """
    Cree une LigneArticle minimale dans le tenant donne.
    / Create a minimal LigneArticle in the given tenant.

    Defaults : amount=1000c, qty=1, status=VALID, payment_method=CASH,
    sale_origin=LESPASS, vat=0, datetime=now.
    """
    from BaseBillet.models import (
        LigneArticle, Product, Price, ProductSold, PriceSold,
        SaleOrigin, PaymentMethod,
    )

    with tenant_context(tenant):
        # On reutilise un Product/Price existant si possible, sinon on cree.
        # Pour les tests, on cree des objets ephemeres avec un nom unique.
        suffix = uuid.uuid4().hex[:8]
        product, _ = Product.objects.get_or_create(
            name=f"TestProduct_{suffix}",
            defaults={
                "categorie_article": Product.BILLET,
            },
        )
        price, _ = Price.objects.get_or_create(
            product=product,
            name=f"TestPrice_{suffix}",
            defaults={"prix": Decimal("10.00")},
        )
        productsold, _ = ProductSold.objects.get_or_create(
            product=product,
            categorie_article=product.categorie_article,
        )
        pricesold, _ = PriceSold.objects.get_or_create(
            productsold=productsold,
            price=price,
            defaults={"prix": Decimal("10.00")},
        )

        defaults = {
            "amount": 1000,
            "qty": Decimal("1"),
            "status": LigneArticle.VALID,
            "payment_method": PaymentMethod.CASH,
            "sale_origin": SaleOrigin.LESPASS,
            "vat": Decimal("0"),
            "pricesold": pricesold,
        }
        defaults.update(kwargs)
        return LigneArticle.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Tests B1
# ---------------------------------------------------------------------------

def test_service_instanciation_ok(tenant_lespass, periode_test):
    """
    Le service s'instancie sans erreur et expose un queryset.
    / The service instantiates without error and exposes a queryset.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from comptabilite.services import RapportComptableService
        from django.db.models import QuerySet
        service = RapportComptableService(debut, fin)
        assert isinstance(service.queryset, QuerySet)
        assert service.datetime_debut == debut
        assert service.datetime_fin == fin


def test_base_queryset_filtre_status(tenant_lespass, periode_test):
    """
    Le queryset de base ne garde que V/P/F/N (exclut UNPAID, CANCELED, etc.).
    / Base queryset only keeps V/P/F/N (excludes UNPAID, CANCELED, etc.).
    """
    debut, fin = periode_test
    crees = []
    with tenant_context(tenant_lespass):
        from BaseBillet.models import LigneArticle
        l_valid = _creer_ligne(tenant_lespass, status=LigneArticle.VALID)
        l_paid = _creer_ligne(tenant_lespass, status=LigneArticle.PAID)
        l_unpaid = _creer_ligne(tenant_lespass, status=LigneArticle.UNPAID)
        l_canceled = _creer_ligne(tenant_lespass, status=LigneArticle.CANCELED)
        crees = [l_valid, l_paid, l_unpaid, l_canceled]

        from comptabilite.services import RapportComptableService
        service = RapportComptableService(debut, fin)
        pks_dans_qs = set(service.queryset.values_list("pk", flat=True))

        assert l_valid.pk in pks_dans_qs
        assert l_paid.pk in pks_dans_qs
        assert l_unpaid.pk not in pks_dans_qs
        assert l_canceled.pk not in pks_dans_qs

        # Cleanup
        for l in crees:
            l.delete()


def test_base_queryset_exclut_laboutik(tenant_lespass, periode_test):
    """
    Une ligne avec sale_origin=LABOUTIK n'entre PAS dans le queryset V1.
    / A line with sale_origin=LABOUTIK is excluded from the V1 queryset.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import SaleOrigin
        l_lespass = _creer_ligne(tenant_lespass, sale_origin=SaleOrigin.LESPASS)
        l_laboutik = _creer_ligne(tenant_lespass, sale_origin=SaleOrigin.LABOUTIK)

        from comptabilite.services import RapportComptableService
        service = RapportComptableService(debut, fin)
        pks_dans_qs = set(service.queryset.values_list("pk", flat=True))

        assert l_lespass.pk in pks_dans_qs
        assert l_laboutik.pk not in pks_dans_qs

        l_lespass.delete()
        l_laboutik.delete()


def test_calculer_totaux_par_moyen_basique(tenant_lespass, periode_test):
    """
    3 lignes (CASH 1000c, CC 2000c, STRIPE_FED 500c) → dict avec 3 cles +
    total + currency_code.
    / 3 lines (CASH 1000c, CC 2000c, STRIPE_FED 500c) → dict with 3 keys + total.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import PaymentMethod
        l_cash = _creer_ligne(tenant_lespass, amount=1000, payment_method=PaymentMethod.CASH)
        l_cc = _creer_ligne(tenant_lespass, amount=2000, payment_method=PaymentMethod.CC)
        l_stripe = _creer_ligne(tenant_lespass, amount=500, payment_method=PaymentMethod.STRIPE_FED)

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_totaux_par_moyen()

        assert "CA" in rapport  # CASH code
        assert "CC" in rapport
        assert "SF" in rapport  # STRIPE_FED code
        assert rapport["CA"]["total"] == 1000
        assert rapport["CA"]["nb"] == 1
        assert rapport["CC"]["total"] == 2000
        assert rapport["SF"]["total"] == 500
        assert rapport["total"] == 3500
        assert rapport["currency_code"] == "EUR"

        l_cash.delete()
        l_cc.delete()
        l_stripe.delete()


def test_calculer_totaux_par_moyen_avec_qty_decimal(tenant_lespass, periode_test):
    """
    Une ligne amount=1000c, qty=2 doit produire un total=2000c (Sum F*F).
    / A line amount=1000c, qty=2 must produce total=2000c (Sum F*F).
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import PaymentMethod
        ligne = _creer_ligne(
            tenant_lespass,
            amount=1000,
            qty=Decimal("2"),
            payment_method=PaymentMethod.CASH,
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_totaux_par_moyen()

        # CASH code = 'CA'
        assert rapport["CA"]["total"] == 2000
        assert rapport["total"] == 2000

        ligne.delete()


# ---------------------------------------------------------------------------
# Tests B2 — TVA, remboursements, adhesions, billets, detail ventes
# ---------------------------------------------------------------------------

def test_calculer_tva_par_taux(tenant_lespass, periode_test):
    """
    2 lignes (vat=5.5%, vat=20%) → dict avec 2 cles "5.50" et "20.00".
    Chaque cle contient {taux, total_ttc, total_ht, total_tva}.
    Verification : total_ttc - total_ht == total_tva (arrondi pres).
    / 2 lines (vat=5.5%, 20%) → dict with 2 keys "5.50" and "20.00".
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        l1 = _creer_ligne(tenant_lespass, amount=1055, vat=Decimal("5.5"))  # TTC 10.55
        l2 = _creer_ligne(tenant_lespass, amount=1200, vat=Decimal("20"))   # TTC 12.00

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_tva()

        assert "5.50" in rapport
        assert "20.00" in rapport

        # 5.5% : ht = round(1055 * 100 / 105.5) = 1000, tva = 55
        assert rapport["5.50"]["total_ttc"] == 1055
        assert rapport["5.50"]["total_ht"] == 1000
        assert rapport["5.50"]["total_tva"] == 55

        # 20% : ht = round(1200 * 100 / 120) = 1000, tva = 200
        assert rapport["20.00"]["total_ttc"] == 1200
        assert rapport["20.00"]["total_ht"] == 1000
        assert rapport["20.00"]["total_tva"] == 200

        l1.delete()
        l2.delete()


def test_calculer_remboursements_status_negatifs(tenant_lespass, periode_test):
    """
    Une CREDIT_NOTE et une REFUNDED → dict avec credit_notes + refunded.
    / A CREDIT_NOTE and a REFUNDED → dict with credit_notes + refunded sub-keys.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import LigneArticle

        l_avoir = _creer_ligne(
            tenant_lespass, amount=-500, status=LigneArticle.CREDIT_NOTE
        )
        l_refund = _creer_ligne(
            tenant_lespass, amount=-300, status=LigneArticle.REFUNDED
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_remboursements()

        assert "credit_notes" in rapport
        assert "refunded" in rapport
        assert rapport["credit_notes"]["total"] == -500
        assert rapport["credit_notes"]["nb"] == 1
        assert rapport["refunded"]["total"] == -300
        assert rapport["refunded"]["nb"] == 1

        l_avoir.delete()
        l_refund.delete()


def test_calculer_adhesions_avec_membership(tenant_lespass, periode_test):
    """
    1 ligne avec membership → dict 'detail' avec cle composite + total + nb.
    / 1 line with membership → dict with composite key + total + nb.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import (
            Membership, Product, Price, PriceSold, ProductSold,
            PaymentMethod, LigneArticle,
        )
        from AuthBillet.models import TibilletUser

        # Cree un user, un produit adhesion + prix, puis une Membership.
        suffix = uuid.uuid4().hex[:8]
        user, _ = TibilletUser.objects.get_or_create(
            email=f"test_adh_{suffix}@example.com",
            defaults={"is_active": True},
        )
        product, _ = Product.objects.get_or_create(
            name=f"Adh_{suffix}",
            defaults={"categorie_article": Product.ADHESION},
        )
        price, _ = Price.objects.get_or_create(
            product=product,
            name=f"Tarif_{suffix}",
            defaults={"prix": Decimal("15.00")},
        )
        productsold, _ = ProductSold.objects.get_or_create(
            product=product,
            categorie_article=product.categorie_article,
        )
        pricesold, _ = PriceSold.objects.get_or_create(
            productsold=productsold, price=price,
            defaults={"prix": Decimal("15.00")},
        )
        membership = Membership.objects.create(
            user=user,
            price=price,
            contribution_value=Decimal("15.00"),
        )

        ligne = LigneArticle.objects.create(
            amount=1500, qty=Decimal("1"),
            status=LigneArticle.VALID,
            payment_method=PaymentMethod.STRIPE_FED,
            pricesold=pricesold,
            membership=membership,
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_adhesions()

        assert rapport["total"] == 1500
        assert rapport["nb"] == 1
        assert len(rapport["detail"]) == 1
        # cle = produit_uuid__tarif_uuid__moyen
        key = f"{product.uuid}__{price.uuid}__SF"
        assert key in rapport["detail"]
        assert rapport["detail"][key]["nom_produit"] == product.name
        assert rapport["detail"][key]["nom_tarif"] == price.name
        assert rapport["detail"][key]["moyen_paiement"] == "SF"
        assert rapport["detail"][key]["total"] == 1500
        assert rapport["detail"][key]["nb"] == 1

        ligne.delete()
        membership.delete()


def test_calculer_billets_avec_reservation(tenant_lespass, periode_test):
    """
    1 ligne avec reservation+event → dict 'detail' avec cle composite event/produit/tarif.
    / 1 line with reservation+event → dict with composite key event/produit/tarif.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import (
            Reservation, Event, Product, Price, PriceSold, ProductSold,
            PaymentMethod, LigneArticle,
        )
        from AuthBillet.models import TibilletUser

        suffix = uuid.uuid4().hex[:8]
        user, _ = TibilletUser.objects.get_or_create(
            email=f"test_bil_{suffix}@example.com",
            defaults={"is_active": True},
        )
        event = Event.objects.create(
            name=f"Concert_{suffix}",
            datetime=timezone.now() + timedelta(days=10),
        )
        product, _ = Product.objects.get_or_create(
            name=f"Billet_{suffix}",
            defaults={"categorie_article": Product.BILLET},
        )
        price, _ = Price.objects.get_or_create(
            product=product, name=f"Plein_{suffix}",
            defaults={"prix": Decimal("20.00")},
        )
        productsold, _ = ProductSold.objects.get_or_create(
            product=product,
            categorie_article=product.categorie_article,
        )
        pricesold, _ = PriceSold.objects.get_or_create(
            productsold=productsold, price=price,
            defaults={"prix": Decimal("20.00")},
        )
        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
        )
        ligne = LigneArticle.objects.create(
            amount=2000, qty=Decimal("1"),
            status=LigneArticle.VALID,
            payment_method=PaymentMethod.STRIPE_FED,
            pricesold=pricesold,
            reservation=reservation,
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_billets()

        assert rapport["nb"] == 1
        assert rapport["total"] == 2000
        key = f"{event.uuid}__{product.uuid}__{price.uuid}"
        assert key in rapport["detail"]
        assert rapport["detail"][key]["nom_event"] == event.name
        assert rapport["detail"][key]["nom_produit"] == product.name
        assert rapport["detail"][key]["nom_tarif"] == price.name
        assert rapport["detail"][key]["nb"] == 1
        assert rapport["detail"][key]["total"] == 2000

        ligne.delete()
        reservation.delete()
        # stdimage enregistre un post_delete par field d'image via une instance method.
        # Si l'image n'est pas set, le callback crashe sur os.path.splitext(None).
        # On desactive temporairement TOUS les receivers post_delete pour Event.
        # / stdimage registers a post_delete per image field via bound method.
        # If image is not set, callback crashes on os.path.splitext(None).
        # Temporarily disable ALL post_delete receivers for Event.
        from django.db.models.signals import post_delete
        from django.utils.module_loading import import_string
        import django.dispatch
        event_uid = id(Event)
        # Sauvegarde et suppression temporaire des receivers lies a Event
        # / Save and temporarily remove receivers linked to Event
        saved_receivers = []
        remaining_receivers = []
        for receiver in post_delete.receivers:
            # Chaque receiver est un tuple (key, weakref/callable)
            # key = (id(dispatch_uid ou func), id(sender) ou NONE_ID)
            lookup_key = receiver[0]
            sender_id = lookup_key[1]
            if sender_id == event_uid:
                saved_receivers.append(receiver)
            else:
                remaining_receivers.append(receiver)
        post_delete.receivers = remaining_receivers
        try:
            event.delete()
        finally:
            post_delete.receivers = remaining_receivers + saved_receivers


def test_calculer_detail_ventes_groupe_par_categorie(tenant_lespass, periode_test):
    """
    Plusieurs lignes (BILLET + ADHESION) groupees par categorie d'article.
    / Multiple lines grouped by article category.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import Product, PaymentMethod, LigneArticle

        # 1 BILLET payant
        l_billet = _creer_ligne(
            tenant_lespass, amount=1000, qty=Decimal("1"),
            payment_method=PaymentMethod.STRIPE_FED, vat=Decimal("20"),
        )
        # 1 ligne offerte du meme type (vat=0)
        l_offert = _creer_ligne(
            tenant_lespass, amount=0, qty=Decimal("1"),
            payment_method=PaymentMethod.FREE, vat=Decimal("0"),
            pricesold=l_billet.pricesold,  # meme produit pour grouper
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_detail_ventes()

        # La categorie est BILLET (defaut de _creer_ligne)
        assert Product.BILLET in rapport
        cat = rapport[Product.BILLET]
        assert isinstance(cat["articles"], list)
        # 1 seul article (les 2 lignes utilisent le meme produit via pricesold partage)
        assert len(cat["articles"]) == 1
        article = cat["articles"][0]
        assert article["qty_payants"] == 1.0
        assert article["qty_offerts"] == 1.0
        assert article["qty_total"] == 2.0
        assert article["total_ttc"] == 1000  # seul l_billet contribue (l_offert est 0)
        # Verifier qu'au moins total_ht et total_tva sont des int
        assert isinstance(article["total_ht"], int)
        assert isinstance(article["total_tva"], int)

        l_billet.delete()
        l_offert.delete()


# ---------------------------------------------------------------------------
# Tests B3 — synthese, infos legales, hash, rapport complet
# ---------------------------------------------------------------------------

def test_calculer_synthese_operations(tenant_lespass, periode_test):
    """
    Tableau croise : type d'operation x moyen de paiement.
    / Cross table: operation type x payment method.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from BaseBillet.models import PaymentMethod
        # 1 billet en STRIPE_FED, 1 adhesion en CASH
        # Pour eviter le piege Event/stdimage, on cree directement les
        # objets Reservation/Membership via factories minimales.
        from BaseBillet.models import (
            Reservation, Membership, Event, Product, Price, PriceSold, ProductSold,
            LigneArticle,
        )
        from AuthBillet.models import TibilletUser
        from django.db.models.signals import post_delete

        suffix = uuid.uuid4().hex[:8]
        user, _ = TibilletUser.objects.get_or_create(
            email=f"test_syn_{suffix}@example.com",
            defaults={"is_active": True},
        )
        event = Event.objects.create(
            name=f"E_{suffix}",
            datetime=timezone.now() + timedelta(days=1),
        )
        product, _ = Product.objects.get_or_create(
            name=f"P_{suffix}",
            defaults={"categorie_article": Product.BILLET},
        )
        price, _ = Price.objects.get_or_create(
            product=product, name=f"T_{suffix}",
            defaults={"prix": Decimal("10.00")},
        )
        productsold, _ = ProductSold.objects.get_or_create(
            product=product, categorie_article=product.categorie_article,
        )
        pricesold, _ = PriceSold.objects.get_or_create(
            productsold=productsold, price=price,
            defaults={"prix": Decimal("10.00")},
        )
        reservation = Reservation.objects.create(user_commande=user, event=event)
        membership = Membership.objects.create(user=user, price=price,
                                                contribution_value=Decimal("10.00"))

        l_billet = LigneArticle.objects.create(
            amount=1000, qty=Decimal("1"), status=LigneArticle.VALID,
            payment_method=PaymentMethod.STRIPE_FED, pricesold=pricesold,
            reservation=reservation,
        )
        l_adh = LigneArticle.objects.create(
            amount=500, qty=Decimal("1"), status=LigneArticle.VALID,
            payment_method=PaymentMethod.CASH, pricesold=pricesold,
            membership=membership,
        )

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).calculer_synthese_operations()

        assert "vente_billets" in rapport
        assert "vente_adhesions" in rapport
        assert "remboursements" in rapport
        assert rapport["vente_billets"].get("SF") == 1000
        assert rapport["vente_adhesions"].get("CA") == 500
        # Pas de remboursement cree → vide ou pas de cle
        assert rapport["remboursements"] in ({}, {None: 0})

        l_billet.delete()
        l_adh.delete()
        # Cleanup Event (stdimage workaround)
        receivers_to_restore = []
        for sender_key, receiver_dict in list(post_delete.receivers):
            if sender_key[1] == id(Event):
                receivers_to_restore.append((sender_key, receiver_dict))
                post_delete.receivers.remove((sender_key, receiver_dict))
        try:
            reservation.delete()
            event.delete()
            membership.delete()
        finally:
            post_delete.receivers.extend(receivers_to_restore)


def test_calculer_infos_legales_depuis_configuration(tenant_lespass, periode_test):
    """
    Recupere les infos legales depuis Configuration.get_solo().
    / Recovers legal info from Configuration singleton.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from comptabilite.services import RapportComptableService
        infos = RapportComptableService(debut, fin).calculer_infos_legales()

        # 8 cles attendues
        for k in ("organisation", "adresse", "code_postal", "ville",
                  "siren", "tva_number", "email", "phone"):
            assert k in infos, f"Cle manquante : {k}"
            assert isinstance(infos[k], str), f"{k} doit etre str (vide ou non)"


def test_calculer_hash_lignes_stable_et_change_avec_modif(tenant_lespass, periode_test):
    """
    Meme queryset → meme hash. Modifier une ligne → hash different.
    / Same queryset → same hash. Modify a line → hash changes.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        ligne = _creer_ligne(tenant_lespass, amount=1500)

        from comptabilite.services import RapportComptableService
        hash1 = RapportComptableService(debut, fin).calculer_hash_lignes()
        hash2 = RapportComptableService(debut, fin).calculer_hash_lignes()
        assert hash1 == hash2, "Meme queryset doit produire le meme hash"
        assert len(hash1) == 64, "SHA-256 hex = 64 chars"

        ligne.amount = 9999
        ligne.save()

        hash3 = RapportComptableService(debut, fin).calculer_hash_lignes()
        assert hash3 != hash1, "Modification d'une ligne doit changer le hash"

        ligne.delete()


def test_generer_rapport_complet_structure(tenant_lespass, periode_test):
    """
    generer_rapport_complet() retourne dict avec EXACTEMENT 9 cles racine.
    / Returns dict with EXACTLY 9 root keys.
    """
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).generer_rapport_complet()

        cles_attendues = {
            "totaux_par_moyen", "detail_ventes", "tva",
            "adhesions", "billets", "remboursements",
            "synthese_operations", "infos_legales", "meta",
        }
        assert set(rapport.keys()) == cles_attendues, (
            f"Cles inattendues. Reel : {set(rapport.keys())}"
        )
        # Verifier les 3 cles de meta
        assert "datetime_debut" in rapport["meta"]
        assert "datetime_fin" in rapport["meta"]
        assert "schema" in rapport["meta"]


def test_generer_rapport_complet_serialisable_json(tenant_lespass, periode_test):
    """
    json.dumps(rapport) doit fonctionner sans erreur.
    / json.dumps(rapport) must work without error.
    """
    import json
    debut, fin = periode_test
    with tenant_context(tenant_lespass):
        ligne = _creer_ligne(tenant_lespass, amount=1000, vat=Decimal("20"))

        from comptabilite.services import RapportComptableService
        rapport = RapportComptableService(debut, fin).generer_rapport_complet()

        # Doit etre serialisable JSON sans crash
        payload = json.dumps(rapport)
        assert isinstance(payload, str)
        assert len(payload) > 100  # contenu non vide

        ligne.delete()


# ---------------------------------------------------------------------------
# Tests B4 — End-to-end: tasks.generer_cloture_pour_tenant
# ---------------------------------------------------------------------------

def test_generer_cloture_pour_tenant_cree_une_cloture(tenant_lespass):
    """
    L'appel a generer_cloture_pour_tenant cree une ClotureCaisse en base.
    / Calling generer_cloture_pour_tenant creates a ClotureCaisse in DB.
    """
    # On choisit une periode passee pour eviter les races avec d'autres tests
    fin = timezone.now() - timedelta(days=30)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant_lespass):
        from comptabilite.models import ClotureCaisse
        # Cleanup au cas ou une cloture du test precedent existe
        ClotureCaisse.objects.filter(
            datetime_debut=debut, datetime_fin=fin,
        ).delete()

        from comptabilite.tasks import generer_cloture_pour_tenant
        uuid_returned = generer_cloture_pour_tenant(
            schema_name=tenant_lespass.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )

        assert uuid_returned is not None, "La tache doit retourner l'UUID de la cloture creee"

        cloture = ClotureCaisse.objects.get(uuid=uuid_returned)
        assert cloture.niveau == "J"
        assert cloture.numero_sequentiel >= 1
        assert cloture.datetime_debut == debut
        assert cloture.datetime_fin == fin
        assert isinstance(cloture.rapport_json, dict)
        # 8 sections + meta = 9 cles
        assert len(cloture.rapport_json.keys()) == 9
        assert "totaux_par_moyen" in cloture.rapport_json
        assert len(cloture.hash_lignes) == 64

        # Cleanup
        cloture.delete()


def test_generer_cloture_idempotent(tenant_lespass):
    """
    Deux appels avec les memes bornes → 1 seule cloture (idempotence).
    / Two calls with same bounds → 1 single closure (idempotent).
    """
    fin = timezone.now() - timedelta(days=60)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant_lespass):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(
            datetime_debut=debut, datetime_fin=fin,
        ).delete()

        from comptabilite.tasks import generer_cloture_pour_tenant
        uuid1 = generer_cloture_pour_tenant(
            schema_name=tenant_lespass.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
        uuid2 = generer_cloture_pour_tenant(
            schema_name=tenant_lespass.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )

        assert uuid1 == uuid2, "L'idempotence doit retourner le meme UUID"
        # Verifier qu'il n'y a qu'une seule cloture pour cette periode
        clotures = ClotureCaisse.objects.filter(
            datetime_debut=debut, datetime_fin=fin,
        )
        assert clotures.count() == 1

        clotures.first().delete()
