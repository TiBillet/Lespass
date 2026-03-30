# Session 12 — Fondation HMAC + Service de calcul — Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser les fondations de la conformite LNE : chainage HMAC-SHA256 sur chaque LigneArticle + service de calcul des rapports comptables (12 methodes).

**Architecture:** Chaque LigneArticle recoit un HMAC-SHA256 chaine avec la precedente (cle secrete Fernet par tenant dans LaboutikConfiguration). Un service `RapportComptableService` centralise tous les calculs de rapports. La verification d'integrite croise avec les CorrectionPaiement pour distinguer corrections tracees de falsifications.

**Tech Stack:** Django 4.2, django-tenants, DRF serializers, HMAC-SHA256, Fernet (cryptography), pytest

**Conventions:** Code FALC (commentaires bilingues FR/EN), ViewSet explicit, pas de ModelViewSet, pas de Django Forms. Voir skill `djc` pour les patterns. **Ne jamais faire d'operation git.**

**Fichiers de reference a lire avant de commencer :**
- `GUIDELINES.md` et `CLAUDE.md` (regles du projet)
- `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md` (design spec)
- `tests/TESTS_README.md` (conventions tests)

---

## File Structure

| Action | Fichier | Responsabilite |
|--------|---------|---------------|
| Create | `laboutik/integrity.py` | Calcul HMAC, verification chaine, garde post-cloture |
| Create | `laboutik/reports.py` | RapportComptableService (12 methodes de calcul) |
| Create | `tests/pytest/test_integrity_hmac.py` | Tests chainage HMAC |
| Create | `tests/pytest/test_rapport_comptable.py` | Tests service de calcul |
| Create | `laboutik/management/commands/verify_integrity.py` | Management command verification |
| Modify | `BaseBillet/models.py:2887-2966` | +3 champs sur LigneArticle (hmac_hash, previous_hmac, total_ht) |
| Modify | `laboutik/models.py:23-109` | +5 champs sur LaboutikConfiguration (hmac_key, fond_de_caisse, etc.) |
| Modify | `laboutik/views.py:1442-1508` | Integration HMAC dans _creer_lignes_articles() |

---

### Task 1: Cle HMAC sur LaboutikConfiguration

**Files:**
- Modify: `laboutik/models.py:23-109`
- Test: `tests/pytest/test_integrity_hmac.py`

- [ ] **Step 1: Ecrire le test de generation de cle**

```python
# tests/pytest/test_integrity_hmac.py
"""
Tests du chainage HMAC-SHA256 pour la conformite LNE (exigence 8).
/ HMAC-SHA256 chaining tests for LNE compliance (requirement 8).

LOCALISATION : tests/pytest/test_integrity_hmac.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from django_tenants.utils import tenant_context
from Customers.models import Client


TENANT_SCHEMA = 'lespass'


def _get_tenant():
    """Recupere le tenant de test. / Gets the test tenant."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestCleHMAC:
    """Tests de la cle HMAC par tenant. / HMAC key per tenant tests."""

    @pytest.mark.django_db
    def test_cle_generee_automatiquement(self):
        """
        get_or_create_hmac_key() genere une cle de 64 caracteres hex au premier appel.
        / Generates a 64-char hex key on first call.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.models import LaboutikConfiguration
            config = LaboutikConfiguration.get_solo()
            # Reinitialiser la cle pour le test
            # / Reset key for test
            config.hmac_key = None
            config.save(update_fields=['hmac_key'])

            cle = config.get_or_create_hmac_key()

            assert cle is not None
            assert len(cle) == 64  # 32 bytes en hex = 64 chars

    @pytest.mark.django_db
    def test_cle_stable_entre_appels(self):
        """
        Deux appels a get_or_create_hmac_key() retournent la meme cle.
        / Two calls return the same key.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.models import LaboutikConfiguration
            config = LaboutikConfiguration.get_solo()
            config.hmac_key = None
            config.save(update_fields=['hmac_key'])

            cle_1 = config.get_or_create_hmac_key()
            cle_2 = config.get_or_create_hmac_key()

            assert cle_1 == cle_2
```

