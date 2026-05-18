"""
Helper du management command `demo_data_v2` : genere un jeu de ventes
comptables de demo a chiffres ronds sur le tenant `lespass`.
/ Helper for `demo_data_v2`: seeds round-number accounting sales on `lespass`.

LOCALISATION : Administration/management/commands/_demo_data_v2_ventes.py

Couvre les 13 cas tracables dans `LigneArticle` (Option A — scope LigneArticle
uniquement). Les cas hors scope (versements inter-tenants, recharges wallet
federe pures, trigger gift, refund crowd) sont documentes dans
TECH_DOC/SESSIONS/TODO/COMPTABILITE-inter-tenants.md et signales en sortie
de commande.

Strategie technique :
- Toutes les LigneArticle sont creees DIRECTEMENT en status final
  (VALID / FREERES / CREDIT_NOTE / REFUNDED). Cela saute les signaux
  pre_save de transition d'etat (cf. tests/PIEGES.md) et evite les effets
  de bord (envoi mail, push Fedow, ping LaBoutik).
- Les PriceSold sont crees avec `id_price_stripe=None` pour eviter l'appel
  API Stripe declenche par `get_or_create_price_sold()`.
- Les datetimes sont backdates via `.update(datetime=...)` apres creation
  (le `auto_now_add=True` empeche de passer le datetime au create()).
- L'idempotence est assuree par le marqueur de nom de produit `[DEMO] `.
  Le reset filtre les LigneArticle dont le produit a ce prefixe.

/ Tech strategy:
/ - LigneArticle created directly in final status (skip transition signals,
/   side effects like mail/Fedow/LaBoutik).
/ - PriceSold created with id_price_stripe=None (no Stripe API call).
/ - Datetimes backdated via .update() (auto_now_add blocks direct pass).
/ - Idempotency via product name prefix '[DEMO] '.
"""
import logging
import uuid as uuid_lib
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Prefixe utilise pour reperer les produits crees par la demo, pour le reset.
# / Prefix used to mark demo-created products, for reset.
DEMO_PRODUCT_PREFIX = "[DEMO] "


# Mapping Decimal -> code court Price.vat (CharField avec choices).
# 5.5% n'a pas de code court dans le modele → on tombe sur 'NA'. Cela ne pose
# pas de probleme : le rapport compta lit LigneArticle.vat (Decimal) en direct.
# / Decimal -> short Price.vat code. 5.5% has no choice in model → falls back 'NA'.
# / Not a problem: accounting report reads LigneArticle.vat (Decimal) directly.
_VAT_DECIMAL_TO_CODE = {
    Decimal("0"): "NA",
    Decimal("10.00"): "DX",
    Decimal("20.00"): "VG",
    Decimal("8.50"): "HC",
    Decimal("2.20"): "DD",
}


def _produit_demo(name, categorie_article):
    """
    Cree (ou recupere) un Product de demo, marque par DEMO_PRODUCT_PREFIX.
    La TVA est portee par Price (Price.vat code court) et LigneArticle (Decimal).
    / Get/create a demo Product. VAT is on Price (short code) and LigneArticle (Decimal).
    """
    from BaseBillet.models import Product
    nom = f"{DEMO_PRODUCT_PREFIX}{name}"
    produit, _ = Product.objects.get_or_create(
        name=nom,
        defaults={
            "categorie_article": categorie_article,
            "publish": False,  # invisible pour les users finaux
        },
    )
    if produit.categorie_article != categorie_article:
        produit.categorie_article = categorie_article
        produit.save(update_fields=["categorie_article"])
    return produit


