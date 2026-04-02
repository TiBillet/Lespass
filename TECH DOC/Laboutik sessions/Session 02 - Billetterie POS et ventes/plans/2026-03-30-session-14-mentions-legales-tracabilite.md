# Session 14 — Mentions légales tickets + traçabilité impressions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre les tickets de vente conformes LNE (exigences 3 et 9) : mentions légales, ventilation TVA, numéro séquentiel, mention DUPLICATA, et traçabilité des impressions via `ImpressionLog`.

**Architecture:** Modèle `ImpressionLog` pour tracer chaque impression. Enrichissement du formatter de vente avec les infos légales (raison sociale, SIRET, TVA, HT/TTC). Compteur séquentiel de tickets sur `LaboutikConfiguration`. Détection duplicata par comptage des `ImpressionLog` précédents. Le builder ESC/POS est étendu pour rendre les nouvelles sections.

**Tech Stack:** Django 4.2, django-tenants, Celery, ESC/POS (sunmi_cloud_printer)

---

## Fichiers concernés

| Action | Fichier | Responsabilité |
|--------|---------|---------------|
| Créer | `laboutik/migrations/0012_impression_log_compteur_tickets.py` | Migration : ImpressionLog + compteur_tickets |
| Créer | `tests/pytest/test_mentions_legales.py` | 7+ tests session 14 |
| Modifier | `laboutik/models.py` | Ajouter ImpressionLog + compteur_tickets sur LaboutikConfiguration |
| Modifier | `laboutik/printing/formatters.py` | Enrichir formatter_ticket_vente() avec legal + TVA |
| Modifier | `laboutik/printing/escpos_builder.py` | Rendre les nouvelles sections (legal, TVA, duplicata) |
| Modifier | `laboutik/printing/tasks.py` | Créer ImpressionLog avant chaque impression |
| Modifier | `laboutik/views.py` | Passer is_duplicata dans imprimer_ticket() |
| Modifier | `Administration/admin/laboutik.py` | Ajouter pied_ticket + ImpressionLogAdmin |

---

## Contexte clé pour l'implémenteur

### Configuration (BaseBillet.Configuration — singleton par tenant)
Les infos légales sont sur `Configuration.get_solo()` :
- `organisation` : raison sociale
- `adress`, `postal_code`, `city` : adresse
- `siren` : numéro SIRET/SIREN
- `tva_number` : n° TVA intracommunautaire (peut être null → art. 293 B)

### Calcul TVA existant (laboutik/reports.py:159-191)
`calculer_tva()` dans `RapportComptableService` fait déjà : `HT = round(TTC / (1 + taux/100))`.
Le même calcul existe dans `laboutik/integrity.py:calculer_total_ht()`.

### Structure ticket_data existante
```python
{
    "header": {"title": str, "subtitle": str, "date": str},
    "articles": [{"name": str, "qty": int, "price": int, "total": int}],
    "total": {"amount": int, "label": str},
    "qrcode": str or None,
    "footer": [str, ...],
}
```
On ajoute les clés : `"legal"`, `"tva_breakdown"`, `"total_ht"`, `"total_tva"`, `"is_duplicata"`, `"pied_ticket"`, `"receipt_number"`.

### Patron d'impression (laboutik/printing/tasks.py)
`imprimer_async(printer_pk, ticket_data, schema_name)` reçoit un `ticket_data` dict sérialisable JSON. Le formatter construit ce dict, puis la tâche Celery le passe au backend via `imprimer(printer, ticket_data)`.

### Multi-tenant
Tout tourne dans `schema_context(schema_name)` dans les tâches Celery. Les tests utilisent `schema_context('lespass')`.

### Règles FALC
Commentaires bilingues FR/EN, variables explicites, pas de magie.

### Pas de git
Ne faire aucune opération git. Le mainteneur s'en occupe.

---

## Task 1 : Modèle ImpressionLog + compteur_tickets

**Files:**
- Modify: `laboutik/models.py` (après la classe ClotureCaisse, ~ligne 954)
- Modify: `laboutik/models.py` (ajouter `compteur_tickets` sur LaboutikConfiguration, ~ligne 143)
- Create: `laboutik/migrations/0012_impression_log_compteur_tickets.py`

- [ ] **Step 1: Ajouter `compteur_tickets` sur LaboutikConfiguration**

Dans `laboutik/models.py`, après le champ `total_perpetuel` (ligne ~143), ajouter :