- [ ] **Step 2: Lancer le test pour verifier qu'il echoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py::TestCleHMAC -v
```
Attendu : FAIL (champs/methodes n'existent pas encore)

- [ ] **Step 3: Ajouter les champs sur LaboutikConfiguration**

Dans `laboutik/models.py`, apres le champ `sunmi_app_key` (ligne 72) et avant `def get_sunmi_app_id` (ligne 74), ajouter :

```python
    # --- Cle HMAC pour le chainage d'integrite (conformite LNE exigence 8) ---
    # La cle est chiffree avec Fernet. L'utilisateur final n'y a jamais acces.
    # / HMAC key for integrity chaining (LNE compliance req. 8)
    # Key is Fernet-encrypted. End user never has access.
    hmac_key = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name=_("HMAC key (encrypted)"),
        help_text=_(
            "Cle HMAC pour le chainage d'integrite des donnees d'encaissement. "
            "Generee automatiquement, stockee chiffree Fernet. "
            "/ HMAC key for POS data integrity chaining. "
            "Auto-generated, Fernet-encrypted."
        ),
    )

    # --- Configuration rapports comptables ---
    # / Accounting reports configuration
    fond_de_caisse = models.IntegerField(
        default=0,
        verbose_name=_("Cash float (cents)"),
        help_text=_(
            "Montant initial du tiroir-caisse en centimes. "
            "/ Initial cash drawer amount in cents."
        ),
    )
    rapport_emails = models.JSONField(
        default=list, blank=True,
        verbose_name=_("Report email recipients"),
        help_text=_(
            "Liste d'adresses email pour l'envoi automatique des rapports. "
            "/ List of email addresses for automatic report sending."
        ),
    )
    PERIODICITE_CHOICES = [
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('yearly', _('Yearly')),
    ]
    rapport_periodicite = models.CharField(
        max_length=10, choices=PERIODICITE_CHOICES, default='daily',
        verbose_name=_("Report frequency"),
        help_text=_(
            "Frequence d'envoi automatique des rapports comptables. "
            "/ Automatic accounting report sending frequency."
        ),
    )
    pied_ticket = models.TextField(
        blank=True, default='',
        verbose_name=_("Receipt footer text"),
        help_text=_(
            "Texte libre imprime en bas de chaque ticket de vente. "
            "/ Custom text printed at the bottom of every receipt."
        ),
    )

    # --- Total perpetuel (conformite LNE exigence 7) ---
    # Cumul depuis la mise en service. JAMAIS remis a 0.
    # / Cumulative total since first use. NEVER reset to 0.
    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Perpetual total (cents)"),
        help_text=_(
            "Total cumule de toutes les clotures depuis la mise en service. "
            "Ne doit jamais etre remis a zero. "
            "/ Cumulative total of all closures since first use. "
            "Must never be reset to zero."
        ),
    )
```

Puis ajouter les methodes getter/setter/create apres `set_sunmi_app_key()` (ligne 102) :

```python
    def get_hmac_key(self):
        """Dechiffre et retourne la cle HMAC, ou None si vide.
        / Decrypts and returns the HMAC key, or None if empty."""
        if not self.hmac_key:
            return None
        from root_billet.utils import fernet_decrypt
        return fernet_decrypt(self.hmac_key)

    def set_hmac_key(self, value):
        """Chiffre et stocke la cle HMAC.
        / Encrypts and stores the HMAC key."""
        if not value:
            self.hmac_key = None
        else:
            from root_billet.utils import fernet_encrypt
            self.hmac_key = fernet_encrypt(value)

    def get_or_create_hmac_key(self):
        """
        Retourne la cle HMAC. La genere si elle n'existe pas encore.
        Cle de 256 bits (32 octets) en hexadecimal.
        / Returns HMAC key. Generates it if not yet created.
        256-bit key (32 bytes) in hexadecimal.
        """
        cle_existante = self.get_hmac_key()
        if cle_existante:
            return cle_existante

        import secrets
        nouvelle_cle = secrets.token_hex(32)
        self.set_hmac_key(nouvelle_cle)
        self.save(update_fields=['hmac_key'])
        return nouvelle_cle
```

**IMPORTANT** : Changer l'import Fernet de `fedow_connect.utils` a `root_billet.utils` (ligne ~4 du fichier, si present) pour eviter une dependance fragile.

- [ ] **Step 4: Creer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name add_hmac_and_report_config
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 5: Lancer le test pour verifier qu'il passe**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py::TestCleHMAC -v
```
Attendu : 2 PASSED

---

### Task 2: Champs HMAC + total_ht sur LigneArticle

**Files:**
- Modify: `BaseBillet/models.py:2887-2966`
- Test: `tests/pytest/test_integrity_hmac.py`

- [ ] **Step 1: Ecrire le test total_ht**

Ajouter dans `tests/pytest/test_integrity_hmac.py` :

```python
class TestTotalHT:
    """Tests du calcul HT (donnee elementaire LNE exigence 3).
    / HT calculation tests (LNE requirement 3 elementary data)."""

    @pytest.mark.django_db
    def test_total_ht_tva_20(self):
        """
        TVA 20% sur 1200 centimes TTC → HT = 1000, TVA = 200.
        / 20% VAT on 1200 cents TTC → HT = 1000, VAT = 200.
        """
        amount_ttc = 1200
        taux_tva = 20.0
        total_ht_attendu = int(round(amount_ttc / (1 + taux_tva / 100)))
        total_tva_attendu = amount_ttc - total_ht_attendu

        assert total_ht_attendu == 1000
        assert total_tva_attendu == 200

    @pytest.mark.django_db
    def test_total_ht_tva_zero(self):
        """
        TVA 0% → HT = TTC, TVA = 0.
        / 0% VAT → HT = TTC, VAT = 0.
        """
        amount_ttc = 500
        taux_tva = 0.0

        if taux_tva > 0:
            total_ht = int(round(amount_ttc / (1 + taux_tva / 100)))
        else:
            total_ht = amount_ttc

        total_tva = amount_ttc - total_ht

        assert total_ht == 500
        assert total_tva == 0

    @pytest.mark.django_db
    def test_total_ht_tva_5_5(self):
        """
        TVA 5.5% sur 528 centimes TTC → HT = 500, TVA = 28.
        / 5.5% VAT on 528 cents TTC → HT = 500, VAT = 28.
        """
        amount_ttc = 528
        taux_tva = 5.5
        total_ht = int(round(amount_ttc / (1 + taux_tva / 100)))
        total_tva = amount_ttc - total_ht

        assert total_ht == 500
        assert total_tva == 28
```