def _prix_demo(produit, name, prix_ttc, vat=Decimal("0")):
    """
    Cree (ou recupere) un Price de demo + sa ProductSold + sa PriceSold.
    Les PriceSold sont crees AVEC id_price_stripe=None pour eviter l'appel Stripe.
    Le code Price.vat est mappe depuis le decimal (fallback 'NA' si non trouve).
    / Get/create demo Price + ProductSold + PriceSold (id_price_stripe=None).
    """
    from BaseBillet.models import Price, ProductSold, PriceSold

    vat_code = _VAT_DECIMAL_TO_CODE.get(vat, "NA")

    price, _ = Price.objects.get_or_create(
        product=produit,
        name=name,
        defaults={"prix": prix_ttc, "vat": vat_code},
    )
    if price.prix != prix_ttc or price.vat != vat_code:
        price.prix = prix_ttc
        price.vat = vat_code
        price.save(update_fields=["prix", "vat"])

    productsold, _ = ProductSold.objects.get_or_create(
        product=produit,
        categorie_article=produit.categorie_article,
    )

    pricesold, _ = PriceSold.objects.get_or_create(
        productsold=productsold,
        price=price,
        defaults={
            "prix": prix_ttc,
            # PAS d'appel Stripe — on laisse l'id Stripe null
            # / NO Stripe call — leave Stripe ID null
            "id_price_stripe": None,
        },
    )
    return pricesold


def _user_demo():
    """
    Cree (ou recupere) un user 'demo@example.com' pour la demo.
    / Get/create a 'demo@example.com' user for the demo.
    """
    from AuthBillet.models import TibilletUser
    user, _ = TibilletUser.objects.get_or_create(
        email="demo-ventes@example.com",
        defaults={
            "username": "demo-ventes",
            "is_active": True,
            "first_name": "Demo",
            "last_name": "Ventes",
        },
    )
    return user


def _event_demo(name, datetime_event):
    """
    Cree (ou recupere) un Event de demo, marque par DEMO_PRODUCT_PREFIX.
    / Get/create a demo Event, marked by DEMO_PRODUCT_PREFIX.
    """
    from BaseBillet.models import Event
    nom = f"{DEMO_PRODUCT_PREFIX}{name}"
    event, _ = Event.objects.get_or_create(
        name=nom,
        defaults={
            "datetime": datetime_event,
            "published": False,  # invisible des users finaux / hidden from end users
        },
    )
    return event


def _reservation_demo(user, event, status="V"):
    """
    Cree une Reservation directement en status final (V=VALID par defaut),
    avec mail_send=True pour eviter tout envoi.
    / Create Reservation directly in final status, mail_send=True.
    """
    from BaseBillet.models import Reservation
    return Reservation.objects.create(
        user_commande=user,
        event=event,
        status=status,
        mail_send=True,  # bloque l'envoi de mail si jamais un signal le declenche
    )


def _membership_demo(user, price, payment_method):
    """
    Cree une Membership en status=ONCE (paye en ligne).
    On evite status=ADMIN qui declenche un signal auto-creant une LigneArticle
    (et appelant get_or_create_price_sold -> Stripe).
    / Create Membership in ONCE status. Avoid ADMIN status (auto-creates LigneArticle
    via get_or_create_price_sold which calls Stripe API).
    """
    from BaseBillet.models import Membership
    return Membership.objects.create(
        user=user,
        price=price,
        contribution_value=price.prix,
        payment_method=payment_method,
        status=Membership.ONCE,
        deadline=timezone.now() + timedelta(days=365),
    )


def _creer_lignearticle(
    pricesold,
    qty,
    amount_centimes,
    vat,
    payment_method,
    status,
    sale_origin,
    *,
    reservation=None,
    membership=None,
    asset=None,
):
    """
    Cree une LigneArticle directement dans son status final (VALID, FREERES,
    CREDIT_NOTE, REFUNDED). Saute les signaux de transition (cf. PIEGES.md).
    / Create LigneArticle directly in final status. Skips transition signals.
    """
    from BaseBillet.models import LigneArticle
    return LigneArticle.objects.create(
        pricesold=pricesold,
        qty=qty,
        amount=amount_centimes,
        vat=vat,
        payment_method=payment_method,
        status=status,
        sale_origin=sale_origin,
        reservation=reservation,
        membership=membership,
        asset=asset,
    )


def _backdate_lignes(lignes_uuids, datetime_cible):
    """
    Force le datetime des LigneArticle (contournement auto_now_add).
    / Force datetime of LigneArticle (work around auto_now_add).
    """
    from BaseBillet.models import LigneArticle
    LigneArticle.objects.filter(uuid__in=lignes_uuids).update(datetime=datetime_cible)