```python
# --- Compteur sequentiel de tickets de vente (conformite LNE) ---
# Incremente a chaque ticket de vente imprime. Global au tenant.
# / Sequential receipt counter (LNE compliance). Incremented per printed sale ticket. Global to tenant.
compteur_tickets = models.PositiveIntegerField(
    default=0,
    verbose_name=_("Receipt counter"),
    help_text=_(
        "Compteur sequentiel de tickets de vente. "
        "Incremente automatiquement a chaque impression. "
        "/ Sequential receipt counter. "
        "Auto-incremented on each print."
    ),
)
```

- [ ] **Step 2: Créer le modèle ImpressionLog**

Dans `laboutik/models.py`, après la classe `ClotureCaisse`, ajouter :

```python
class ImpressionLog(models.Model):
    """
    Tracabilite des impressions et envois de justificatifs.
    Conformite LNE exigence 9 : securisation des justificatifs.
    / Print/send tracking for receipts.
    LNE compliance requirement 9: receipt security.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
    )
    datetime = models.DateTimeField(auto_now_add=True)

    # Lien vers la ligne d'article (ticket de vente)
    # / Link to the article line (sale receipt)
    ligne_article = models.ForeignKey(
        'BaseBillet.LigneArticle', on_delete=models.PROTECT,
        null=True, blank=True, related_name='impressions',
    )

    # Pour les tickets multi-lignes (regroupement par uuid_transaction)
    # / For multi-line tickets (grouped by uuid_transaction)
    uuid_transaction = models.UUIDField(
        null=True, blank=True,
        verbose_name=_("Transaction UUID"),
        help_text=_("Regroupe les lignes d'un meme paiement. / Groups lines from the same payment."),
    )

    # Lien vers la cloture (ticket Z)
    # / Link to the closure (Z-ticket)
    cloture = models.ForeignKey(
        ClotureCaisse, on_delete=models.PROTECT,
        null=True, blank=True, related_name='impressions',
    )

    # Operateur qui a lance l'impression
    # / Operator who triggered the print
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL, null=True, blank=True,
    )

    # Imprimante utilisee
    # / Printer used
    printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True,
    )

    TYPE_CHOICES = [
        ('VENTE', _('Sale receipt')),
        ('CLOTURE', _('Closure report')),
        ('COMMANDE', _('Order ticket')),
        ('BILLET', _('Event ticket')),
    ]
    type_justificatif = models.CharField(
        max_length=10, choices=TYPE_CHOICES,
        verbose_name=_("Receipt type"),
    )

    is_duplicata = models.BooleanField(
        default=False,
        verbose_name=_("Duplicate"),
        help_text=_("True si c'est une re-impression. / True if this is a reprint."),
    )

    FORMAT_CHOICES = [('P', _('Paper')), ('E', _('Electronic'))]
    format_emission = models.CharField(
        max_length=1, choices=FORMAT_CHOICES, default='P',
        verbose_name=_("Output format"),
    )

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Print log')
        verbose_name_plural = _('Print logs')

    def __str__(self):
        return f"{self.type_justificatif} — {self.datetime}"
```

- [ ] **Step 3: Générer et appliquer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name impression_log_compteur_tickets
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
```

Attendu : migration créée, appliquée sans erreur, `check` OK.

---

## Task 2 : Enrichir formatter_ticket_vente()

**Files:**
- Modify: `laboutik/printing/formatters.py:24-81`

- [ ] **Step 1: Écrire le test du formatter enrichi**

Dans `tests/pytest/test_mentions_legales.py` :

```python
"""
tests/pytest/test_mentions_legales.py — Tests Session 14 : mentions legales + tracabilite.
/ Tests Session 14: legal mentions + print tracking.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
"""
import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
import uuid as uuid_module

from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Configuration, LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, LaboutikConfiguration, ImpressionLog, Printer,
)

TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-mentions@tibillet.localhost'
        user, _created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente non-cache.
    / The first visible point of sale."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(test_data):
    """Un produit POS avec un prix.
    / A POS product with a price."""
    with schema_context(TENANT_SCHEMA):
        product = Product.objects.filter(
            methode_choices=Product.VENTE,
        ).first()
        price = product.prices.first() if product else None
        return product, price