- [ ] **Step 2: Lancer les tests HT (doivent passer — calcul pur)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py::TestTotalHT -v
```
Attendu : 3 PASSED (ce sont des tests de calcul pur, pas de DB)

- [ ] **Step 3: Ajouter les 3 champs sur LigneArticle**

Dans `BaseBillet/models.py`, apres le champ `credit_note_for` (vers la fin de la classe LigneArticle), ajouter :

```python
    # --- Chainage HMAC-SHA256 (conformite LNE exigence 8) ---
    # Chaque ligne est chainee avec la precedente via HMAC.
    # La cle secrete est par tenant (LaboutikConfiguration.hmac_key).
    # / HMAC-SHA256 chaining (LNE compliance requirement 8).
    # Each line is chained with the previous one via HMAC.
    # Secret key is per tenant (LaboutikConfiguration.hmac_key).
    hmac_hash = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name=_("HMAC hash"),
        help_text=_(
            "HMAC-SHA256 de cette ligne, chainee avec la precedente. "
            "/ HMAC-SHA256 of this line, chained with the previous one."
        ),
    )
    previous_hmac = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name=_("Previous HMAC"),
        help_text=_(
            "HMAC de la LigneArticle precedente dans la chaine. "
            "/ HMAC of the previous LigneArticle in the chain."
        ),
    )

    # --- Donnee elementaire HT (conformite LNE exigence 3) ---
    # Le referentiel LNE exige le total HT comme donnee elementaire,
    # pas seulement comme valeur calculee.
    # / LNE requirement 3: HT must be stored as elementary data,
    # not just computed.
    total_ht = models.IntegerField(
        default=0,
        verbose_name=_("Total HT (cents)"),
        help_text=_(
            "Total hors taxes en centimes. "
            "Calcule : TTC / (1 + taux_tva/100). "
            "/ Total excluding tax in cents. "
            "Computed: TTC / (1 + vat_rate/100)."
        ),
    )
```

- [ ] **Step 4: Creer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name add_hmac_and_total_ht_on_lignearticle
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 5: Verifier que manage.py check est propre**

```bash
docker exec lespass_django poetry run python manage.py check
```
Attendu : System check identified no issues.

---

### Task 3: Module integrity.py

**Files:**
- Create: `laboutik/integrity.py`
- Test: `tests/pytest/test_integrity_hmac.py`

- [ ] **Step 1: Ecrire les tests du chainage HMAC**

Ajouter dans `tests/pytest/test_integrity_hmac.py` :

```python
from decimal import Decimal


def _creer_ligne_article_test(tenant, amount=1200, vat=Decimal('20.00'),
                               payment_method='CASH', sale_origin='LABOUTIK'):
    """
    Cree une LigneArticle de test avec les champs minimaux.
    / Creates a test LigneArticle with minimal fields.
    """
    with tenant_context(tenant):
        from BaseBillet.models import LigneArticle, Product, Price, PriceSold, ProductSold

        # Recuperer un produit et prix existants (crees par create_test_pos_data)
        # / Get existing product and price (created by create_test_pos_data)
        product = Product.objects.filter(
            categorie_pos__isnull=False
        ).first()
        if not product:
            pytest.skip("Pas de produit POS disponible (lancer create_test_pos_data)")

        price = Price.objects.filter(product=product).first()
        if not price:
            pytest.skip("Pas de prix disponible")

        product_sold, _ = ProductSold.objects.get_or_create(
            product=product,
            defaults={'product_name': product.name},
        )
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            prix=price.prix,
            defaults={'price_name': str(price)},
        )

        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=amount,
            vat=vat,
            payment_method=payment_method,
            sale_origin=sale_origin,
            status=LigneArticle.VALID,
        )
        return ligne


