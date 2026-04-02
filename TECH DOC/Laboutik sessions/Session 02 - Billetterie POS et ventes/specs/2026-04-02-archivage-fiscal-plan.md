# Session 18 — Archivage fiscal : Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementer l'archivage fiscal (Ex.10-12, Ex.15, Ex.19) : 2 nouveaux modeles, 3 management commands, 1 bouton admin export fiscal, branchement historique fond de caisse.

**Architecture:** Nouveau module `laboutik/archivage.py` factorise la logique d'export (CSV + JSON + hash HMAC). 3 management commands et 1 vue admin l'appellent. 2 modeles d'audit immutables (`JournalOperation`, `HistoriqueFondDeCaisse`). Tests `FastTenantTestCase`.

**Tech Stack:** Django 4.2, django-tenants, DRF, pytest, WeasyPrint (PDF existant), HMAC-SHA256, zipfile, csv.

**Spec:** `TECH DOC/Laboutik sessions/Session 02 - Billetterie POS et ventes/specs/2026-04-02-archivage-fiscal-acces-administration-design.md`

---

## Fichiers

| Action | Fichier | Responsabilite |
|--------|---------|----------------|
| Modifier | `laboutik/models.py` | Ajouter `JournalOperation` + `HistoriqueFondDeCaisse` |
| Creer | `laboutik/migrations/0016_journaloperation_historiquefondecaisse.py` | Migration |
| Creer | `laboutik/archivage.py` | Logique d'export factorisee (CSV + JSON + hash) |
| Creer | `laboutik/management/commands/archiver_donnees.py` | Command archivage ZIP |
| Creer | `laboutik/management/commands/verifier_archive.py` | Command verification hash |
| Creer | `laboutik/management/commands/acces_fiscal.py` | Command export fiscal |
| Modifier | `laboutik/views.py` | Branchement `HistoriqueFondDeCaisse` dans `fond_de_caisse()` |
| Modifier | `Administration/admin/laboutik.py` | Admin read-only pour les 2 modeles + bouton export fiscal |
| Creer | `tests/pytest/test_archivage_fiscal.py` | 14 tests |

---

## Task 1 : Modeles `JournalOperation` + `HistoriqueFondDeCaisse`

**Files:**
- Modify: `laboutik/models.py` (ajouter apres `SortieCaisse`, ligne ~1362)
- Create: `laboutik/migrations/0016_journaloperation_historiquefondecaisse.py` (auto)

- [ ] **Step 1: Ajouter `JournalOperation` dans `laboutik/models.py`**

Ajouter apres la classe `SortieCaisse` (fin du fichier) :

```python
# --- Journal des operations d'archivage (tracabilite LNE Ex.15) ---
# Trace immutable de chaque operation technique : archivage, verification,
# export fiscal. Chaque entree est chainee HMAC avec la precedente.
# / Immutable audit trail for technical operations: archiving, verification,
# fiscal export. Each entry is HMAC-chained with the previous one.

class JournalOperation(models.Model):
    """
    Trace immutable d'une operation technique (archivage, verification, export).
    Chainee HMAC-SHA256 avec l'entree precedente (meme logique que LigneArticle).
    / Immutable trace of a technical operation (archiving, verification, export).
    HMAC-SHA256 chained with the previous entry.

    LOCALISATION : laboutik/models.py
    """
    ARCHIVAGE = 'ARCHIVAGE'
    VERIFICATION = 'VERIFICATION'
    EXPORT_FISCAL = 'EXPORT_FISCAL'
    TYPE_CHOICES = [
        (ARCHIVAGE, _('Archiving')),
        (VERIFICATION, _('Verification')),
        (EXPORT_FISCAL, _('Fiscal export')),
    ]

    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Type d'operation effectuee
    # / Type of operation performed
    type_operation = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name=_("Operation type"),
    )

    # Horodatage immutable
    # / Immutable timestamp
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date"),
    )

    # Operateur qui a lance l'operation (null si Celery Beat)
    # / Operator who launched the operation (null if Celery Beat)
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='operations_journal',
        verbose_name=_("Operator"),
    )

    # Metadonnees libres (periode, hash, nb fichiers, resultat...)
    # / Free-form metadata (period, hash, file count, result...)
    details = models.JSONField(
        default=dict,
        verbose_name=_("Details"),
    )

    # HMAC-SHA256 chaine avec l'entree precedente
    # / HMAC-SHA256 chained with the previous entry
    hmac_hash = models.CharField(
        max_length=64,
        blank=True, default='',
        verbose_name=_("HMAC hash"),
    )

    def __str__(self):
        return f"{self.get_type_operation_display()} — {self.datetime:%Y-%m-%d %H:%M}"

    class Meta:
        ordering = ['datetime']
        verbose_name = _('Operation log')
        verbose_name_plural = _('Operation logs')


# --- Historique fond de caisse ---
# Trace immutable de chaque modification du fond de caisse.
# / Immutable trace of each cash float change.

class HistoriqueFondDeCaisse(models.Model):
    """
    Trace immutable d'un changement de fond de caisse.
    Creee a chaque POST sur fond-de-caisse (PaiementViewSet).
    / Immutable trace of a cash float change.
    Created on each POST to fond-de-caisse (PaiementViewSet).

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Point de vente actif au moment du changement
    # / Active point of sale at the time of change
    point_de_vente = models.ForeignKey(
        'laboutik.PointDeVente', on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='historique_fond_de_caisse',
        verbose_name=_("Point of sale"),
    )

    # Operateur qui a modifie le fond
    # / Operator who changed the float
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='historique_fond_de_caisse',
        verbose_name=_("Operator"),
    )

    # Horodatage immutable
    # / Immutable timestamp
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date"),
    )

    # Montant avant modification (centimes)
    # / Amount before change (cents)
    ancien_montant = models.IntegerField(
        verbose_name=_("Previous amount (cents)"),
    )

    # Montant apres modification (centimes)
    # / Amount after change (cents)
    nouveau_montant = models.IntegerField(
        verbose_name=_("New amount (cents)"),
    )

    # Raison optionnelle
    # / Optional reason
    raison = models.TextField(
        blank=True, default='',
        verbose_name=_("Reason"),
    )

    def __str__(self):
        ancien = self.ancien_montant / 100
        nouveau = self.nouveau_montant / 100
        return f"{ancien:.2f} € → {nouveau:.2f} € ({self.datetime:%Y-%m-%d %H:%M})"

    class Meta:
        ordering = ['-datetime']
        verbose_name = _('Cash float history')
        verbose_name_plural = _('Cash float history')
```