def _reset_ventes_demo():
    """
    Supprime les LigneArticle et objets associes (Reservation, Membership,
    Event, Product) crees par la demo (prefixe DEMO_PRODUCT_PREFIX).
    Ordre de suppression : LigneArticle -> Reservation -> Membership -> Event
    -> PriceSold -> Price -> ProductSold -> Product.
    Doit etre appele DANS un tenant_context().
    / Delete demo LigneArticle and related objects. Must be called inside tenant_context().
    """
    from BaseBillet.models import (
        LigneArticle, Reservation, Membership, Event, Product, Price,
        ProductSold, PriceSold,
    )
    pq = LigneArticle.objects.filter(
        pricesold__productsold__product__name__startswith=DEMO_PRODUCT_PREFIX,
    )
    nb_lignes = pq.count()
    pq.delete()

    rq = Reservation.objects.filter(event__name__startswith=DEMO_PRODUCT_PREFIX)
    nb_resa = rq.count()
    rq.delete()

    mq = Membership.objects.filter(price__product__name__startswith=DEMO_PRODUCT_PREFIX)
    nb_mb = mq.count()
    mq.delete()

    eq = Event.objects.filter(name__startswith=DEMO_PRODUCT_PREFIX)
    nb_event = eq.count()
    eq.delete()

    psq = PriceSold.objects.filter(price__product__name__startswith=DEMO_PRODUCT_PREFIX)
    psq.delete()
    pq2 = Price.objects.filter(product__name__startswith=DEMO_PRODUCT_PREFIX)
    pq2.delete()
    psoq = ProductSold.objects.filter(product__name__startswith=DEMO_PRODUCT_PREFIX)
    psoq.delete()
    prq = Product.objects.filter(name__startswith=DEMO_PRODUCT_PREFIX)
    prq.delete()

    logger.info(
        f"Reset demo : {nb_lignes} LigneArticle, {nb_resa} Reservation, "
        f"{nb_mb} Membership, {nb_event} Event supprimes."
    )