class TestChainageHMAC:
    """Tests du chainage HMAC-SHA256. / HMAC-SHA256 chaining tests."""

    @pytest.mark.django_db
    def test_hmac_calcule_non_vide(self):
        """
        calculer_hmac() retourne une chaine de 64 caracteres hex.
        / Returns a 64-char hex string.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac
            ligne = _creer_ligne_article_test(tenant)
            hmac_resultat = calculer_hmac(ligne, 'cle_secrete_test', '')

            assert len(hmac_resultat) == 64
            assert all(c in '0123456789abcdef' for c in hmac_resultat)

    @pytest.mark.django_db
    def test_hmac_chaine_3_lignes(self):
        """
        3 lignes chainees → verifier_chaine retourne True.
        / 3 chained lines → verifier_chaine returns True.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac, verifier_chaine
            from laboutik.models import LaboutikConfiguration

            config = LaboutikConfiguration.get_solo()
            cle = config.get_or_create_hmac_key()

            previous = ''
            for i in range(3):
                ligne = _creer_ligne_article_test(tenant, amount=1000 + i * 100)
                # Calculer HT
                if float(ligne.vat) > 0:
                    ligne.total_ht = int(round(ligne.amount / (1 + float(ligne.vat) / 100)))
                else:
                    ligne.total_ht = ligne.amount
                ligne.previous_hmac = previous
                ligne.hmac_hash = calculer_hmac(ligne, cle, previous)
                ligne.save(update_fields=['total_ht', 'hmac_hash', 'previous_hmac'])
                previous = ligne.hmac_hash

            from BaseBillet.models import LigneArticle
            lignes_chainees = LigneArticle.objects.filter(
                hmac_hash__gt='',
                sale_origin='LABOUTIK',
            )
            est_valide, erreurs, corrections = verifier_chaine(lignes_chainees, cle)
            assert est_valide is True
            assert len(erreurs) == 0

    @pytest.mark.django_db
    def test_hmac_detecte_modification(self):
        """
        Modifier le amount d'une ligne → verifier_chaine retourne False.
        / Modifying amount breaks the chain → returns False.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac, verifier_chaine
            from laboutik.models import LaboutikConfiguration
            from BaseBillet.models import LigneArticle

            config = LaboutikConfiguration.get_solo()
            cle = config.get_or_create_hmac_key()

            # Creer 2 lignes chainees
            # / Create 2 chained lines
            previous = ''
            lignes = []
            for i in range(2):
                ligne = _creer_ligne_article_test(tenant, amount=1000)
                ligne.total_ht = int(round(ligne.amount / (1 + float(ligne.vat) / 100)))
                ligne.previous_hmac = previous
                ligne.hmac_hash = calculer_hmac(ligne, cle, previous)
                ligne.save(update_fields=['total_ht', 'hmac_hash', 'previous_hmac'])
                previous = ligne.hmac_hash
                lignes.append(ligne)

            # Falsifier la premiere ligne (modification directe en DB)
            # / Tamper with the first line (direct DB modification)
            lignes[0].amount = 9999
            lignes[0].save(update_fields=['amount'])

            lignes_chainees = LigneArticle.objects.filter(
                hmac_hash__gt='',
                sale_origin='LABOUTIK',
            )
            est_valide, erreurs, corrections = verifier_chaine(lignes_chainees, cle)
            assert est_valide is False
            assert len(erreurs) >= 1
```

- [ ] **Step 2: Lancer les tests pour verifier qu'ils echouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py::TestChainageHMAC -v
```
Attendu : FAIL (module laboutik.integrity n'existe pas)

- [ ] **Step 3: Creer laboutik/integrity.py**

```python
"""
Module d'integrite des donnees d'encaissement.
Chainage HMAC-SHA256 conforme a l'exigence 8 du referentiel LNE v1.7.
/ Data integrity module for POS transactions.
HMAC-SHA256 chaining per LNE certification standard v1.7, requirement 8.

LOCALISATION : laboutik/integrity.py

Algorithmes acceptables selon le referentiel LNE (page 37) :
- HMAC-SHA-256 (utilise ici)
- HMAC-SHA3
- RSA-SSA-PSS, ECDSA (surdimensionne pour notre cas)

Algorithmes NON acceptables :
- SHA-256 seul (sans cle), SHA-1, MD5, CRC16, CRC32