def _creer_ligne_article_directe(product, price, pv, qty=1, payment_method='CA'):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Simule ce que fait _creer_lignes_articles() dans views.py.
    / Creates a LigneArticle directly in DB (bypassing the view).
    """
    prix_centimes = int(round(price.prix * 100))

    product_sold, _ = ProductSold.objects.get_or_create(
        product=product,
        defaults={'name': product.name},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=price,
        defaults={
            'prix': price.prix,
            'name': price.name or product.name,
        },
    )

    uuid_tx = uuid_module.uuid4()

    from laboutik.integrity import calculer_total_ht, calculer_hmac, obtenir_previous_hmac
    taux_tva = float(price.vat or 0)
    total_ht = calculer_total_ht(prix_centimes, taux_tva)

    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=Decimal(str(qty)),
        amount=prix_centimes,
        vat=price.vat or Decimal('0'),
        payment_method=payment_method,
        sale_origin=SaleOrigin.LABOUTIK,
        status='V',
        point_de_vente=pv,
        uuid_transaction=uuid_tx,
        total_ht=total_ht,
    )

    # Chainage HMAC
    # / HMAC chaining
    config = LaboutikConfiguration.get_solo()
    cle_hmac = config.get_or_create_hmac_key()
    previous_hmac = obtenir_previous_hmac()
    ligne.hmac_hash = calculer_hmac(ligne, cle_hmac, previous_hmac)
    ligne.previous_hmac = previous_hmac
    ligne.save(update_fields=['hmac_hash', 'previous_hmac'])

    return ligne, uuid_tx


class TestFormatterTicketVente:
    """Tests pour le formatter de ticket de vente enrichi.
    / Tests for the enriched sale ticket formatter."""

    def test_ticket_contient_raison_sociale(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir la raison sociale (Configuration.organisation).
        / The ticket must contain the business name."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            config = Configuration.get_solo()
            assert "legal" in ticket_data
            assert ticket_data["legal"]["business_name"] == config.organisation

    def test_ticket_contient_siret(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir le SIRET si disponible.
        / The ticket must contain the SIRET if available."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            assert "legal" in ticket_data
            # Le SIRET peut etre vide dans les donnees de test, mais la cle doit exister
            # / SIRET may be empty in test data, but the key must exist
            assert "siret" in ticket_data["legal"]

    def test_ticket_contient_ventilation_tva(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir la ventilation TVA par taux.
        / The ticket must contain the VAT breakdown by rate."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            assert "tva_breakdown" in ticket_data
            assert isinstance(ticket_data["tva_breakdown"], list)
            # Au moins une entree TVA
            # / At least one VAT entry
            assert len(ticket_data["tva_breakdown"]) >= 1

    def test_ticket_total_ht_ttc(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """total_ht + total_tva = total TTC.
        / total_ht + total_tva = total TTC."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            total_ttc = ticket_data["total"]["amount"]
            total_ht = ticket_data["total_ht"]
            total_tva = ticket_data["total_tva"]

            assert total_ht + total_tva == total_ttc

    def test_tva_non_applicable(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Si pas de tva_number dans Configuration, mention art. 293 B du CGI.
        / If no tva_number in Configuration, mention art. 293 B."""
        with schema_context(TENANT_SCHEMA):
            config = Configuration.get_solo()
            ancien_tva = config.tva_number
            config.tva_number = None
            config.save(update_fields=['tva_number'])

            try:
                product, price = premier_produit_et_prix
                ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

                from laboutik.printing.formatters import formatter_ticket_vente
                ticket_data = formatter_ticket_vente(
                    [ligne], premier_pv, admin_user, 'Especes',
                )

                assert "293 B" in ticket_data["legal"]["tva_number"]
            finally:
                config.tva_number = ancien_tva
                config.save(update_fields=['tva_number'])


class TestImpressionLog:
    """Tests pour la tracabilite des impressions.
    / Tests for print tracking."""

    def test_impression_log_cree(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Apres appel de _creer_impression_log, un ImpressionLog est cree.
        / After calling _creer_impression_log, an ImpressionLog is created."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            # Creer un log manuellement (simule ce que fait imprimer_async)
            # / Create a log manually (simulates what imprimer_async does)
            log = ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=False,
                format_emission='P',
            )
            assert ImpressionLog.objects.filter(uuid_transaction=uuid_tx).exists()
            assert log.is_duplicata is False

    def test_duplicata_marque(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """La 2e impression de la meme transaction est marquee duplicata.
        / The 2nd print of the same transaction is marked as duplicate."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            # Premiere impression
            # / First print
            ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=False,
                format_emission='P',
            )

            # Deuxieme impression — verifier que c'est un duplicata
            # / Second print — verify it's a duplicate
            nb_precedentes = ImpressionLog.objects.filter(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
            ).count()
            est_duplicata = nb_precedentes > 0

            log2 = ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=est_duplicata,
                format_emission='P',
            )
            assert log2.is_duplicata is True
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v -x 2>&1 | head -40
```

Attendu : FAIL sur `test_ticket_contient_raison_sociale` car `"legal"` n'existe pas encore dans ticket_data.

- [ ] **Step 3: Enrichir formatter_ticket_vente()**

Remplacer le contenu de `formatter_ticket_vente()` dans `laboutik/printing/formatters.py:24-81` :

```python
def formatter_ticket_vente(lignes_articles, pv, operateur, moyen_paiement):
    """
    Formate un ticket de vente client (apres paiement).
    Inclut les mentions legales (raison sociale, SIRET, TVA) conformement LNE exigence 3.
    / Formats a customer sale ticket (after payment).
    Includes legal mentions (business name, SIRET, VAT) per LNE requirement 3.

    LOCALISATION : laboutik/printing/formatters.py

    :param lignes_articles: QuerySet ou list de LigneArticle
    :param pv: PointDeVente
    :param operateur: TibilletUser (caissier)
    :param moyen_paiement: str (ex: "Especes", "CB", "NFC")
    :return: dict ticket_data
    """
    from BaseBillet.models import Configuration
    from laboutik.models import LaboutikConfiguration
    from laboutik.integrity import calculer_total_ht

    now = timezone.localtime(timezone.now())

    # --- Infos legales depuis Configuration (singleton du tenant) ---
    # / Legal info from Configuration (tenant singleton)
    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    # Adresse complete
    # / Full address
    parties_adresse = []
    if config.adress:
        parties_adresse.append(config.adress)
    if config.postal_code:
        parties_adresse.append(str(config.postal_code))
    if config.city:
        parties_adresse.append(config.city)
    adresse_complete = " ".join(parties_adresse)

    # TVA : numero ou mention d'exoneration
    # / VAT: number or exemption notice
    tva_display = config.tva_number if config.tva_number else _("TVA non applicable, art. 293 B du CGI")

    # Numero sequentiel du ticket (incremente atomiquement)
    # / Sequential receipt number (atomically incremented)
    from django.db.models import F
    LaboutikConfiguration.objects.filter(pk=laboutik_config.pk).update(
        compteur_tickets=F('compteur_tickets') + 1,
    )
    laboutik_config.refresh_from_db()
    numero_ticket = laboutik_config.compteur_tickets

    legal = {
        "business_name": config.organisation or "",
        "address": adresse_complete,
        "siret": config.siren or "",
        "tva_number": tva_display,
        "receipt_number": f"T-{numero_ticket:06d}",
        "terminal_id": pv.name if pv else "",
    }

    # --- Construire la liste des articles avec taux TVA ---
    # / Build the articles list with VAT rate
    articles = []
    total_centimes = 0
    tva_par_taux = {}

    for ligne in lignes_articles:
        qty = int(ligne.qty)
        amount_centimes = ligne.amount
        article_total = amount_centimes * qty
        total_centimes += article_total

        # Nom du produit via PriceSold → ProductSold
        # / Product name via PriceSold → ProductSold
        product_name = str(ligne.pricesold) if ligne.pricesold else _("Article")

        # Taux TVA de la ligne
        # / VAT rate of the line
        taux_tva = float(ligne.vat or 0)

        articles.append({
            "name": product_name,
            "qty": qty,
            "price": amount_centimes,
            "total": article_total,
            "vat_rate": f"{taux_tva:.2f}",
        })

        # Accumuler la TVA par taux
        # / Accumulate VAT by rate
        cle_tva = f"{taux_tva:.2f}"
        if cle_tva not in tva_par_taux:
            tva_par_taux[cle_tva] = {"rate": cle_tva, "ttc": 0}
        tva_par_taux[cle_tva]["ttc"] += article_total

    # Calculer HT et TVA pour chaque taux
    # / Compute HT and VAT for each rate
    tva_breakdown = []
    total_ht_global = 0
    total_tva_global = 0

    for cle_tva, donnees_tva in tva_par_taux.items():
        taux = float(cle_tva)
        ttc = donnees_tva["ttc"]

        if taux > 0:
            ht = int(round(ttc / (1 + taux / 100)))
            tva_montant = ttc - ht
        else:
            ht = ttc
            tva_montant = 0

        total_ht_global += ht
        total_tva_global += tva_montant

        tva_breakdown.append({
            "rate": cle_tva,
            "ht": ht,
            "tva": tva_montant,
            "ttc": ttc,
        })

    # Nom de l'operateur
    # / Operator name
    operateur_name = ""
    if operateur:
        operateur_name = operateur.email if operateur.email else str(operateur)

    # Pied de ticket personnalise
    # / Custom receipt footer
    pied_ticket = laboutik_config.pied_ticket or ""

    footer_lines = []
    if pied_ticket:
        footer_lines.append(pied_ticket)
    footer_lines.append(_("Merci de votre visite !"))

    return {
        "header": {
            "title": pv.name if pv else "",
            "subtitle": operateur_name,
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "legal": legal,
        "articles": articles,
        "total": {
            "amount": total_centimes,
            "label": moyen_paiement,
        },
        "tva_breakdown": tva_breakdown,
        "total_ht": total_ht_global,
        "total_tva": total_tva_global,
        "is_duplicata": False,
        "receipt_number": f"T-{numero_ticket:06d}",
        "pied_ticket": pied_ticket,
        "qrcode": None,
        "footer": footer_lines,
    }
```

- [ ] **Step 4: Lancer les tests du formatter**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py::TestFormatterTicketVente -v
```

Attendu : les 5 tests du formatter passent.

---

## Task 3 : Modifier escpos_builder.py pour les nouvelles sections

**Files:**
- Modify: `laboutik/printing/escpos_builder.py:29-169`

- [ ] **Step 1: Ajouter le rendu des mentions légales et de la ventilation TVA**

Dans `laboutik/printing/escpos_builder.py`, modifier `build_escpos_from_ticket_data()`.

Après le rendu du header (ligne ~88, après `builder.appendText("---...`), ajouter le rendu de la section `legal`.

Après le rendu du total (ligne ~139), ajouter le rendu de `tva_breakdown`.

Après le footer existant, ajouter la mention DUPLICATA si `is_duplicata`.

Voici la fonction complète à remplacer :

```python
def build_escpos_from_ticket_data(dots_per_line, ticket_data):
    """
    Construit les donnees ESC/POS a partir d'un dict ticket_data.
    Retourne les octets binaires prets a etre envoyes a l'imprimante.
    / Builds ESC/POS data from a ticket_data dict.
    Returns raw binary bytes ready to send to the printer.

    LOCALISATION : laboutik/printing/escpos_builder.py

    Le SunmiCloudPrinter est utilise ici comme un builder ESC/POS pur.
    Il n'envoie rien — on recupere juste les octets via .orderData.
    L'envoi est gere par le backend (Cloud, LAN, Inner).
    / SunmiCloudPrinter is used here as a pure ESC/POS builder.
    It doesn't send anything — we just get the bytes via .orderData.
    Sending is handled by the backend (Cloud, LAN, Inner).

    :param dots_per_line: Nombre de dots par ligne (576, 384, 240)
    :param ticket_data: dict avec header, articles, total, qrcode, footer
    :return: bytes ESC/POS
    """
    builder = SunmiCloudPrinter(
        dots_per_line=dots_per_line,
        app_id="builder_only",
        app_key="builder_only",
        printer_sn="builder_only",
    )

    builder.setUtf8Mode(1)
    builder.restoreDefaultSettings()

    # --- En-tete du ticket ---
    # / Ticket header
    header = ticket_data.get("header", {})
    title = header.get("title", "")
    subtitle = header.get("subtitle", "")
    date_text = header.get("date", "")

    if title:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=False)
        builder.appendText(title + "\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)

    if subtitle:
        builder.setAlignment(ALIGN_CENTER)
        builder.appendText(subtitle + "\n")

    if date_text:
        builder.setAlignment(ALIGN_CENTER)
        builder.appendText(date_text + "\n")

    # --- Mentions legales (raison sociale, SIRET, TVA) ---
    # / Legal mentions (business name, SIRET, VAT)
    legal = ticket_data.get("legal")
    if legal:
        builder.setAlignment(ALIGN_CENTER)
        business_name = legal.get("business_name", "")
        if business_name:
            builder.setPrintModes(bold=True, double_h=False, double_w=False)
            builder.appendText(business_name + "\n")
            builder.setPrintModes(bold=False, double_h=False, double_w=False)

        address = legal.get("address", "")
        if address:
            builder.appendText(address + "\n")

        siret = legal.get("siret", "")
        if siret:
            builder.appendText(f"SIRET: {siret}\n")

        tva_number = legal.get("tva_number", "")
        if tva_number:
            builder.appendText(f"TVA: {tva_number}\n")

        receipt_number = legal.get("receipt_number", "")
        if receipt_number:
            builder.appendText(f"Ticket: {receipt_number}\n")

    if title or subtitle or date_text or legal:
        builder.appendText("--------------------------------\n")

    # --- Mention DUPLICATA (en haut, bien visible) ---
    # / DUPLICATE mention (at the top, clearly visible)
    is_duplicata = ticket_data.get("is_duplicata", False)
    if is_duplicata:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=True)
        builder.appendText("*** DUPLICATA ***\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)
        builder.appendText("--------------------------------\n")

    # --- Articles ---
    # / Articles
    articles = ticket_data.get("articles", [])
    if articles:
        builder.setAlignment(ALIGN_LEFT)
        for article in articles:
            article_name = article.get("name", "")
            article_qty = article.get("qty", 1)
            article_price = article.get("price", 0)
            article_total = article.get("total", 0)

            article_a_un_prix = (article_price is not None and article_price > 0)

            if article_a_un_prix:
                total_euros = f"{article_total / 100:.2f}"
                line = f"{article_name} x{article_qty}  {total_euros}EUR\n"
            else:
                line = f"{article_qty} x {article_name}\n"

            builder.appendText(line)

        builder.appendText("--------------------------------\n")

    # --- Total ---
    # / Total
    total_data = ticket_data.get("total", {})
    total_amount = total_data.get("amount", 0)
    total_label = total_data.get("label", "")

    total_est_present = "amount" in total_data and total_amount is not None
    if total_est_present:
        builder.setAlignment(ALIGN_LEFT)
        builder.setPrintModes(bold=True, double_h=False, double_w=False)
        total_euros = f"{total_amount / 100:.2f}"
        builder.appendText(f"TOTAL: {total_euros} EUR\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)

    if total_label:
        builder.appendText(f"{total_label}\n")

    # --- Ventilation TVA par taux ---
    # / VAT breakdown by rate
    tva_breakdown = ticket_data.get("tva_breakdown", [])
    if tva_breakdown:
        builder.appendText("--------------------------------\n")
        builder.setAlignment(ALIGN_LEFT)

        # En-tete du tableau TVA
        # / VAT table header
        builder.appendText("TVA%     HT       TVA      TTC\n")

        for tva_ligne in tva_breakdown:
            taux = tva_ligne.get("rate", "0.00")
            ht = tva_ligne.get("ht", 0)
            tva_montant = tva_ligne.get("tva", 0)
            ttc = tva_ligne.get("ttc", 0)

            ht_euros = f"{ht / 100:.2f}"
            tva_euros = f"{tva_montant / 100:.2f}"
            ttc_euros = f"{ttc / 100:.2f}"

            builder.appendText(
                f"{taux:>5}% {ht_euros:>7} {tva_euros:>7} {ttc_euros:>7}\n"
            )

        # Totaux HT et TVA globaux
        # / Global HT and VAT totals
        total_ht = ticket_data.get("total_ht", 0)
        total_tva = ticket_data.get("total_tva", 0)

        if total_ht or total_tva:
            builder.appendText("--------------------------------\n")
            builder.appendText(f"Total HT:  {total_ht / 100:.2f} EUR\n")
            builder.appendText(f"Total TVA: {total_tva / 100:.2f} EUR\n")

    # --- QR code ---
    qrcode_text = ticket_data.get("qrcode")
    if qrcode_text:
        builder.lineFeed(1)
        builder.setAlignment(ALIGN_CENTER)
        builder.appendQRcode(module_size=8, ec_level=2, text=qrcode_text)
        builder.lineFeed(1)

    # --- Pied de page ---
    # / Footer
    footer_lines = ticket_data.get("footer", [])
    if footer_lines:
        builder.setAlignment(ALIGN_CENTER)
        for footer_line in footer_lines:
            builder.appendText(footer_line + "\n")

    # --- Avance papier et coupe ---
    # / Paper feed and cut
    builder.lineFeed(3)
    builder.cutPaper(full_cut=False)

    return builder.orderData
```

- [ ] **Step 2: Vérifier que les tests existants passent toujours**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
```

Attendu : 7 tests passent.

---

## Task 4 : Traçabilité des impressions dans imprimer_async

**Files:**
- Modify: `laboutik/printing/tasks.py:32-88`
- Modify: `laboutik/views.py:3226-3311` (imprimer_ticket)

- [ ] **Step 1: Modifier imprimer_async pour créer un ImpressionLog**

Dans `laboutik/printing/tasks.py`, modifier `imprimer_async()` pour créer un `ImpressionLog` avant chaque impression.

Le `ticket_data` peut contenir un dict optionnel `"impression_meta"` avec les infos nécessaires :
```python
"impression_meta": {
    "uuid_transaction": str or None,
    "cloture_uuid": str or None,
    "type_justificatif": str,  # 'VENTE', 'CLOTURE', 'COMMANDE', 'BILLET'
    "operateur_pk": str or None,
    "format_emission": 'P' or 'E',
}
```

Modifier `imprimer_async()` :

```python
@shared_task(bind=True, max_retries=10)
def imprimer_async(self, printer_pk, ticket_data, schema_name):
    """
    Imprime un ticket de maniere asynchrone via Celery.
    Cree un ImpressionLog pour la tracabilite (LNE exigence 9).
    Retry exponentiel en cas d'echec recoverable (imprimante injoignable).
    Abandon immediat si l'imprimante n'existe plus en DB (erreur permanente).
    / Prints a ticket asynchronously via Celery.
    Creates an ImpressionLog for tracking (LNE requirement 9).
    Exponential retry on recoverable failure (printer unreachable).
    Immediate abort if printer no longer exists in DB (permanent error).

    LOCALISATION : laboutik/printing/tasks.py

    :param printer_pk: UUID (str) de l'imprimante
    :param ticket_data: dict avec header, articles, total, qrcode, footer + impression_meta optionnel
    :param schema_name: nom du schema tenant (pour schema_context)
    """
    try:
        with schema_context(schema_name):
            from laboutik.models import Printer, ImpressionLog
            from laboutik.printing import imprimer

            try:
                printer = Printer.objects.get(pk=printer_pk)
            except (ObjectDoesNotExist, ValueError):
                logger.error(
                    f"[PRINT TASK] Imprimante {printer_pk} introuvable — "
                    f"abandon (pas de retry)"
                )
                return

            # --- Tracabilite : creer ImpressionLog (LNE exigence 9) ---
            # / Tracking: create ImpressionLog (LNE requirement 9)
            impression_meta = ticket_data.pop("impression_meta", None)
            if impression_meta:
                uuid_transaction = impression_meta.get("uuid_transaction")
                cloture_uuid = impression_meta.get("cloture_uuid")
                type_justificatif = impression_meta.get("type_justificatif", "VENTE")
                operateur_pk_str = impression_meta.get("operateur_pk")
                format_emission = impression_meta.get("format_emission", "P")

                # Detecter duplicata : une impression precedente existe-t-elle ?
                # / Detect duplicate: does a previous print exist?
                filtre_duplicata = {"type_justificatif": type_justificatif}
                if uuid_transaction:
                    filtre_duplicata["uuid_transaction"] = uuid_transaction
                elif cloture_uuid:
                    filtre_duplicata["cloture__uuid"] = cloture_uuid

                nb_precedentes = ImpressionLog.objects.filter(**filtre_duplicata).count()
                est_duplicata = nb_precedentes > 0

                # Injecter is_duplicata dans ticket_data pour le builder ESC/POS
                # / Inject is_duplicata into ticket_data for the ESC/POS builder
                ticket_data["is_duplicata"] = est_duplicata

                # Operateur (peut etre None si tache Celery sans user)
                # / Operator (may be None if Celery task without user)
                operateur = None
                if operateur_pk_str:
                    from AuthBillet.models import TibilletUser
                    try:
                        operateur = TibilletUser.objects.get(pk=operateur_pk_str)
                    except TibilletUser.DoesNotExist:
                        pass

                # Cloture (pour les tickets Z)
                # / Closure (for Z-tickets)
                cloture_obj = None
                if cloture_uuid:
                    from laboutik.models import ClotureCaisse
                    try:
                        cloture_obj = ClotureCaisse.objects.get(uuid=cloture_uuid)
                    except ClotureCaisse.DoesNotExist:
                        pass

                ImpressionLog.objects.create(
                    uuid_transaction=uuid_transaction,
                    cloture=cloture_obj,
                    operateur=operateur,
                    printer=printer,
                    type_justificatif=type_justificatif,
                    is_duplicata=est_duplicata,
                    format_emission=format_emission,
                )

                logger.info(
                    f"[PRINT TASK] ImpressionLog cree — "
                    f"type={type_justificatif} duplicata={est_duplicata}"
                )

            result = imprimer(printer, ticket_data)

            if not result["ok"]:
                error_message = result.get("error", "Erreur inconnue")
                logger.warning(
                    f"[PRINT TASK] Echec impression — "
                    f"printer={printer.name} erreur={error_message} "
                    f"retry={self.request.retries}/{self.max_retries}"
                )
                delai_retry = min(5 * (2 ** self.request.retries), 300)
                raise self.retry(
                    exc=Exception(error_message),
                    countdown=delai_retry,
                )

            logger.info(
                f"[PRINT TASK] OK — printer={printer.name}"
            )

    except self.MaxRetriesExceededError:
        logger.error(
            f"[PRINT TASK] Abandon apres {self.max_retries} retries — "
            f"printer_pk={printer_pk}"
        )
```

- [ ] **Step 2: Modifier imprimer_ticket() dans views.py pour passer impression_meta**

Dans `laboutik/views.py`, dans la méthode `imprimer_ticket()` (ligne ~3301), remplacer l'appel `imprimer_async.delay(...)` pour inclure `impression_meta` dans le `ticket_data` :

Après la ligne `ticket_data = formatter_ticket_vente(...)` et avant `imprimer_async.delay(...)`, ajouter :

```python
        # Ajouter les metadonnees d'impression pour la tracabilite (LNE exigence 9)
        # / Add print metadata for tracking (LNE requirement 9)
        ticket_data["impression_meta"] = {
            "uuid_transaction": uuid_transaction_str,
            "cloture_uuid": None,
            "type_justificatif": "VENTE",
            "operateur_pk": str(operateur.pk) if operateur else None,
            "format_emission": "P",
        }
```

- [ ] **Step 3: Lancer tous les tests de la session**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
```

Attendu : 7 tests passent.

---

## Task 5 : Admin — pied_ticket dans LaboutikConfigurationAdmin + ImpressionLogAdmin

**Files:**
- Modify: `Administration/admin/laboutik.py`

- [ ] **Step 1: Ajouter pied_ticket et compteur_tickets dans les fieldsets**

Dans `Administration/admin/laboutik.py`, dans `LaboutikConfigurationAdmin.fieldsets`, ajouter une nouvelle section :

```python
    fieldsets = (
        (_('Interface caisse / POS interface'), {
            'fields': (
                'taille_police_articles',
            ),
        }),
        (_('Sunmi Cloud'), {
            'fields': (
                'sunmi_app_id',
                'sunmi_app_key',
            ),
            'description': _(
                "Identifiants Sunmi Cloud (stockes chiffres). "
                "/ Sunmi Cloud credentials (stored encrypted)."
            ),
        }),
        (_('Ticket de vente / Sale receipt'), {
            'fields': (
                'pied_ticket',
                'compteur_tickets',
            ),
            'description': _(
                "Personnalisation des tickets de vente. "
                "/ Sale receipt customization."
            ),
        }),
    )
```

- [ ] **Step 2: Ajouter ImpressionLogAdmin**

Dans `Administration/admin/laboutik.py`, ajouter l'import de `ImpressionLog` et l'admin :

Ajouter `ImpressionLog` dans l'import depuis `laboutik.models`.

Puis ajouter :

```python
@admin.register(ImpressionLog, site=staff_admin_site)
class ImpressionLogAdmin(ModelAdmin):
    """Admin lecture seule pour la tracabilite des impressions.
    Read-only admin for print tracking.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = (
        'datetime', 'type_justificatif', 'is_duplicata',
        'uuid_transaction', 'printer', 'operateur', 'format_emission',
    )
    list_filter = ('type_justificatif', 'is_duplicata', 'format_emission')
    search_fields = ('uuid_transaction',)
    ordering = ('-datetime',)
    readonly_fields = (
        'uuid', 'datetime', 'ligne_article', 'uuid_transaction',
        'cloture', 'operateur', 'printer', 'type_justificatif',
        'is_duplicata', 'format_emission',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

- [ ] **Step 3: Vérifier django check**

```bash
docker exec lespass_django poetry run python manage.py check
```

Attendu : 0 issues.

---

## Task 6 : Tests de régression

**Files:**
- Test: `tests/pytest/test_mentions_legales.py` (déjà créé en Task 2)
- Test: `tests/pytest/` (tous les tests existants)

- [ ] **Step 1: Lancer les 7+ tests de la session 14**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
```

Attendu : 7 tests passent.

- [ ] **Step 2: Lancer tous les tests pytest laboutik**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik or cloture or mentions" 2>&1 | tail -20
```

Attendu : 0 régression.

- [ ] **Step 3: Lancer tous les tests pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : 283+ tests passent (283 existants + 7 nouveaux = 290+), 0 échec.

---

## Critères de succès (checklist finale)

- [ ] Modèle ImpressionLog créé avec migration
- [ ] compteur_tickets sur LaboutikConfiguration
- [ ] Ticket de vente avec mentions légales complètes (raison sociale, adresse, SIRET, TVA)
- [ ] Ventilation TVA par taux sur le ticket
- [ ] Numéro séquentiel de ticket (T-000001, T-000002, ...)
- [ ] Mention "DUPLICATA" sur réimpressions (gras, encadré, double hauteur+largeur)
- [ ] ImpressionLog créé à chaque impression via imprimer_async
- [ ] Champ pied_ticket dans l'admin LaboutikConfiguration
- [ ] ImpressionLogAdmin lecture seule
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent (0 régression)