def seed_ventes_demo(*, reset=False):
    """
    Cree le jeu de demo des ventes comptables sur le tenant courant.
    Doit etre appele DANS tenant_context(tenant_cible).
    / Seed demo accounting sales on current tenant. Call inside tenant_context().

    Retourne un dict de stats : {nb_lignes_creees, total_ttc_centimes,
    cas_couverts (list[str]), cas_skippes (list[str])}.
    / Returns stats dict.
    """
    from BaseBillet.models import Product, LigneArticle, PaymentMethod, SaleOrigin

    stats = {"nb_lignes_creees": 0, "total_ttc_centimes": 0,
             "cas_couverts": [], "cas_skippes": []}

    if reset:
        _reset_ventes_demo()

    # --- Datetime cible : hier 14:00 heure locale (tombe dans la fenetre J)
    # / Target datetime: yesterday 14:00 local (fits in daily closure window)
    now_local = timezone.localtime()
    hier_14h = (now_local - timedelta(days=1)).replace(
        hour=14, minute=0, second=0, microsecond=0,
    )

    lignes_creees_uuids = []

    with transaction.atomic():
        # --- Acteurs communs / Common actors ---
        user = _user_demo()

        # --- 1. EVENEMENTS : Concert Jazz + Atelier ---
        # / Events
        event_jazz = _event_demo("Concert Jazz", hier_14h + timedelta(days=30))
        event_atelier = _event_demo("Atelier menuiserie", hier_14h + timedelta(days=45))

        # Tarifs Concert Jazz
        # / Concert Jazz pricing
        prix_jazz_plein = _prix_demo(
            _produit_demo("Concert Jazz - Plein", Product.BILLET),
            "Plein", Decimal("20.00"), vat=Decimal("10.00"),
        )
        prix_jazz_reduit = _prix_demo(
            _produit_demo("Concert Jazz - Reduit", Product.BILLET),
            "Reduit", Decimal("16.00"), vat=Decimal("10.00"),
        )
        prix_jazz_offert = _prix_demo(
            _produit_demo("Concert Jazz - Offert", Product.FREERES),
            "Offert", Decimal("0.00"), vat=Decimal("0"),
        )

        # Tarifs Atelier
        # / Atelier pricing
        prix_atelier_normal = _prix_demo(
            _produit_demo("Atelier - Normal", Product.BILLET),
            "Normal", Decimal("30.00"), vat=Decimal("10.00"),
        )
        prix_atelier_solidaire = _prix_demo(
            _produit_demo("Atelier - Solidaire", Product.BILLET),
            "Solidaire", Decimal("10.00"), vat=Decimal("10.00"),
        )

        # === Cas 1 : Concert Jazz Plein x 10 via Stripe Federe (SF) -> 200 EUR
        # / Case 1: Concert Jazz Full x 10 via Stripe Federated -> 200 EUR
        resa1 = _reservation_demo(user, event_jazz)
        l1 = _creer_lignearticle(
            pricesold=prix_jazz_plein, qty=Decimal("10"), amount_centimes=2000,
            vat=Decimal("10.00"), payment_method=PaymentMethod.STRIPE_FED,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.LESPASS, reservation=resa1,
        )
        lignes_creees_uuids.append(l1.uuid)
        stats["cas_couverts"].append("1) Billet Stripe federe (SF) - 200.00 EUR")
        stats["total_ttc_centimes"] += 10 * 2000

        # === Cas 2 : Concert Jazz Reduit x 5 via Stripe Non-Federe (SN) -> 80 EUR
        # / Case 2: Concert Jazz Reduced x 5 via Stripe Non-Federated -> 80 EUR
        resa2 = _reservation_demo(user, event_jazz)
        l2 = _creer_lignearticle(
            pricesold=prix_jazz_reduit, qty=Decimal("5"), amount_centimes=1600,
            vat=Decimal("10.00"), payment_method=PaymentMethod.STRIPE_NOFED,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.LESPASS, reservation=resa2,
        )
        lignes_creees_uuids.append(l2.uuid)
        stats["cas_couverts"].append("2) Billet Stripe non-federe (SN) - 80.00 EUR")
        stats["total_ttc_centimes"] += 5 * 1600

        # === Cas 5 : Concert Jazz Offert x 2 (FREERES) -> 0 EUR
        # / Case 5: Concert Jazz Free x 2 (FREERES) -> 0 EUR
        resa5 = _reservation_demo(user, event_jazz, status="V")
        l5 = _creer_lignearticle(
            pricesold=prix_jazz_offert, qty=Decimal("2"), amount_centimes=0,
            vat=Decimal("0"), payment_method=PaymentMethod.FREE,
            status=LigneArticle.FREERES, sale_origin=SaleOrigin.LESPASS, reservation=resa5,
        )
        lignes_creees_uuids.append(l5.uuid)
        stats["cas_couverts"].append("5) Reservation gratuite (NA/FREERES) - 0.00 EUR")

        # === Cas 3 : Atelier Normal x 4 paye via CB TPE (CC) - admin manuel -> 120 EUR
        # / Case 3: Atelier Normal x 4 paid by POS terminal (CC) admin -> 120 EUR
        resa3 = _reservation_demo(user, event_atelier)
        l3 = _creer_lignearticle(
            pricesold=prix_atelier_normal, qty=Decimal("4"), amount_centimes=3000,
            vat=Decimal("10.00"), payment_method=PaymentMethod.CC,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.ADMIN, reservation=resa3,
        )
        lignes_creees_uuids.append(l3.uuid)
        stats["cas_couverts"].append("3) Billet CB TPE (CC) saisie admin - 120.00 EUR")
        stats["total_ttc_centimes"] += 4 * 3000

        # === Cas 4 : Atelier Solidaire x 2 paye en especes (CA) -> 20 EUR
        # / Case 4: Atelier Solidaire x 2 paid in cash (CA) -> 20 EUR
        resa4 = _reservation_demo(user, event_atelier)
        l4 = _creer_lignearticle(
            pricesold=prix_atelier_solidaire, qty=Decimal("2"), amount_centimes=1000,
            vat=Decimal("10.00"), payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.ADMIN, reservation=resa4,
        )
        lignes_creees_uuids.append(l4.uuid)
        stats["cas_couverts"].append("4) Billet especes (CA) saisie admin - 20.00 EUR")
        stats["total_ttc_centimes"] += 2 * 1000

        # --- 2. ADHESIONS ---
        # / Memberships
        prix_adh_classique = _prix_demo(
            _produit_demo("Adhesion 2026", Product.ADHESION),
            "Adhesion standard", Decimal("25.00"), vat=Decimal("0"),
        )
        prix_adh_soutien = _prix_demo(
            _produit_demo("Adhesion Soutien", Product.ADHESION),
            "Soutien", Decimal("50.00"), vat=Decimal("0"),
        )
        prix_adh_don = _prix_demo(
            _produit_demo("Adhesion par virement", Product.ADHESION),
            "Don associatif", Decimal("100.00"), vat=Decimal("0"),
        )
        prix_adh_sepa = _prix_demo(
            _produit_demo("Adhesion Stripe SEPA", Product.ADHESION),
            "Cotisation pro SEPA", Decimal("30.00"), vat=Decimal("0"),
        )
        prix_adh_recurrent = _prix_demo(
            _produit_demo("Adhesion mensuelle", Product.ADHESION),
            "Mensuel", Decimal("15.00"), vat=Decimal("0"),
        )

        # === Cas 9 : Adhesion en ligne Stripe federe (SF) x 8 -> 200 EUR
        # / Case 9: Online membership via Stripe federated x 8 -> 200 EUR
        for i in range(8):
            mb = _membership_demo(user, prix_adh_classique.price, PaymentMethod.STRIPE_FED)
            l = _creer_lignearticle(
                pricesold=prix_adh_classique, qty=Decimal("1"), amount_centimes=2500,
                vat=Decimal("0"), payment_method=PaymentMethod.STRIPE_FED,
                status=LigneArticle.VALID, sale_origin=SaleOrigin.LESPASS, membership=mb,
            )
            lignes_creees_uuids.append(l.uuid)
            stats["total_ttc_centimes"] += 2500
        stats["cas_couverts"].append("9) Adhesion en ligne Stripe federe (SF) x 8 - 200.00 EUR")

        # === Cas 10a : Adhesion soutien payee en cheque (CH) - manuel admin -> 50 EUR
        # / Case 10a: Support membership paid by check (CH) admin -> 50 EUR
        mb_soutien = _membership_demo(user, prix_adh_soutien.price, PaymentMethod.CHEQUE)
        l10a = _creer_lignearticle(
            pricesold=prix_adh_soutien, qty=Decimal("1"), amount_centimes=5000,
            vat=Decimal("0"), payment_method=PaymentMethod.CHEQUE,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.ADMIN, membership=mb_soutien,
        )
        lignes_creees_uuids.append(l10a.uuid)
        stats["cas_couverts"].append("10a) Adhesion cheque (CH) saisie admin - 50.00 EUR")
        stats["total_ttc_centimes"] += 5000

        # === Cas 10b : Adhesion don par virement bancaire (TR) -> 100 EUR
        # / Case 10b: Donation membership by bank transfer (TR) -> 100 EUR
        mb_don = _membership_demo(user, prix_adh_don.price, PaymentMethod.TRANSFER)
        l10b = _creer_lignearticle(
            pricesold=prix_adh_don, qty=Decimal("1"), amount_centimes=10000,
            vat=Decimal("0"), payment_method=PaymentMethod.TRANSFER,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.ADMIN, membership=mb_don,
        )
        lignes_creees_uuids.append(l10b.uuid)
        stats["cas_couverts"].append("10b) Adhesion virement (TR) saisie admin - 100.00 EUR")
        stats["total_ttc_centimes"] += 10000

        # === Cas 3 (suite) : Adhesion pro Stripe SEPA (SP) -> 30 EUR
        # / Case 3 (continued): Pro membership via Stripe SEPA -> 30 EUR
        mb_sepa = _membership_demo(user, prix_adh_sepa.price, PaymentMethod.STRIPE_SEPA_NOFED)
        lsepa = _creer_lignearticle(
            pricesold=prix_adh_sepa, qty=Decimal("1"), amount_centimes=3000,
            vat=Decimal("0"), payment_method=PaymentMethod.STRIPE_SEPA_NOFED,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.LESPASS, membership=mb_sepa,
        )
        lignes_creees_uuids.append(lsepa.uuid)
        stats["cas_couverts"].append("3) Adhesion Stripe SEPA (SP) - 30.00 EUR")
        stats["total_ttc_centimes"] += 3000

        # === Cas 11 : Adhesion mensuelle recurrente Stripe (SR) echeance -> 15 EUR
        # / Case 11: Monthly recurring Stripe membership (SR) installment -> 15 EUR
        mb_rec = _membership_demo(user, prix_adh_recurrent.price, PaymentMethod.STRIPE_RECURENT)
        l11 = _creer_lignearticle(
            pricesold=prix_adh_recurrent, qty=Decimal("1"), amount_centimes=1500,
            vat=Decimal("0"), payment_method=PaymentMethod.STRIPE_RECURENT,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.WEBHOOK, membership=mb_rec,
        )
        lignes_creees_uuids.append(l11.uuid)
        stats["cas_couverts"].append("11) Adhesion Stripe recurrente (SR) - 15.00 EUR")
        stats["total_ttc_centimes"] += 1500

        # --- 3. VENTES VIA QR / NFC (monnaie locale ou cashless) ---
        # / QR/NFC sales (local currency or cashless)
        prix_biere = _prix_demo(
            _produit_demo("Biere", Product.BADGE),
            "Biere 5e", Decimal("5.00"), vat=Decimal("20.00"),
        )
        prix_soft = _prix_demo(
            _produit_demo("Soft", Product.BADGE),
            "Soft 4e", Decimal("4.00"), vat=Decimal("5.50"),
        )
        prix_sandwich = _prix_demo(
            _produit_demo("Sandwich", Product.BADGE),
            "Sandwich 6e", Decimal("6.00"), vat=Decimal("5.50"),
        )

        # === Cas 12a : Biere x 20 payee en QR (QR) TVA 20% -> 100 EUR
        # / Case 12a: Beer x 20 paid by QR (TVA 20%) -> 100 EUR
        l12a = _creer_lignearticle(
            pricesold=prix_biere, qty=Decimal("20"), amount_centimes=500,
            vat=Decimal("20.00"), payment_method=PaymentMethod.QRCODE_MA,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.QRCODE_MA,
            asset=uuid_lib.uuid4(),
        )
        lignes_creees_uuids.append(l12a.uuid)
        stats["cas_couverts"].append("12a) Biere QR (QR) TVA 20% - 100.00 EUR")
        stats["total_ttc_centimes"] += 20 * 500

        # === Cas 12b : Soft x 10 paye en monnaie locale euro (LE) TVA 5.5% -> 40 EUR
        # / Case 12b: Soft x 10 paid in local euro currency (LE) -> 40 EUR
        l12b = _creer_lignearticle(
            pricesold=prix_soft, qty=Decimal("10"), amount_centimes=400,
            vat=Decimal("5.50"), payment_method=PaymentMethod.LOCAL_EURO,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.NFC_MA,
            asset=uuid_lib.uuid4(),
        )
        lignes_creees_uuids.append(l12b.uuid)
        stats["cas_couverts"].append("12b) Soft monnaie locale euro (LE) TVA 5.5% - 40.00 EUR")
        stats["total_ttc_centimes"] += 10 * 400

        # === Cas 12c : Sandwich x 10 paye en monnaie locale gift (LG) TVA 5.5% -> 60 EUR
        # / Case 12c: Sandwich x 10 paid in local gift currency (LG) -> 60 EUR
        l12c = _creer_lignearticle(
            pricesold=prix_sandwich, qty=Decimal("10"), amount_centimes=600,
            vat=Decimal("5.50"), payment_method=PaymentMethod.LOCAL_GIFT,
            status=LigneArticle.VALID, sale_origin=SaleOrigin.NFC_MA,
            asset=uuid_lib.uuid4(),
        )
        lignes_creees_uuids.append(l12c.uuid)
        stats["cas_couverts"].append("12c) Sandwich monnaie locale gift (LG) TVA 5.5% - 60.00 EUR")
        stats["total_ttc_centimes"] += 10 * 600

        # --- 4. AVOIR (CREDIT_NOTE) sur 1 billet Plein -> -20 EUR
        # / Credit note on 1 Full ticket -> -20 EUR
        # On simule l'avoir comme une 2e ligne avec qty=-1 et status=CREDIT_NOTE.
        # C'est l'effet final que produirait Reservation._creer_avoir().
        # / Simulate credit note as a second line with qty=-1 and status=CREDIT_NOTE.
        l_avoir = _creer_lignearticle(
            pricesold=prix_jazz_plein, qty=Decimal("-1"), amount_centimes=2000,
            vat=Decimal("10.00"), payment_method=PaymentMethod.STRIPE_FED,
            status=LigneArticle.CREDIT_NOTE, sale_origin=SaleOrigin.ADMIN,
            reservation=resa1,
        )
        lignes_creees_uuids.append(l_avoir.uuid)
        stats["cas_couverts"].append("8) Avoir admin sur billet Plein (qty=-1) - -20.00 EUR")
        stats["total_ttc_centimes"] += -1 * 2000

        # --- 5. REMBOURSEMENT (REFUNDED) sur 1 billet Reduit -> -16 EUR
        # / Refund on 1 Reduced ticket -> -16 EUR (HORS total general — calcule
        # separement dans la section remboursements).
        # / Simulate refund (out of general total — separate refund section).
        l_refund = _creer_lignearticle(
            pricesold=prix_jazz_reduit, qty=Decimal("-1"), amount_centimes=1600,
            vat=Decimal("10.00"), payment_method=PaymentMethod.STRIPE_NOFED,
            status=LigneArticle.REFUNDED, sale_origin=SaleOrigin.LESPASS,
            reservation=resa2,
        )
        lignes_creees_uuids.append(l_refund.uuid)
        stats["cas_couverts"].append("7) Remboursement Stripe (qty=-1) - -16.00 EUR (hors total)")
        # On NE compte PAS le remboursement dans total_ttc_centimes : il sort
        # du periometre du rapport via _base_queryset.exclude(status=REFUNDED).
        # / Refund excluded from total: _base_queryset doesn't include REFUNDED.

    # --- Backdate hors transaction (update plus stable que dans atomic) ---
    # / Backdate outside transaction (more stable)
    _backdate_lignes(lignes_creees_uuids, hier_14h)
    stats["nb_lignes_creees"] = len(lignes_creees_uuids)

    return stats