La cle HMAC est par tenant, chiffree Fernet dans LaboutikConfiguration.
L'utilisateur final (le lieu/association) n'a jamais acces a la cle.
/ The HMAC key is per tenant, Fernet-encrypted in LaboutikConfiguration.
The end user (venue/association) never has access to the key.
"""
import hmac
import hashlib
import json


def calculer_hmac(ligne, cle_secrete, previous_hmac=''):
    """
    Calcule le HMAC-SHA256 d'une LigneArticle chainee avec la precedente.
    Les champs hashes sont ceux qui impactent le rapport comptable.
    / Computes HMAC-SHA256 of a LigneArticle chained with the previous one.
    Hashed fields are those impacting the accounting report.

    LOCALISATION : laboutik/integrity.py

    :param ligne: LigneArticle instance
    :param cle_secrete: str — cle HMAC en clair (dechiffree depuis Fernet)
    :param previous_hmac: str — HMAC de la ligne precedente ('' si premiere)
    :return: str — empreinte HMAC-SHA256 de 64 caracteres hex
    """
    donnees = json.dumps([
        str(ligne.uuid),
        str(ligne.datetime.isoformat()) if ligne.datetime else '',
        ligne.amount,
        ligne.total_ht,
        float(ligne.qty),
        float(ligne.vat),
        ligne.payment_method or '',
        ligne.status or '',
        ligne.sale_origin or '',
        previous_hmac,
    ])
    return hmac.new(
        cle_secrete.encode('utf-8'),
        donnees.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def obtenir_previous_hmac(sale_origin='LABOUTIK'):
    """
    Retourne le hmac_hash de la derniere LigneArticle chainee.
    Les chaines sont separees par sale_origin (production vs test).
    / Returns the hmac_hash of the last chained LigneArticle.
    Chains are separated by sale_origin (production vs test).

    LOCALISATION : laboutik/integrity.py
    """
    from BaseBillet.models import LigneArticle
    derniere_hmac = LigneArticle.objects.filter(
        sale_origin=sale_origin,
        hmac_hash__gt='',
    ).order_by('-datetime', '-pk').values_list('hmac_hash', flat=True).first()
    return derniere_hmac or ''


def verifier_chaine(lignes_queryset, cle_secrete):
    """
    Verifie l'integrite de la chaine HMAC sur un queryset de LigneArticle.
    Croise avec CorrectionPaiement pour distinguer corrections tracees de falsifications.
    / Verifies HMAC chain integrity on a LigneArticle queryset.
    Cross-checks with CorrectionPaiement to distinguish traced corrections from tampering.

    LOCALISATION : laboutik/integrity.py

    :param lignes_queryset: QuerySet de LigneArticle (sera ordonne par datetime, pk)
    :param cle_secrete: str — cle HMAC en clair
    :return: tuple (est_valide: bool, erreurs: list, corrections_tracees: list)
    """
    erreurs = []
    corrections_tracees = []
    previous = ''

    for ligne in lignes_queryset.order_by('datetime', 'pk'):
        # Les lignes pre-migration n'ont pas de HMAC — on les ignore
        # / Pre-migration lines have no HMAC — skip them
        if not ligne.hmac_hash:
            continue

        attendu = calculer_hmac(ligne, cle_secrete, previous)

        if ligne.hmac_hash != attendu:
            # Verifier si c'est une correction tracee (CorrectionPaiement)
            # / Check if it's a traced correction (CorrectionPaiement)
            from laboutik.models import CorrectionPaiement
            correction = CorrectionPaiement.objects.filter(
                ligne_article=ligne,
            ).first()

            if correction:
                corrections_tracees.append({
                    'uuid': str(ligne.uuid),
                    'correction_uuid': str(correction.uuid),
                    'ancien_moyen': correction.ancien_moyen,
                    'nouveau_moyen': correction.nouveau_moyen,
                    'raison': correction.raison,
                })
            else:
                erreurs.append({
                    'uuid': str(ligne.uuid),
                    'datetime': str(ligne.datetime),
                    'attendu': attendu,
                    'trouve': ligne.hmac_hash,
                })

        previous = ligne.hmac_hash

    est_valide = len(erreurs) == 0
    return (est_valide, erreurs, corrections_tracees)


def calculer_total_ht(amount_ttc_centimes, taux_tva):
    """
    Calcule le total HT depuis le TTC et le taux de TVA.
    / Computes HT total from TTC and VAT rate.

    LOCALISATION : laboutik/integrity.py

    Formule LNE : HT = round(TTC / (1 + taux/100))
    TVA = TTC - HT

    :param amount_ttc_centimes: int — montant TTC en centimes
    :param taux_tva: Decimal ou float — taux TVA en % (ex: 20.0)
    :return: int — total HT en centimes
    """
    taux = float(taux_tva)
    if taux > 0:
        return int(round(amount_ttc_centimes / (1 + taux / 100)))
    return amount_ttc_centimes
```

**Note :** Le modele `CorrectionPaiement` n'existe pas encore (session 17). L'import est protege par un try/except ou simplement dans le corps de la fonction. Si le modele n'existe pas encore, `verifier_chaine` traitera toute rupture comme une erreur — c'est correct car sans modele CorrectionPaiement, il n'y a pas de correction possible.

- [ ] **Step 4: Lancer les tests pour verifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py -v
```
Attendu : 5+ PASSED (TestCleHMAC + TestTotalHT + TestChainageHMAC)

---

### Task 4: Integration HMAC dans _creer_lignes_articles()

**Files:**
- Modify: `laboutik/views.py:1442-1508`

- [ ] **Step 1: Modifier _creer_lignes_articles()**

Dans `laboutik/views.py`, ajouter les imports en haut du fichier :

```python
from laboutik.integrity import calculer_hmac, obtenir_previous_hmac, calculer_total_ht
```

Puis dans `_creer_lignes_articles()`, apres la boucle de creation des LigneArticle (apres le `LigneArticle.objects.create(...)`, vers ligne 1492), ajouter le chainage HMAC :

```python
    # --- Chainage HMAC (conformite LNE exigence 8) ---
    # Calcule le total HT et le HMAC pour chaque ligne creee.
    # Le HMAC est chaine avec la ligne precedente.
    # / HMAC chaining (LNE compliance req. 8).
    # Computes HT and HMAC for each created line.
    from laboutik.models import LaboutikConfiguration
    config_laboutik = LaboutikConfiguration.get_solo()
    cle_hmac = config_laboutik.get_or_create_hmac_key()
    previous_hmac_value = obtenir_previous_hmac(sale_origin=lignes_creees[0].sale_origin if lignes_creees else 'LABOUTIK')

    for ligne_a_chainer in lignes_creees:
        # Calculer le HT (donnee elementaire LNE exigence 3)
        # / Compute HT (LNE req. 3 elementary data)
        ligne_a_chainer.total_ht = calculer_total_ht(ligne_a_chainer.amount, ligne_a_chainer.vat)

        # Chainer le HMAC avec la ligne precedente
        # / Chain HMAC with previous line
        ligne_a_chainer.previous_hmac = previous_hmac_value
        ligne_a_chainer.hmac_hash = calculer_hmac(ligne_a_chainer, cle_hmac, previous_hmac_value)
        ligne_a_chainer.save(update_fields=['total_ht', 'hmac_hash', 'previous_hmac'])

        previous_hmac_value = ligne_a_chainer.hmac_hash
```

**ATTENTION** : `lignes_creees` est la liste retournee par la boucle de creation. Verifier le nom exact de la variable dans le code actuel (vers ligne 1492-1506).

- [ ] **Step 2: Lancer les tests existants POS pour verifier 0 regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_paiement_*.py tests/pytest/test_cloture_*.py -v
```
Attendu : tous PASSED (les nouveaux champs ont des defaults, pas de casse)

- [ ] **Step 3: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : 261+ PASSED, 0 FAILED

---

### Task 5: RapportComptableService

**Files:**
- Create: `laboutik/reports.py`
- Test: `tests/pytest/test_rapport_comptable.py`

- [ ] **Step 1: Ecrire les tests du service**

```python
# tests/pytest/test_rapport_comptable.py
"""
Tests du RapportComptableService.
/ RapportComptableService tests.