- [ ] **Step 2: Generer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name journaloperation_historiquefondecaisse
```

Expected: migration `0016_journaloperation_historiquefondecaisse.py` creee.

- [ ] **Step 3: Appliquer la migration**

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

Expected: `Applying laboutik.0016_...OK` sur tous les schemas.

- [ ] **Step 4: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

Expected: `System check identified no issues.`

---

## Task 2 : Admin read-only pour les 2 modeles

**Files:**
- Modify: `Administration/admin/laboutik.py`

- [ ] **Step 1: Ajouter les imports**

Au debut du fichier `Administration/admin/laboutik.py`, ajouter aux imports existants de `laboutik.models` :

```python
from laboutik.models import (
    ...,  # imports existants
    JournalOperation,
    HistoriqueFondDeCaisse,
)
```

- [ ] **Step 2: Ajouter `JournalOperationAdmin`**

Apres `ImpressionLogAdmin` (fin du fichier), ajouter :

```python
@admin.register(JournalOperation, site=laboutik_admin_site)
class JournalOperationAdmin(ModelAdmin):
    """
    Journal des operations (archivage, verification, export fiscal).
    Lecture seule — aucune modification possible.
    / Operation log (archiving, verification, fiscal export).
    Read-only — no modification allowed.

    LOCALISATION : Administration/admin/laboutik.py
    """
    list_display = [
        'datetime', 'type_operation', 'operateur',
    ]
    list_filter = ['type_operation']
    readonly_fields = [
        'uuid', 'type_operation', 'datetime', 'operateur',
        'details', 'hmac_hash',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

- [ ] **Step 3: Ajouter `HistoriqueFondDeCaisseAdmin`**

Juste apres `JournalOperationAdmin` :

```python
# Helpers de formatage au niveau module (pas dans le ModelAdmin)
# Unfold intercepte les methodes du ModelAdmin via son systeme @action.
# / Module-level formatting helpers (not inside ModelAdmin).
# Unfold intercepts ModelAdmin methods via its @action system.

def _euros_ancien(obj):
    """Formate l'ancien montant en euros. / Formats previous amount in euros."""
    return f"{obj.ancien_montant / 100:.2f} €"
_euros_ancien.short_description = _("Previous amount")

def _euros_nouveau(obj):
    """Formate le nouveau montant en euros. / Formats new amount in euros."""
    return f"{obj.nouveau_montant / 100:.2f} €"
_euros_nouveau.short_description = _("New amount")


@admin.register(HistoriqueFondDeCaisse, site=laboutik_admin_site)
class HistoriqueFondDeCaisseAdmin(ModelAdmin):
    """
    Historique des changements de fond de caisse.
    Lecture seule — aucune modification possible.
    / Cash float change history.
    Read-only — no modification allowed.

    LOCALISATION : Administration/admin/laboutik.py
    """
    list_display = [
        'datetime', _euros_ancien, _euros_nouveau, 'operateur',
    ]
    readonly_fields = [
        'uuid', 'point_de_vente', 'operateur', 'datetime',
        'ancien_montant', 'nouveau_montant', 'raison',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

- [ ] **Step 4: Ajouter les entrees dans la sidebar**

Trouver la section sidebar "Caisse LaBoutik" dans `Administration/admin_tenant.py` (ou la ou la sidebar est definie). Ajouter les 2 modeles dans la section existante de laboutik :

```python
{
    "title": _("Journal operations"),
    "icon": "history",
    "link": reverse_lazy("admin:laboutik_journaloperation_changelist"),
},
{
    "title": _("Cash float history"),
    "icon": "account_balance_wallet",
    "link": reverse_lazy("admin:laboutik_historiquefondecaisse_changelist"),
},
```

- [ ] **Step 5: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

Expected: 0 issues.

---

## Task 3 : Branchement `HistoriqueFondDeCaisse` dans la vue `fond_de_caisse`

**Files:**
- Modify: `laboutik/views.py` (methode `fond_de_caisse`, ligne ~1323)

- [ ] **Step 1: Ajouter l'import**

En haut de `laboutik/views.py`, dans les imports de `laboutik.models`, ajouter `HistoriqueFondDeCaisse`.

- [ ] **Step 2: Creer l'historique avant de sauver le nouveau montant**

Dans la methode `fond_de_caisse()`, section POST (apres la validation du serializer, avant `config.fond_de_caisse = montant_centimes`), ajouter :

```python
            # Trace du changement de fond de caisse avant modification
            # / Record cash float change before modification
            from laboutik.models import HistoriqueFondDeCaisse
            HistoriqueFondDeCaisse.objects.create(
                ancien_montant=config.fond_de_caisse,
                nouveau_montant=montant_centimes,
                operateur=request.user if request.user.is_authenticated else None,
                point_de_vente=self._get_point_de_vente_from_request(request),
            )
```

Note : `self._get_point_de_vente_from_request(request)` — verifier si cette methode existe deja dans le ViewSet. Sinon, extraire le PV depuis `request.POST.get('uuid_pv')` ou `request.GET.get('uuid_pv')` directement :

```python
            # Recuperer le PV depuis les parametres (peut etre absent)
            # / Get PV from params (may be missing)
            uuid_pv = request.POST.get('uuid_pv') or request.GET.get('uuid_pv')
            point_de_vente_pour_historique = None
            if uuid_pv:
                from laboutik.models import PointDeVente
                point_de_vente_pour_historique = PointDeVente.objects.filter(uuid=uuid_pv).first()

            HistoriqueFondDeCaisse.objects.create(
                ancien_montant=config.fond_de_caisse,
                nouveau_montant=montant_centimes,
                operateur=request.user if request.user.is_authenticated else None,
                point_de_vente=point_de_vente_pour_historique,
            )
```

- [ ] **Step 3: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 4 : Module `laboutik/archivage.py` — logique d'export factorisee

**Files:**
- Create: `laboutik/archivage.py`

C'est le coeur de la session. Ce module est appele par les 3 commands et la vue admin.

- [ ] **Step 1: Creer `laboutik/archivage.py` avec les fonctions de base**

```python
"""
Module d'archivage fiscal pour la conformite LNE (Ex.10-12).
Genere des archives CSV + JSON avec hash HMAC-SHA256 verifiable.
/ Fiscal archiving module for LNE compliance (Ex.10-12).
Generates CSV + JSON archives with verifiable HMAC-SHA256 hashes.

LOCALISATION : laboutik/archivage.py

Ce module est appele par :
- laboutik/management/commands/archiver_donnees.py (ZIP)
- laboutik/management/commands/acces_fiscal.py (dossier)
- Administration/admin/laboutik.py (bouton export fiscal)
/ Called by: archiver_donnees (ZIP), acces_fiscal (folder), admin export button.
"""
import csv
import hashlib
import hmac
import io
import json
import zipfile
from datetime import date, datetime

from django.utils import timezone

from BaseBillet.models import (
    Configuration, LigneArticle, SaleOrigin,
)
from laboutik.models import (
    ClotureCaisse, CorrectionPaiement, HistoriqueFondDeCaisse,
    ImpressionLog, LaboutikConfiguration, SortieCaisse,
)


# --- Colonnes CSV par modele ---
# / CSV columns per model

COLONNES_LIGNES_ARTICLE = [
    'uuid', 'datetime', 'article', 'categorie', 'prix_ttc_centimes',
    'quantite', 'payment_method', 'sale_origin', 'taux_tva',
    'total_ht_centimes', 'total_tva_centimes', 'point_de_vente',
    'operateur_email', 'user_email', 'uuid_transaction', 'hmac_hash',
]

COLONNES_CLOTURES = [
    'uuid', 'datetime_cloture', 'datetime_ouverture', 'niveau',
    'numero_sequentiel', 'total_especes', 'total_carte_bancaire',
    'total_cashless', 'total_cheque', 'total_general',
    'nombre_transactions', 'total_perpetuel', 'hash_lignes',
    'responsable_email', 'point_de_vente',
]

COLONNES_CORRECTIONS = [
    'uuid', 'datetime', 'ligne_article_uuid', 'ancien_moyen',
    'nouveau_moyen', 'raison', 'operateur_email',
]

COLONNES_IMPRESSIONS = [
    'uuid', 'datetime', 'type_justificatif', 'is_duplicata',
    'format_emission', 'ligne_article_uuid', 'cloture_uuid',
    'uuid_transaction', 'operateur_email', 'printer_name',
]

COLONNES_SORTIES_CAISSE = [
    'uuid', 'datetime', 'point_de_vente', 'montant_total_centimes',
    'ventilation_json', 'note', 'operateur_email',
]

COLONNES_HISTORIQUE_FOND = [
    'uuid', 'datetime', 'point_de_vente', 'ancien_montant_centimes',
    'nouveau_montant_centimes', 'raison', 'operateur_email',
]


def _ecrire_csv(colonnes, lignes_dicts):
    """
    Ecrit un CSV en memoire (bytes UTF-8 avec BOM, delimiteur ;).
    / Writes a CSV in memory (UTF-8 bytes with BOM, delimiter ;).

    :param colonnes: list[str] — en-tetes
    :param lignes_dicts: list[dict] — lignes de donnees
    :return: bytes — contenu CSV
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=colonnes, delimiter=';',
                            extrasaction='ignore')
    writer.writeheader()
    for ligne in lignes_dicts:
        writer.writerow(ligne)
    # BOM UTF-8 pour Excel FR
    # / UTF-8 BOM for French Excel
    return b'\xef\xbb\xbf' + buffer.getvalue().encode('utf-8')


def _extraire_lignes_article(debut, fin):
    """
    Extrait les LigneArticle de la periode en liste de dicts.
    / Extracts LigneArticle for the period as a list of dicts.
    """
    filtres = {'sale_origin__in': [SaleOrigin.LABOUTIK, SaleOrigin.LABOUTIK_TEST]}
    if debut:
        filtres['datetime__gte'] = debut
    if fin:
        filtres['datetime__lte'] = fin

    lignes = LigneArticle.objects.filter(**filtres).select_related(
        'responsable', 'point_de_vente',
    ).order_by('datetime', 'pk')

    resultats = []
    for la in lignes:
        resultats.append({
            'uuid': str(la.uuid),
            'datetime': la.datetime.isoformat() if la.datetime else '',
            'article': la.article or '',
            'categorie': la.categorie or '',
            'prix_ttc_centimes': la.amount or 0,
            'quantite': str(la.qty),
            'payment_method': la.payment_method or '',
            'sale_origin': la.sale_origin or '',
            'taux_tva': str(la.vat),
            'total_ht_centimes': la.total_ht or 0,
            'total_tva_centimes': (la.amount or 0) - (la.total_ht or 0),
            'point_de_vente': str(la.point_de_vente.uuid) if la.point_de_vente else '',
            'operateur_email': la.responsable.email if la.responsable else '',
            'user_email': la.user_email() if hasattr(la, 'user_email') else '',
            'uuid_transaction': str(la.uuid_transaction) if la.uuid_transaction else '',
            'hmac_hash': la.hmac_hash or '',
        })
    return resultats


def _extraire_clotures(debut, fin):
    """
    Extrait les ClotureCaisse de la periode.
    / Extracts ClotureCaisse for the period.
    """
    filtres = {}
    if debut:
        filtres['datetime_cloture__gte'] = debut
    if fin:
        filtres['datetime_cloture__lte'] = fin

    clotures = ClotureCaisse.objects.filter(**filtres).select_related(
        'responsable', 'point_de_vente',
    ).order_by('datetime_cloture')

    resultats = []
    for c in clotures:
        resultats.append({
            'uuid': str(c.uuid),
            'datetime_cloture': c.datetime_cloture.isoformat() if c.datetime_cloture else '',
            'datetime_ouverture': c.datetime_ouverture.isoformat() if c.datetime_ouverture else '',
            'niveau': c.niveau or '',
            'numero_sequentiel': c.numero_sequentiel or 0,
            'total_especes': c.total_especes or 0,
            'total_carte_bancaire': c.total_carte_bancaire or 0,
            'total_cashless': c.total_cashless or 0,
            'total_cheque': getattr(c, 'total_cheque', 0) or 0,
            'total_general': c.total_general or 0,
            'nombre_transactions': c.nombre_transactions or 0,
            'total_perpetuel': c.total_perpetuel or 0,
            'hash_lignes': c.hash_lignes or '',
            'responsable_email': c.responsable.email if c.responsable else '',
            'point_de_vente': str(c.point_de_vente.uuid) if c.point_de_vente else '',
        })
    return resultats


def _extraire_corrections(debut, fin):
    """
    Extrait les CorrectionPaiement de la periode.
    / Extracts CorrectionPaiement for the period.
    """
    filtres = {}
    if debut:
        filtres['datetime__gte'] = debut
    if fin:
        filtres['datetime__lte'] = fin

    corrections = CorrectionPaiement.objects.filter(**filtres).select_related(
        'operateur',
    ).order_by('datetime')

    resultats = []
    for c in corrections:
        resultats.append({
            'uuid': str(c.uuid),
            'datetime': c.datetime.isoformat() if c.datetime else '',
            'ligne_article_uuid': str(c.ligne_article_id),
            'ancien_moyen': c.ancien_moyen or '',
            'nouveau_moyen': c.nouveau_moyen or '',
            'raison': c.raison or '',
            'operateur_email': c.operateur.email if c.operateur else '',
        })
    return resultats


def _extraire_impressions(debut, fin):
    """
    Extrait les ImpressionLog de la periode.
    / Extracts ImpressionLog for the period.
    """
    filtres = {}
    if debut:
        filtres['datetime__gte'] = debut
    if fin:
        filtres['datetime__lte'] = fin

    impressions = ImpressionLog.objects.filter(**filtres).select_related(
        'operateur', 'printer',
    ).order_by('datetime')

    resultats = []
    for i in impressions:
        resultats.append({
            'uuid': str(i.uuid),
            'datetime': i.datetime.isoformat() if i.datetime else '',
            'type_justificatif': i.type_justificatif or '',
            'is_duplicata': i.is_duplicata,
            'format_emission': i.format_emission or '',
            'ligne_article_uuid': str(i.ligne_article_id) if i.ligne_article_id else '',
            'cloture_uuid': str(i.cloture_id) if i.cloture_id else '',
            'uuid_transaction': str(i.uuid_transaction) if i.uuid_transaction else '',
            'operateur_email': i.operateur.email if i.operateur else '',
            'printer_name': i.printer.name if i.printer else '',
        })
    return resultats


def _extraire_sorties_caisse(debut, fin):
    """
    Extrait les SortieCaisse de la periode.
    / Extracts SortieCaisse for the period.
    """
    filtres = {}
    if debut:
        filtres['datetime__gte'] = debut
    if fin:
        filtres['datetime__lte'] = fin

    sorties = SortieCaisse.objects.filter(**filtres).select_related(
        'point_de_vente', 'operateur',
    ).order_by('datetime')

    resultats = []
    for s in sorties:
        resultats.append({
            'uuid': str(s.uuid),
            'datetime': s.datetime.isoformat() if s.datetime else '',
            'point_de_vente': str(s.point_de_vente.uuid) if s.point_de_vente else '',
            'montant_total_centimes': s.montant_total or 0,
            'ventilation_json': json.dumps(s.ventilation),
            'note': s.note or '',
            'operateur_email': s.operateur.email if s.operateur else '',
        })
    return resultats


def _extraire_historique_fond(debut, fin):
    """
    Extrait les HistoriqueFondDeCaisse de la periode.
    / Extracts HistoriqueFondDeCaisse for the period.
    """
    filtres = {}
    if debut:
        filtres['datetime__gte'] = debut
    if fin:
        filtres['datetime__lte'] = fin

    historiques = HistoriqueFondDeCaisse.objects.filter(**filtres).select_related(
        'point_de_vente', 'operateur',
    ).order_by('datetime')

    resultats = []
    for h in historiques:
        resultats.append({
            'uuid': str(h.uuid),
            'datetime': h.datetime.isoformat() if h.datetime else '',
            'point_de_vente': str(h.point_de_vente.uuid) if h.point_de_vente else '',
            'ancien_montant_centimes': h.ancien_montant,
            'nouveau_montant_centimes': h.nouveau_montant,
            'raison': h.raison or '',
            'operateur_email': h.operateur.email if h.operateur else '',
        })
    return resultats


def _calculer_hmac_fichier(contenu_bytes, cle_secrete):
    """
    Calcule le HMAC-SHA256 d'un contenu bytes.
    / Computes HMAC-SHA256 of bytes content.

    :param contenu_bytes: bytes — contenu du fichier
    :param cle_secrete: str — cle HMAC en clair
    :return: str — 64 caracteres hex
    """
    return hmac.new(
        cle_secrete.encode('utf-8'),
        contenu_bytes,
        hashlib.sha256,
    ).hexdigest()


def _construire_meta(schema, debut, fin, compteurs):
    """
    Construit le dict meta.json avec les infos du tenant.
    / Builds the meta.json dict with tenant info.

    :param schema: str — schema tenant
    :param debut: date ou None
    :param fin: date ou None
    :param compteurs: dict — nombre d'elements par type
    :return: dict
    """
    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    return {
        'logiciel': 'TiBillet/Lespass',
        'version': '2.0.0',
        'organisation': config.organisation or '',
        'adresse': config.adress or '',
        'code_postal': str(config.postal_code or ''),
        'ville': config.city or '',
        'siren': config.siren or '',
        'tva_number': config.tva_number or '',
        'periode_debut': debut.isoformat() if debut else 'tout',
        'periode_fin': fin.isoformat() if fin else 'tout',
        'date_generation': timezone.now().isoformat(),
        'schema_tenant': schema,
        'nombre_lignes_article': compteurs.get('lignes_article', 0),
        'nombre_clotures': compteurs.get('clotures', 0),
        'nombre_corrections': compteurs.get('corrections', 0),
        'nombre_impressions': compteurs.get('impressions', 0),
        'nombre_sorties_caisse': compteurs.get('sorties_caisse', 0),
        'nombre_historique_fond': compteurs.get('historique_fond', 0),
        'total_perpetuel_a_date': laboutik_config.total_perpetuel or 0,
    }


def generer_fichiers_archive(schema, debut=None, fin=None):
    """
    Genere tous les fichiers d'archive en memoire (dict nom → bytes).
    C'est la fonction centrale appelee par les 3 commands et la vue admin.
    / Generates all archive files in memory (dict name → bytes).
    Central function called by the 3 commands and the admin view.

    LOCALISATION : laboutik/archivage.py

    :param schema: str — schema tenant (pour meta.json)
    :param debut: date ou None — debut de la periode (None = tout)
    :param fin: date ou None — fin de la periode (None = tout)
    :return: dict {nom_fichier: bytes_contenu}
    """
    # Convertir les dates en datetime aware si fournies
    # / Convert dates to aware datetimes if provided
    debut_dt = timezone.make_aware(datetime.combine(debut, datetime.min.time())) if debut else None
    fin_dt = timezone.make_aware(datetime.combine(fin, datetime.max.time())) if fin else None

    # Extraire les donnees de chaque modele
    # / Extract data from each model
    donnees_lignes = _extraire_lignes_article(debut_dt, fin_dt)
    donnees_clotures = _extraire_clotures(debut_dt, fin_dt)
    donnees_corrections = _extraire_corrections(debut_dt, fin_dt)
    donnees_impressions = _extraire_impressions(debut_dt, fin_dt)
    donnees_sorties = _extraire_sorties_caisse(debut_dt, fin_dt)
    donnees_historique = _extraire_historique_fond(debut_dt, fin_dt)

    # Generer les CSV
    # / Generate CSVs
    fichiers = {}
    fichiers['lignes_article.csv'] = _ecrire_csv(COLONNES_LIGNES_ARTICLE, donnees_lignes)
    fichiers['clotures.csv'] = _ecrire_csv(COLONNES_CLOTURES, donnees_clotures)
    fichiers['corrections.csv'] = _ecrire_csv(COLONNES_CORRECTIONS, donnees_corrections)
    fichiers['impressions.csv'] = _ecrire_csv(COLONNES_IMPRESSIONS, donnees_impressions)
    fichiers['sorties_caisse.csv'] = _ecrire_csv(COLONNES_SORTIES_CAISSE, donnees_sorties)
    fichiers['historique_fond_de_caisse.csv'] = _ecrire_csv(COLONNES_HISTORIQUE_FOND, donnees_historique)

    # Generer le JSON structure complet
    # / Generate the full structured JSON
    donnees_completes = {
        'lignes_article': donnees_lignes,
        'clotures': donnees_clotures,
        'corrections': donnees_corrections,
        'impressions': donnees_impressions,
        'sorties_caisse': donnees_sorties,
        'historique_fond_de_caisse': donnees_historique,
    }
    fichiers['donnees.json'] = json.dumps(
        donnees_completes, ensure_ascii=False, indent=2,
    ).encode('utf-8')

    # Generer meta.json
    # / Generate meta.json
    compteurs = {
        'lignes_article': len(donnees_lignes),
        'clotures': len(donnees_clotures),
        'corrections': len(donnees_corrections),
        'impressions': len(donnees_impressions),
        'sorties_caisse': len(donnees_sorties),
        'historique_fond': len(donnees_historique),
    }
    meta = _construire_meta(schema, debut, fin, compteurs)
    fichiers['meta.json'] = json.dumps(
        meta, ensure_ascii=False, indent=2,
    ).encode('utf-8')

    return fichiers


def calculer_hash_fichiers(fichiers, cle_secrete):
    """
    Calcule le hash HMAC-SHA256 de chaque fichier + hash global.
    / Computes HMAC-SHA256 hash of each file + global hash.

    :param fichiers: dict {nom_fichier: bytes_contenu}
    :param cle_secrete: str — cle HMAC en clair
    :return: dict — contenu du hash.json
    """
    hashes_par_fichier = {}
    for nom_fichier in sorted(fichiers.keys()):
        hashes_par_fichier[nom_fichier] = _calculer_hmac_fichier(
            fichiers[nom_fichier], cle_secrete,
        )

    # Hash global = HMAC de la concatenation ordonnee des hash fichiers
    # / Global hash = HMAC of the sorted concatenation of file hashes
    concat_hashes = ''.join(
        hashes_par_fichier[k] for k in sorted(hashes_par_fichier.keys())
    )
    hash_global = hmac.new(
        cle_secrete.encode('utf-8'),
        concat_hashes.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return {
        'algorithme': 'HMAC-SHA256',
        'date_generation': timezone.now().isoformat(),
        'fichiers': hashes_par_fichier,
        'hash_global': hash_global,
    }


def empaqueter_zip(fichiers, hash_json_dict):
    """
    Empaquette les fichiers + hash.json dans un ZIP en memoire.
    / Packages files + hash.json into an in-memory ZIP.

    :param fichiers: dict {nom_fichier: bytes_contenu}
    :param hash_json_dict: dict — contenu du hash.json
    :return: bytes — contenu du ZIP
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for nom, contenu in fichiers.items():
            zf.writestr(nom, contenu)
        zf.writestr('hash.json', json.dumps(
            hash_json_dict, ensure_ascii=False, indent=2,
        ).encode('utf-8'))
    return buffer.getvalue()


def verifier_hash_archive(zip_bytes, cle_secrete):
    """
    Verifie l'integrite d'une archive ZIP en recalculant les hash HMAC.
    / Verifies a ZIP archive's integrity by recalculating HMAC hashes.

    :param zip_bytes: bytes — contenu du ZIP
    :param cle_secrete: str — cle HMAC en clair
    :return: tuple (est_valide: bool, resultats: list[dict])
    """
    resultats = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
        # Lire hash.json depuis l'archive
        # / Read hash.json from the archive
        hash_json = json.loads(zf.read('hash.json'))
        hashes_attendus = hash_json.get('fichiers', {})

        # Verifier chaque fichier
        # / Verify each file
        for nom_fichier, hash_attendu in hashes_attendus.items():
            contenu = zf.read(nom_fichier)
            hash_calcule = _calculer_hmac_fichier(contenu, cle_secrete)
            est_ok = (hash_calcule == hash_attendu)
            resultats.append({
                'fichier': nom_fichier,
                'attendu': hash_attendu,
                'calcule': hash_calcule,
                'ok': est_ok,
            })

        # Verifier le hash global
        # / Verify global hash
        concat_recalcule = ''.join(
            _calculer_hmac_fichier(zf.read(nom), cle_secrete)
            for nom in sorted(hashes_attendus.keys())
        )
        hash_global_calcule = hmac.new(
            cle_secrete.encode('utf-8'),
            concat_recalcule.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        hash_global_attendu = hash_json.get('hash_global', '')
        resultats.append({
            'fichier': 'HASH_GLOBAL',
            'attendu': hash_global_attendu,
            'calcule': hash_global_calcule,
            'ok': hash_global_calcule == hash_global_attendu,
        })

    est_valide = all(r['ok'] for r in resultats)
    return (est_valide, resultats)


def generer_readme_fiscal(schema):
    """
    Genere le README.txt en francais pour l'export fiscal.
    / Generates the French README.txt for fiscal export.

    :param schema: str — schema tenant
    :return: bytes — contenu UTF-8
    """
    config = Configuration.get_solo()
    texte = f"""EXPORT DES DONNEES D'ENCAISSEMENT
==================================

Logiciel : TiBillet/Lespass
Organisation : {config.organisation or ''}
SIRET : {config.siren or ''}
Date d'export : {timezone.now().strftime('%d/%m/%Y %H:%M')}

CONTENU DE CE DOSSIER
---------------------

- lignes_article.csv : Toutes les ventes enregistrees
- clotures.csv : Clotures de caisse (journalieres, mensuelles, annuelles)
- corrections.csv : Corrections de moyen de paiement (avec motif)
- impressions.csv : Journal des impressions de tickets
- sorties_caisse.csv : Retraits d'especes
- historique_fond_de_caisse.csv : Modifications du fond de caisse
- donnees.json : Export structure complet (format machine)
- meta.json : Informations sur l'organisation et la periode
- hash.json : Empreintes numeriques pour verification d'integrite

VERIFICATION D'INTEGRITE
-------------------------

Pour verifier que les fichiers n'ont pas ete modifies :

    python manage.py verifier_archive --archive=<chemin_zip> --schema={schema}

Les empreintes HMAC-SHA256 dans hash.json permettent de detecter
toute modification des fichiers apres l'export.

FORMAT DES MONTANTS
-------------------

Tous les montants sont en centimes d'euros (ex: 1250 = 12,50 EUR).
Le delimiteur CSV est le point-virgule (;).
L'encodage est UTF-8.
"""
    return texte.encode('utf-8')


def creer_entree_journal(type_operation, details, cle_secrete, operateur=None):
    """
    Cree une entree JournalOperation avec chainages HMAC.
    / Creates a JournalOperation entry with HMAC chaining.

    :param type_operation: str — ARCHIVAGE, VERIFICATION, EXPORT_FISCAL
    :param details: dict — metadonnees de l'operation
    :param cle_secrete: str — cle HMAC en clair
    :param operateur: TibilletUser ou None
    :return: JournalOperation instance
    """
    from laboutik.models import JournalOperation

    # Recuperer le HMAC de la derniere entree
    # / Get the HMAC of the last entry
    derniere_entree = JournalOperation.objects.order_by('-datetime', '-pk').first()
    previous_hmac = derniere_entree.hmac_hash if derniere_entree else ''

    # Creer l'entree (sans HMAC d'abord pour avoir le datetime)
    # / Create the entry (without HMAC first to get the datetime)
    entree = JournalOperation.objects.create(
        type_operation=type_operation,
        operateur=operateur,
        details=details,
    )

    # Calculer le HMAC avec le datetime reel
    # / Compute HMAC with the actual datetime
    donnees = json.dumps([
        entree.type_operation,
        entree.datetime.isoformat(),
        json.dumps(entree.details, sort_keys=True),
        previous_hmac,
    ])
    entree.hmac_hash = hmac.new(
        cle_secrete.encode('utf-8'),
        donnees.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    entree.save(update_fields=['hmac_hash'])

    return entree
```

- [ ] **Step 2: Verifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "import laboutik.archivage; print('OK')"
```

---

## Task 5 : Management command `archiver_donnees`

**Files:**
- Create: `laboutik/management/commands/archiver_donnees.py`

- [ ] **Step 1: Creer la command**

```python
"""
Management command pour archiver les donnees d'encaissement (LNE Ex.10-12).
Genere un ZIP contenant CSV + JSON + hash HMAC-SHA256.
/ Management command to archive POS data (LNE Ex.10-12).
Generates a ZIP containing CSV + JSON + HMAC-SHA256 hash.

LOCALISATION : laboutik/management/commands/archiver_donnees.py

Usage :
    docker exec lespass_django poetry run python manage.py archiver_donnees \
        --schema=lespass --debut=2026-01-01 --fin=2026-12-31 --output=/tmp/
"""
import os
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import schema_context

from Customers.models import Client


class Command(BaseCommand):
    help = (
        'Archive les donnees d\'encaissement en ZIP (CSV + JSON + hash HMAC). '
        '/ Archives POS data as ZIP (CSV + JSON + HMAC hash).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Schema du tenant (ex: lespass)',
        )
        parser.add_argument(
            '--debut', type=str, required=True,
            help='Date de debut (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--fin', type=str, required=True,
            help='Date de fin (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--output', type=str, required=True,
            help='Repertoire de sortie pour le ZIP',
        )

    def handle(self, *args, **options):
        schema = options['schema']
        debut_str = options['debut']
        fin_str = options['fin']
        output_dir = options['output']

        # Parser les dates
        # / Parse dates
        try:
            debut = date.fromisoformat(debut_str)
            fin = date.fromisoformat(fin_str)
        except ValueError as e:
            raise CommandError(f"Format de date invalide : {e}")

        # Garde : periode max 1 an (LNE Ex.11)
        # / Guard: max 1 year period (LNE Ex.11)
        if (fin - debut).days > 365:
            raise CommandError(
                "La periode ne peut pas depasser 1 an (365 jours). "
                f"Periode demandee : {(fin - debut).days} jours."
            )

        if fin < debut:
            raise CommandError("La date de fin doit etre apres la date de debut.")

        # Verifier que le tenant existe
        # / Verify tenant exists
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(f"Tenant '{schema}' introuvable.")

        # Creer le repertoire de sortie si necessaire
        # / Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)

        with schema_context(schema):
            from laboutik.archivage import (
                calculer_hash_fichiers, creer_entree_journal,
                empaqueter_zip, generer_fichiers_archive,
            )
            from laboutik.models import LaboutikConfiguration

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()
            if not cle:
                raise CommandError(
                    f"[{schema}] Pas de cle HMAC configuree. "
                    "Lancez create_test_pos_data ou configurez la cle dans l'admin."
                )

            self.stdout.write(f"[{schema}] Archivage du {debut} au {fin}...")

            # Generer les fichiers
            # / Generate files
            fichiers = generer_fichiers_archive(schema, debut, fin)

            # Calculer les hash HMAC
            # / Compute HMAC hashes
            hash_json = calculer_hash_fichiers(fichiers, cle)

            # Empaqueter en ZIP
            # / Package as ZIP
            zip_bytes = empaqueter_zip(fichiers, hash_json)

            # Ecrire le ZIP
            # / Write the ZIP
            timestamp = debut_str.replace('-', '') + '_' + fin_str.replace('-', '')
            nom_zip = f"{schema}_{timestamp}.zip"
            chemin_zip = os.path.join(output_dir, nom_zip)
            with open(chemin_zip, 'wb') as f:
                f.write(zip_bytes)

            # Creer l'entree journal
            # / Create journal entry
            creer_entree_journal(
                type_operation='ARCHIVAGE',
                details={
                    'periode_debut': debut_str,
                    'periode_fin': fin_str,
                    'chemin_zip': chemin_zip,
                    'hash_global': hash_json['hash_global'],
                    'taille_zip_octets': len(zip_bytes),
                },
                cle_secrete=cle,
            )

            self.stdout.write(self.style.SUCCESS(
                f"  Archive creee : {chemin_zip} ({len(zip_bytes)} octets)"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"  Hash global : {hash_json['hash_global']}"
            ))
```

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python manage.py archiver_donnees --help
```

Expected: affiche l'aide avec les 4 arguments.

---

## Task 6 : Management command `verifier_archive`

**Files:**
- Create: `laboutik/management/commands/verifier_archive.py`

- [ ] **Step 1: Creer la command**

```python
"""
Management command pour verifier l'integrite d'une archive ZIP (LNE Ex.12).
/ Management command to verify ZIP archive integrity (LNE Ex.12).

LOCALISATION : laboutik/management/commands/verifier_archive.py

Usage :
    docker exec lespass_django poetry run python manage.py verifier_archive \
        --archive=/tmp/lespass_20260101_20261231.zip --schema=lespass
"""
import sys

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from Customers.models import Client


class Command(BaseCommand):
    help = (
        'Verifie l\'integrite HMAC d\'une archive ZIP. '
        '/ Verifies HMAC integrity of a ZIP archive.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--archive', type=str, required=True,
            help='Chemin vers le fichier ZIP a verifier',
        )
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Schema du tenant (pour recuperer la cle HMAC)',
        )

    def handle(self, *args, **options):
        chemin_archive = options['archive']
        schema = options['schema']

        # Verifier que le fichier existe
        # / Verify file exists
        try:
            with open(chemin_archive, 'rb') as f:
                zip_bytes = f.read()
        except FileNotFoundError:
            raise CommandError(f"Fichier introuvable : {chemin_archive}")

        # Verifier que le tenant existe
        # / Verify tenant exists
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(f"Tenant '{schema}' introuvable.")

        with schema_context(schema):
            from laboutik.archivage import creer_entree_journal, verifier_hash_archive
            from laboutik.models import LaboutikConfiguration

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()
            if not cle:
                raise CommandError(f"[{schema}] Pas de cle HMAC configuree.")

            self.stdout.write(f"[{schema}] Verification de {chemin_archive}...")

            est_valide, resultats = verifier_hash_archive(zip_bytes, cle)

            # Afficher les resultats
            # / Display results
            nb_ok = 0
            nb_ko = 0
            for r in resultats:
                if r['ok']:
                    nb_ok += 1
                    self.stdout.write(self.style.SUCCESS(f"  OK  {r['fichier']}"))
                else:
                    nb_ko += 1
                    self.stdout.write(self.style.ERROR(f"  KO  {r['fichier']}"))
                    self.stdout.write(f"       attendu : {r['attendu']}")
                    self.stdout.write(f"       calcule : {r['calcule']}")

            # Creer l'entree journal
            # / Create journal entry
            creer_entree_journal(
                type_operation='VERIFICATION',
                details={
                    'fichier_archive': chemin_archive,
                    'resultat': 'OK' if est_valide else 'KO',
                    'nb_fichiers_ok': nb_ok,
                    'nb_fichiers_ko': nb_ko,
                },
                cle_secrete=cle,
            )

            if est_valide:
                self.stdout.write(self.style.SUCCESS(
                    f"\n  ARCHIVE INTEGRE — {nb_ok} fichier(s) verifie(s), 0 erreur"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"\n  ALERTE — {nb_ko} fichier(s) corrompu(s) sur {nb_ok + nb_ko}"
                ))
                sys.exit(1)
```

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python manage.py verifier_archive --help
```

---

## Task 7 : Management command `acces_fiscal`

**Files:**
- Create: `laboutik/management/commands/acces_fiscal.py`

- [ ] **Step 1: Creer la command**

```python
"""
Management command pour generer un export complet pour l'administration fiscale (LNE Ex.19).
/ Management command to generate a full export for fiscal administration (LNE Ex.19).

LOCALISATION : laboutik/management/commands/acces_fiscal.py

Usage :
    docker exec lespass_django poetry run python manage.py acces_fiscal \
        --schema=lespass --output=/tmp/export_fiscal/
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import schema_context

from Customers.models import Client


class Command(BaseCommand):
    help = (
        'Genere un export complet pour l\'administration fiscale. '
        '/ Generates a full export for fiscal administration.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Schema du tenant (ex: lespass)',
        )
        parser.add_argument(
            '--output', type=str, required=True,
            help='Repertoire de sortie',
        )

    def handle(self, *args, **options):
        schema = options['schema']
        output_base = options['output']

        # Verifier que le tenant existe
        # / Verify tenant exists
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(f"Tenant '{schema}' introuvable.")

        # Creer le dossier de sortie
        # / Create output directory
        date_str = timezone.now().strftime('%Y-%m-%d')
        nom_dossier = f"export_fiscal_{schema}_{date_str}"
        chemin_dossier = os.path.join(output_base, nom_dossier)
        os.makedirs(chemin_dossier, exist_ok=True)

        with schema_context(schema):
            from laboutik.archivage import (
                calculer_hash_fichiers, creer_entree_journal,
                generer_fichiers_archive, generer_readme_fiscal,
            )
            from laboutik.models import LaboutikConfiguration

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()
            if not cle:
                raise CommandError(f"[{schema}] Pas de cle HMAC configuree.")

            self.stdout.write(f"[{schema}] Export fiscal complet (tout l'historique)...")

            # Generer les fichiers sans limite de periode
            # / Generate files without period limit
            fichiers = generer_fichiers_archive(schema, debut=None, fin=None)

            # Calculer les hash HMAC
            # / Compute HMAC hashes
            hash_json = calculer_hash_fichiers(fichiers, cle)

            # Ecrire chaque fichier dans le dossier
            # / Write each file to the directory
            for nom, contenu in fichiers.items():
                chemin = os.path.join(chemin_dossier, nom)
                with open(chemin, 'wb') as f:
                    f.write(contenu)

            # Ecrire hash.json
            # / Write hash.json
            with open(os.path.join(chemin_dossier, 'hash.json'), 'w') as f:
                json.dump(hash_json, f, ensure_ascii=False, indent=2)

            # Ecrire README.txt
            # / Write README.txt
            readme_bytes = generer_readme_fiscal(schema)
            with open(os.path.join(chemin_dossier, 'README.txt'), 'wb') as f:
                f.write(readme_bytes)

            # Creer l'entree journal
            # / Create journal entry
            nb_total = sum(1 for _ in fichiers) + 2  # +hash.json +README.txt
            creer_entree_journal(
                type_operation='EXPORT_FISCAL',
                details={
                    'chemin_dossier': chemin_dossier,
                    'nb_fichiers': nb_total,
                    'date_export': date_str,
                },
                cle_secrete=cle,
            )

            self.stdout.write(self.style.SUCCESS(
                f"  Export genere dans : {chemin_dossier}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"  {nb_total} fichiers generes"
            ))
```

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python manage.py acces_fiscal --help
```

---

## Task 8 : Bouton export fiscal dans l'admin

**Files:**
- Modify: `Administration/admin/laboutik.py` (dans `ClotureCaisseAdmin`)

- [ ] **Step 1: Ajouter l'URL dans `get_urls()`**

Dans `ClotureCaisseAdmin.get_urls()` (ligne ~558 de `Administration/admin/laboutik.py`), ajouter dans `custom_urls` :

```python
            path(
                'export-fiscal/',
                self.admin_site.admin_view(self.export_fiscal),
                name='laboutik_cloturecaisse_export_fiscal',
            ),
```

- [ ] **Step 2: Ajouter la vue `export_fiscal`**

Apres la methode `exporter_excel`, ajouter :

```python
    def export_fiscal(self, request):
        """
        GET : formulaire avec dates debut/fin.
        POST : genere le ZIP et le propose en telechargement.
        / GET: form with start/end dates.
        POST: generates ZIP and offers download.

        LOCALISATION : Administration/admin/laboutik.py
        """
        from django.db import connection
        from django.http import HttpResponse

        if request.method == 'GET':
            # Formulaire simple avec 2 champs date
            # / Simple form with 2 date fields
            html = """
            <div style="max-width: 500px; margin: 40px auto; font-family: sans-serif;">
                <h2 style="margin-bottom: 20px;">Export fiscal</h2>
                <p style="color: #666; margin-bottom: 20px;">
                    Genere un fichier ZIP contenant toutes les donnees d'encaissement
                    avec empreintes HMAC pour verification d'integrite.
                </p>
                <form method="post">
                    <input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">
                    <div style="margin-bottom: 15px;">
                        <label style="display: block; margin-bottom: 5px; font-weight: bold;">
                            Date de debut (optionnel) :
                        </label>
                        <input type="date" name="debut"
                               style="padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%;">
                    </div>
                    <div style="margin-bottom: 15px;">
                        <label style="display: block; margin-bottom: 5px; font-weight: bold;">
                            Date de fin (optionnel) :
                        </label>
                        <input type="date" name="fin"
                               style="padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%;">
                    </div>
                    <p style="color: #888; font-size: 0.9em; margin-bottom: 20px;">
                        Laissez vide pour exporter tout l'historique.
                    </p>
                    <button type="submit"
                            style="background: var(--color-primary-600, #2563eb); color: white;
                                   padding: 10px 24px; border: none; border-radius: 6px;
                                   cursor: pointer; font-size: 1em;">
                        Telecharger l'export fiscal
                    </button>
                </form>
            </div>
            """.format(csrf=request.META.get('CSRF_COOKIE', ''))
            from django.http import HttpResponse as HR
            from django.middleware.csrf import get_token
            html = html.replace('{csrf}', get_token(request))
            return HR(html)

        # POST : generer le ZIP
        # / POST: generate ZIP
        from datetime import date

        from laboutik.archivage import (
            calculer_hash_fichiers, creer_entree_journal,
            empaqueter_zip, generer_fichiers_archive,
        )
        from laboutik.models import LaboutikConfiguration

        config = LaboutikConfiguration.get_solo()
        cle = config.get_hmac_key()
        if not cle:
            return HttpResponse("Pas de cle HMAC configuree.", status=500)

        schema = connection.schema_name

        # Parser les dates optionnelles
        # / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get('debut', '').strip()
        fin_str = request.POST.get('fin', '').strip()
        if debut_str:
            debut = date.fromisoformat(debut_str)
        if fin_str:
            fin = date.fromisoformat(fin_str)

        # Generer l'archive
        # / Generate archive
        fichiers = generer_fichiers_archive(schema, debut, fin)
        hash_json = calculer_hash_fichiers(fichiers, cle)
        zip_bytes = empaqueter_zip(fichiers, hash_json)

        # Journal
        # / Log
        creer_entree_journal(
            type_operation='EXPORT_FISCAL',
            details={
                'source': 'admin',
                'hash_global': hash_json['hash_global'],
                'operateur': request.user.email if request.user else '',
            },
            cle_secrete=cle,
            operateur=request.user if request.user.is_authenticated else None,
        )

        # Reponse telechargement
        # / Download response
        date_str = timezone.now().strftime('%Y%m%d')
        nom_fichier = f"export_fiscal_{schema}_{date_str}.zip"
        response = HttpResponse(zip_bytes, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
        return response
```

- [ ] **Step 3: Ajouter un lien dans le template changelist**

Dans `ClotureCaisseAdmin`, ajouter ou modifier `changelist_view` pour injecter un bouton :

```python
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['export_fiscal_url'] = 'export-fiscal/'
        return super().changelist_view(request, extra_context)
```

Note : le lien sera accessible directement via l'URL `/admin/laboutik/cloturecaisse/export-fiscal/`. Pas besoin de template custom — l'URL suffit. On peut l'ajouter dans la sidebar ou comme action.

- [ ] **Step 4: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 9 : Tests

**Files:**
- Create: `tests/pytest/test_archivage_fiscal.py`

- [ ] **Step 1: Creer le fichier de test**

```python
"""
tests/pytest/test_archivage_fiscal.py — Session 18 : archivage fiscal + acces administration.
/ Session 18: fiscal archiving + administration access.

Couvre :
- JournalOperation (creation, chainages HMAC)
- HistoriqueFondDeCaisse (creation via fond_de_caisse POST)
- archiver_donnees (ZIP, contenu, hash, periode max)
- verifier_archive (OK, KO)
- acces_fiscal (dossier, README)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py -v
"""
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import json
import os
import tempfile
import zipfile

from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

import pytest

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct, LigneArticle, PaymentMethod, Price,
    PriceSold, Product, ProductSold, SaleOrigin,
)
from laboutik.models import (
    ClotureCaisse, CorrectionPaiement, HistoriqueFondDeCaisse,
    JournalOperation, LaboutikConfiguration, PointDeVente,
    SortieCaisse,
)


class TestArchivageFiscal(FastTenantTestCase):
    """Tests pour l'archivage fiscal et l'acces administration (session 18).
    / Tests for fiscal archiving and administration access (session 18)."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_archivage'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-archivage.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Archivage'

    def setUp(self):
        """Cree les donnees minimales pour chaque test.
        / Creates minimal data for each test."""
        connection.set_tenant(self.tenant)

        # Configuration HMAC
        # / HMAC configuration
        self.config = LaboutikConfiguration.get_solo()
        self.config.set_hmac_key('cle-test-archivage-2026')
        self.config.fond_de_caisse = 5000  # 50,00 €
        self.config.save()
        self.cle_hmac = self.config.get_hmac_key()

        # Categorie et produit POS
        # / POS category and product
        self.categorie = CategorieProduct.objects.create(name='Boissons Test Arch')
        self.produit = Product.objects.create(
            name='Biere Test Arch',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit, name='Pinte', prix=Decimal('5.00'), publish=True,
        )

        # Point de vente
        # / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test Arch',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
        )
        self.pv.products.add(self.produit)

        # Utilisateur admin
        # / Admin user
        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-arch@tibillet.localhost',
            defaults={'username': 'admin-arch@tibillet.localhost', 'is_staff': True, 'is_active': True},
        )

        # Creer une LigneArticle pour avoir des donnees a archiver
        # / Create a LigneArticle to have data to archive
        product_sold = ProductSold.objects.create(
            product=self.produit, name='Biere Test Arch',
        )
        price_sold = PriceSold.objects.create(
            productsold=product_sold, prix=Decimal('5.00'),
            qty_sold=1, price=self.prix,
        )
        self.ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            article='Biere Test Arch',
            categorie='Boissons Test Arch',
            amount=500,
            total_ht=417,
            qty=1,
            vat=Decimal('20.00'),
            payment_method=PaymentMethod.CASH,
            status='V',
            sale_origin=SaleOrigin.LABOUTIK,
            responsable=self.admin,
            point_de_vente=self.pv,
        )

    # ------------------------------------------------------------------
    # Tests JournalOperation
    # ------------------------------------------------------------------

    def test_journal_operation_creation(self):
        """Une entree JournalOperation est creee avec les bons champs.
        / A JournalOperation entry is created with correct fields."""
        from laboutik.archivage import creer_entree_journal

        entree = creer_entree_journal(
            type_operation='ARCHIVAGE',
            details={'test': True, 'periode': '2026'},
            cle_secrete=self.cle_hmac,
            operateur=self.admin,
        )

        assert entree.type_operation == 'ARCHIVAGE'
        assert entree.details['test'] is True
        assert entree.operateur == self.admin
        assert entree.hmac_hash != ''
        assert len(entree.hmac_hash) == 64

    def test_journal_operation_hmac_chaine(self):
        """Deux entrees successives ont des HMAC differents (chainage).
        / Two successive entries have different HMACs (chaining)."""
        from laboutik.archivage import creer_entree_journal

        entree_1 = creer_entree_journal(
            type_operation='ARCHIVAGE',
            details={'numero': 1},
            cle_secrete=self.cle_hmac,
        )
        entree_2 = creer_entree_journal(
            type_operation='VERIFICATION',
            details={'numero': 2},
            cle_secrete=self.cle_hmac,
        )

        assert entree_1.hmac_hash != entree_2.hmac_hash
        assert entree_1.hmac_hash != ''
        assert entree_2.hmac_hash != ''

    # ------------------------------------------------------------------
    # Tests HistoriqueFondDeCaisse
    # ------------------------------------------------------------------

    def test_historique_fond_de_caisse_creation(self):
        """HistoriqueFondDeCaisse est cree avec les bons montants.
        / HistoriqueFondDeCaisse is created with correct amounts."""
        historique = HistoriqueFondDeCaisse.objects.create(
            ancien_montant=5000,
            nouveau_montant=10000,
            operateur=self.admin,
            point_de_vente=self.pv,
        )

        assert historique.ancien_montant == 5000
        assert historique.nouveau_montant == 10000
        assert historique.operateur == self.admin

    def test_historique_fond_via_api(self):
        """Le POST sur fond-de-caisse cree un HistoriqueFondDeCaisse.
        / POST on fond-de-caisse creates a HistoriqueFondDeCaisse."""
        client = TenantClient(self.tenant)
        client.force_login(self.admin)

        # Compter les historiques avant
        # / Count history entries before
        nb_avant = HistoriqueFondDeCaisse.objects.count()

        response = client.post(
            '/laboutik/caisse/fond-de-caisse/',
            {'montant_euros': '100,00'},
        )

        nb_apres = HistoriqueFondDeCaisse.objects.count()
        assert nb_apres == nb_avant + 1

        dernier = HistoriqueFondDeCaisse.objects.order_by('-datetime').first()
        assert dernier.ancien_montant == 5000  # 50,00 € initial
        assert dernier.nouveau_montant == 10000  # 100,00 € nouveau

    # ------------------------------------------------------------------
    # Tests archivage ZIP
    # ------------------------------------------------------------------

    def test_archiver_genere_zip(self):
        """archiver_donnees produit un ZIP non vide.
        / archiver_donnees produces a non-empty ZIP."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            # Trouver le ZIP genere
            # / Find the generated ZIP
            zips = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            assert len(zips) == 1

            chemin_zip = os.path.join(tmpdir, zips[0])
            taille = os.path.getsize(chemin_zip)
            assert taille > 0

    def test_archive_contient_fichiers_attendus(self):
        """Le ZIP contient les 6 CSV + 3 JSON.
        / The ZIP contains 6 CSVs + 3 JSONs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            zips = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, zips[0])

            with zipfile.ZipFile(chemin_zip, 'r') as zf:
                noms = zf.namelist()

            fichiers_attendus = [
                'lignes_article.csv', 'clotures.csv', 'corrections.csv',
                'impressions.csv', 'sorties_caisse.csv',
                'historique_fond_de_caisse.csv',
                'donnees.json', 'meta.json', 'hash.json',
            ]
            for fichier in fichiers_attendus:
                assert fichier in noms, f"{fichier} manquant dans le ZIP"

    def test_archive_hash_integrite(self):
        """Les hash HMAC dans hash.json correspondent aux fichiers.
        / HMAC hashes in hash.json match the files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            zips = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, zips[0])

            with open(chemin_zip, 'rb') as f:
                zip_bytes = f.read()

            from laboutik.archivage import verifier_hash_archive
            est_valide, resultats = verifier_hash_archive(zip_bytes, self.cle_hmac)

            assert est_valide is True
            for r in resultats:
                assert r['ok'] is True, f"Hash KO pour {r['fichier']}"

    def test_archive_periode_max_1_an(self):
        """Erreur si la periode depasse 365 jours.
        / Error if period exceeds 365 days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(CommandError, match="365 jours"):
                call_command(
                    'archiver_donnees',
                    schema=self.tenant.schema_name,
                    debut='2025-01-01',
                    fin='2026-06-01',
                    output=tmpdir,
                )

    # ------------------------------------------------------------------
    # Tests verification archive
    # ------------------------------------------------------------------

    def test_verifier_archive_ok(self):
        """Archive non modifiee → verification OK.
        / Unmodified archive → verification OK."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            zips = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, zips[0])

            # Ne doit pas lever d'erreur ni sys.exit(1)
            # / Should not raise error or sys.exit(1)
            call_command(
                'verifier_archive',
                archive=chemin_zip,
                schema=self.tenant.schema_name,
            )

    def test_verifier_archive_ko(self):
        """Fichier modifie dans le ZIP → verification KO.
        / Modified file in ZIP → verification KO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            zips = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, zips[0])

            # Modifier un fichier dans le ZIP
            # / Modify a file in the ZIP
            chemin_modifie = os.path.join(tmpdir, 'modifie.zip')
            with zipfile.ZipFile(chemin_zip, 'r') as zf_src:
                with zipfile.ZipFile(chemin_modifie, 'w') as zf_dst:
                    for item in zf_src.namelist():
                        contenu = zf_src.read(item)
                        if item == 'meta.json':
                            # Modifier le contenu
                            # / Modify content
                            contenu = b'{"falsifie": true}'
                        zf_dst.writestr(item, contenu)

            # La verification doit echouer (sys.exit(1))
            # / Verification should fail (sys.exit(1))
            with pytest.raises(SystemExit) as exc_info:
                call_command(
                    'verifier_archive',
                    archive=chemin_modifie,
                    schema=self.tenant.schema_name,
                )
            assert exc_info.value.code == 1

    # ------------------------------------------------------------------
    # Tests export fiscal
    # ------------------------------------------------------------------

    def test_acces_fiscal_genere_dossier(self):
        """acces_fiscal genere un dossier avec README.txt.
        / acces_fiscal generates a folder with README.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'acces_fiscal',
                schema=self.tenant.schema_name,
                output=tmpdir,
            )

            # Trouver le dossier genere
            # / Find the generated directory
            dossiers = [d for d in os.listdir(tmpdir) if d.startswith('export_fiscal_')]
            assert len(dossiers) == 1

            chemin_dossier = os.path.join(tmpdir, dossiers[0])

            # Verifier la presence du README
            # / Verify README presence
            assert os.path.exists(os.path.join(chemin_dossier, 'README.txt'))
            assert os.path.exists(os.path.join(chemin_dossier, 'lignes_article.csv'))
            assert os.path.exists(os.path.join(chemin_dossier, 'hash.json'))
            assert os.path.exists(os.path.join(chemin_dossier, 'meta.json'))

    def test_journal_operation_apres_archivage(self):
        """L'archivage cree une entree JournalOperation.
        / Archiving creates a JournalOperation entry."""
        nb_avant = JournalOperation.objects.count()

        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

        nb_apres = JournalOperation.objects.count()
        assert nb_apres > nb_avant

        derniere = JournalOperation.objects.order_by('-datetime').first()
        assert derniere.type_operation == 'ARCHIVAGE'
        assert 'hash_global' in derniere.details
```

- [ ] **Step 2: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py -v
```

Expected: 14 tests verts.

- [ ] **Step 3: Lancer tous les tests laboutik pour verifier 0 regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_paiement_*.py tests/pytest/test_cloture_*.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_archivage_fiscal.py -v
```

Expected: tous les tests passent, 0 regression.

---

## Task 10 : Verification finale + ruff

- [ ] **Step 1: Ruff check + format sur tous les fichiers modifies**

```bash
docker exec lespass_django poetry run ruff check --fix laboutik/models.py laboutik/archivage.py laboutik/views.py laboutik/management/commands/archiver_donnees.py laboutik/management/commands/verifier_archive.py laboutik/management/commands/acces_fiscal.py
docker exec lespass_django poetry run ruff format laboutik/models.py laboutik/archivage.py laboutik/views.py laboutik/management/commands/archiver_donnees.py laboutik/management/commands/verifier_archive.py laboutik/management/commands/acces_fiscal.py
```

- [ ] **Step 2: Django check**

```bash
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 3: Test complet pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected: tous les tests passent (332+ existants + 14 nouveaux).