# ============================================================================
# Cas NON couverts dans la compta TiBillet actuelle.
# A documenter en sortie de commande.
# / Cases NOT covered in current TiBillet accounting. To print at command end.
# ============================================================================
CAS_NON_COUVERTS = [
    "Versements bancaires inter-tenants (clearance monnaie locale)",
    "Recharges wallet federe pures (Stripe -> asset sans adhesion)",
    "Trigger d'adhesion qui credite un wallet en gift (LG)",
    "Remboursements de contributions crowdfunding (pas implemente)",
]


WARNING_FOOTER = """
====================================================================
DEMO COMPTABLE GENEREE — Option A (scope LigneArticle uniquement)
====================================================================

Cas NON couverts dans la compta TiBillet actuelle :
{cas_non_couverts}

Ces operations existent dans `fedow_core.Transaction` (V2) mais ne sont
PAS tracees dans `LigneArticle` aujourd'hui — donc absentes du FEC,
des CSV comptables, et du rapport temps reel.

Spec d'integration prevue apres le chantier Fedow V2 :
  TECH_DOC/SESSIONS/TODO/COMPTABILITE-inter-tenants.md
====================================================================
"""


def afficher_warning_cas_non_couverts(stdout):
    """
    Imprime le warning sur les cas non couverts.
    / Print the warning about uncovered cases.
    """
    cas_str = "\n".join(f"  - {cas}" for cas in CAS_NON_COUVERTS)
    stdout.write(WARNING_FOOTER.format(cas_non_couverts=cas_str))