LOCALISATION : tests/pytest/test_rapport_comptable.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django_tenants.utils import tenant_context
from Customers.models import Client


TENANT_SCHEMA = 'lespass'


def _get_tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestRapportComptableService:
    """Tests du service de calcul des rapports. / Report calculation service tests."""

    @pytest.mark.django_db
    def test_rapport_complet_12_cles(self):
        """
        generer_rapport_complet() retourne un dict avec 12 cles.
        / Returns a dict with 12 keys.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.reports import RapportComptableService
            from laboutik.models import PointDeVente

            pv = PointDeVente.objects.first()
            if not pv:
                pytest.skip("Pas de PV disponible")

            debut = timezone.now() - timedelta(days=1)
            fin = timezone.now()

            service = RapportComptableService(pv, debut, fin)
            rapport = service.generer_rapport_complet()

            cles_attendues = [
                'totaux_par_moyen', 'detail_ventes', 'tva',
                'solde_caisse', 'recharges', 'adhesions',
                'remboursements', 'habitus', 'billets',
                'synthese_operations', 'operateurs', 'infos_legales',
            ]
            for cle in cles_attendues:
                assert cle in rapport, f"Cle manquante : {cle}"

    @pytest.mark.django_db
    def test_totaux_par_moyen(self):
        """
        calculer_totaux_par_moyen() retourne especes, cb, cashless, total.
        / Returns cash, card, cashless, total.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.reports import RapportComptableService
            from laboutik.models import PointDeVente

            pv = PointDeVente.objects.first()
            if not pv:
                pytest.skip("Pas de PV disponible")

            debut = timezone.now() - timedelta(days=30)
            fin = timezone.now()

            service = RapportComptableService(pv, debut, fin)
            totaux = service.calculer_totaux_par_moyen()

            assert 'especes' in totaux
            assert 'carte_bancaire' in totaux
            assert 'cashless' in totaux
            assert 'total' in totaux
            # Le total est la somme des parties
            # / Total is sum of parts
            assert totaux['total'] == (
                totaux['especes'] + totaux['carte_bancaire'] + totaux['cashless']
                + totaux.get('cheque', 0)
            )

    @pytest.mark.django_db
    def test_tva_calcul(self):
        """
        calculer_tva() retourne des dicts par taux avec total_ht, total_tva, total_ttc.
        / Returns dicts per rate with total_ht, total_tva, total_ttc.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.reports import RapportComptableService
            from laboutik.models import PointDeVente

            pv = PointDeVente.objects.first()
            if not pv:
                pytest.skip("Pas de PV disponible")

            debut = timezone.now() - timedelta(days=30)
            fin = timezone.now()

            service = RapportComptableService(pv, debut, fin)
            tva_result = service.calculer_tva()

            # Chaque entree doit avoir les 3 totaux
            # / Each entry must have all 3 totals
            for taux_label, data in tva_result.items():
                assert 'total_ht' in data
                assert 'total_tva' in data
                assert 'total_ttc' in data
                # HT + TVA = TTC
                assert data['total_ht'] + data['total_tva'] == data['total_ttc']
```

- [ ] **Step 2: Lancer les tests pour verifier qu'ils echouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v
```
Attendu : FAIL (module laboutik.reports n'existe pas)

- [ ] **Step 3: Creer laboutik/reports.py**

Le fichier est trop long pour etre inclus integralement ici. Voici la structure et les methodes a implementer. **Lire le code actuel de `cloturer()` (views.py:949-1064) pour la logique existante — le service la reprend et l'enrichit.**

```python
"""
Service de calcul des rapports comptables.
Utilise pour le Ticket X (live, pas de sauvegarde) et le Ticket Z (cloture).
/ Accounting report calculation service.
Used for Ticket X (live, no save) and Ticket Z (closure, persisted).

LOCALISATION : laboutik/reports.py

FLUX :
- Ticket X : appel depuis CaisseViewSet.recap_en_cours() → rendu HTML direct
- Ticket Z : appel depuis CaisseViewSet.cloturer() → resultat stocke dans ClotureCaisse.rapport_json

DEPENDENCIES :
- BaseBillet.models : LigneArticle, SaleOrigin, PaymentMethod
- laboutik.models : LaboutikConfiguration
- laboutik.integrity : calculer_total_ht
"""
import hashlib
import json

from django.db.models import Sum, Count, Q
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import LigneArticle, SaleOrigin, PaymentMethod


class RapportComptableService:
    """
    Service de calcul des rapports comptables.
    12 methodes de calcul + generer_rapport_complet().
    / Accounting report calculation service.
    12 calculation methods + generer_rapport_complet().

    LOCALISATION : laboutik/reports.py
    """

    def __init__(self, point_de_vente, datetime_debut, datetime_fin):
        """
        :param point_de_vente: PointDeVente instance
        :param datetime_debut: datetime — debut de la periode
        :param datetime_fin: datetime — fin de la periode
        """
        self.pv = point_de_vente
        self.debut = datetime_debut
        self.fin = datetime_fin

        # Queryset de base : toutes les lignes valides de la periode
        # / Base queryset: all valid lines in the period
        self.lignes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=self.debut,
            datetime__lte=self.fin,
            status=LigneArticle.VALID,
        ).select_related(
            'pricesold__productsold__product__categorie_pos',
            'carte',
        )

    def calculer_totaux_par_moyen(self):
        # Reprendre la logique de views.py:957-971
        # Agreger par PaymentMethod
        ...

    def calculer_detail_ventes(self):
        # Par article, groupe par categorie
        # qty vendus/offerts, CA HT/TTC/TVA
        ...

    def calculer_tva(self):
        # Par taux de TVA
        # HT = int(round(TTC / (1 + taux/100)))
        # Reprendre la logique de views.py:1020-1043
        ...

    def calculer_solde_caisse(self):
        # fond_de_caisse + entrees especes - sorties especes
        ...

    def calculer_recharges(self):
        # RE/RC/TM x moyen de paiement
        ...

    def calculer_adhesions(self):
        # Nombre creees/renouvelees, total par moyen
        ...

    def calculer_remboursements(self):
        # Vides carte, retours consigne, avoirs (CREDIT_NOTE)
        ...

    def calculer_habitus(self):
        # Cartes NFC distinctes, mediane recharge, panier moyen
        # SANS N+1 : values('carte').annotate(total=Sum('amount'))
        ...

    def calculer_billets(self):
        # Events de la periode, total billets, vendus caisse vs en ligne
        ...

    def calculer_synthese_operations(self):
        # Tableau croise type x moyen
        ...

    def calculer_operateurs(self):
        # Total par caissier (si champ existe)
        ...

    def _infos_legales(self):
        # SIRET, adresse, n° sequentiel depuis Configuration
        ...

    def generer_rapport_complet(self):
        """
        Calcule les 12 sections du rapport.
        Retourne un dict serialisable JSON.
        / Computes all 12 report sections.
        Returns a JSON-serializable dict.
        """
        return {
            'totaux_par_moyen': self.calculer_totaux_par_moyen(),
            'detail_ventes': self.calculer_detail_ventes(),
            'tva': self.calculer_tva(),
            'solde_caisse': self.calculer_solde_caisse(),
            'recharges': self.calculer_recharges(),
            'adhesions': self.calculer_adhesions(),
            'remboursements': self.calculer_remboursements(),
            'habitus': self.calculer_habitus(),
            'billets': self.calculer_billets(),
            'synthese_operations': self.calculer_synthese_operations(),
            'operateurs': self.calculer_operateurs(),
            'infos_legales': self._infos_legales(),
        }

    def calculer_hash_lignes(self):
        """
        SHA-256 des LigneArticle couvertes (filet de securite pour la cloture).
        / SHA-256 of covered LigneArticle (safety net for closure).
        """
        lignes_data = self.lignes.order_by('datetime', 'pk').values_list(
            'uuid', 'amount', 'qty', 'vat', 'payment_method', 'status',
        )
        donnees = json.dumps(
            [[str(v) for v in ligne] for ligne in lignes_data]
        )
        return hashlib.sha256(donnees.encode('utf-8')).hexdigest()
```

**IMPORTANT** : Chaque methode `calculer_*` doit etre implementee completement. La logique des 5 premieres (totaux, detail, tva, commandes, categories) se trouve deja dans `views.py:949-1064`. Les 7 autres sont nouvelles mais simples (aggregations Django).

- [ ] **Step 4: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v
```
Attendu : 3 PASSED

- [ ] **Step 5: Lancer TOUS les tests pour verifier 0 regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : 270+ PASSED (261 existants + ~9 nouveaux), 0 FAILED

---

### Task 6: Management command verify_integrity

**Files:**
- Create: `laboutik/management/commands/verify_integrity.py`

- [ ] **Step 1: Creer le dossier management si necessaire**

```bash
docker exec lespass_django ls /DjangoFiles/laboutik/management/commands/ 2>/dev/null || echo "A creer"
```

Si le dossier n'existe pas, creer `laboutik/management/__init__.py` et `laboutik/management/commands/__init__.py`.

- [ ] **Step 2: Creer la commande**

```python
"""
Management command pour verifier l'integrite de la chaine HMAC.
/ Management command to verify HMAC chain integrity.

LOCALISATION : laboutik/management/commands/verify_integrity.py

Usage :
    docker exec lespass_django poetry run python manage.py verify_integrity --schema=lespass
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from BaseBillet.models import LigneArticle


class Command(BaseCommand):
    help = 'Verifie la chaine HMAC des LigneArticle / Verifies HMAC chain integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, default=None,
            help='Schema du tenant a verifier (defaut: tenant courant)',
        )

    def handle(self, *args, **options):
        schema = options['schema'] or connection.schema_name

        if schema == 'public':
            from Customers.models import Client
            tenant = Client.objects.exclude(schema_name='public').first()
            if not tenant:
                self.stderr.write("Aucun tenant trouve.")
                return
            schema = tenant.schema_name

        with schema_context(schema):
            from laboutik.models import LaboutikConfiguration
            from laboutik.integrity import verifier_chaine

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()

            if not cle:
                self.stdout.write(self.style.WARNING(
                    f"[{schema}] Pas de cle HMAC configuree. Aucune verification possible."
                ))
                return

            lignes = LigneArticle.objects.filter(
                sale_origin='LABOUTIK',
            )
            total_lignes = lignes.count()
            lignes_avec_hmac = lignes.filter(hmac_hash__gt='').count()

            self.stdout.write(f"[{schema}] {total_lignes} lignes totales, {lignes_avec_hmac} avec HMAC")

            est_valide, erreurs, corrections = verifier_chaine(lignes, cle)

            if corrections:
                self.stdout.write(self.style.WARNING(
                    f"  {len(corrections)} correction(s) tracee(s) (HMAC casse volontairement)"
                ))
                for c in corrections:
                    self.stdout.write(f"    - {c['uuid']} : {c['ancien_moyen']} → {c['nouveau_moyen']}")

            if est_valide:
                self.stdout.write(self.style.SUCCESS(
                    f"  CHAINE INTEGRE — {lignes_avec_hmac} lignes verifiees, 0 erreur"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"  ALERTE — {len(erreurs)} erreur(s) d'integrite detectee(s) :"
                ))
                for e in erreurs:
                    self.stdout.write(f"    - {e['uuid']} ({e['datetime']})")
```

- [ ] **Step 3: Tester la commande**

```bash
docker exec lespass_django poetry run python manage.py verify_integrity --schema=lespass
```
Attendu : affiche le nombre de lignes et le resultat de verification

---

### Task 7: Verification finale

- [ ] **Step 1: manage.py check**

```bash
docker exec lespass_django poetry run python manage.py check
```
Attendu : System check identified no issues.

- [ ] **Step 2: Tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : 270+ PASSED, 0 FAILED

- [ ] **Step 3: Tests specifiques integrite + rapport**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py tests/pytest/test_rapport_comptable.py -v
```
Attendu : tous PASSED

- [ ] **Step 4: Verification commande verify_integrity**

```bash
docker exec lespass_django poetry run python manage.py verify_integrity --schema=lespass
```
Attendu : "CHAINE INTEGRE" ou "Pas de cle HMAC" (si aucune vente n'a ete faite avec le nouveau code)
