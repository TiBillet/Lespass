# Session 13 — Clôtures J/M/A + Total Perpétuel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrichir `ClotureCaisse` avec 3 niveaux de clôture (J/M/A), numéro séquentiel, total perpétuel et hash d'intégrité. Connecter `cloturer()` au `RapportComptableService`. Ajouter les clôtures M/A automatiques via Celery Beat.

**Architecture:** Le modèle `ClotureCaisse` est enrichi de 4 champs (niveau, numero_sequentiel, total_perpetuel, hash_lignes). La vue `cloturer()` est réécrite pour utiliser `RapportComptableService` au lieu du calcul inline. `datetime_ouverture` est calculé automatiquement. Les clôtures M/A sont des tâches Celery Beat qui agrègent les clôtures J.

**Tech Stack:** Django 4.2, PostgreSQL, Celery, django-tenants, DRF

**Contexte session 12 (prérequis terminé):**
- `laboutik/integrity.py` : `calculer_hmac()`, `verifier_chaine()`, `calculer_total_ht()`, `ligne_couverte_par_cloture()`
- `laboutik/reports.py` : `RapportComptableService` (13 méthodes + `calculer_hash_lignes()` + `generer_rapport_complet()`)
- `LaboutikConfiguration` : `hmac_key` (Fernet), `total_perpetuel`, `fond_de_caisse`, `rapport_emails`, etc.
- `LigneArticle` : `hmac_hash`, `previous_hmac`, `total_ht`, `point_de_vente` FK

---

## File Structure

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `laboutik/models.py` | Modifier | Enrichir `ClotureCaisse` (+4 champs, Meta unique_together) + modifier `datetime_cloture` |
| `laboutik/migrations/0010_cloture_enrichie.py` | Créer (auto) | Migration des nouveaux champs |
| `laboutik/serializers.py` | Modifier | Retirer `datetime_ouverture` de `ClotureSerializer` |
| `laboutik/views.py` | Modifier | Réécrire `cloturer()` : datetime_ouverture auto + RapportComptableService + numéro séquentiel + total perpétuel |
| `laboutik/tasks.py` | Modifier | Ajouter `generer_cloture_mensuelle()` et `generer_cloture_annuelle()` |
| `TiBillet/celery.py` | Modifier | Enregistrer les tâches périodiques M/A dans `setup_periodic_tasks()` |
| `laboutik/integrity.py` | Déjà fait | `ligne_couverte_par_cloture()` existe déjà (session 12) — ajouter filtre `niveau='J'` |
| `Administration/admin/laboutik.py` | Modifier | Enrichir `ClotureCaisseAdmin` (list_display, filtres, lecture seule, badge intégrité) |
| `tests/pytest/test_cloture_enrichie.py` | Créer | 7+ tests enrichissement clôture |
| `tests/pytest/test_cloture_caisse.py` | Modifier | Adapter les 7 tests existants (retirer `datetime_ouverture` du POST) |

---

## Task 1: Migration — Enrichir ClotureCaisse

**Files:**
- Modify: `laboutik/models.py:792-884` (classe `ClotureCaisse`)
- Create: `laboutik/migrations/0010_cloture_enrichie.py` (auto-générée)

- [ ] **Step 1: Ajouter les 4 champs sur ClotureCaisse**

Dans `laboutik/models.py`, ajouter après le champ `uuid` et avant `point_de_vente` (ou dans un bloc logique après `nombre_transactions`) :

```python
# --- Niveau de cloture (conformite LNE exigence 6) ---
# J = journaliere (declenchee par le caissier)
# M = mensuelle (automatique Celery Beat, agrege les J du mois)
# A = annuelle (automatique Celery Beat, agrege les M de l'annee)
# / Closure level (LNE compliance req. 6)
# J = daily (triggered by cashier)
# M = monthly (automatic Celery Beat, aggregates daily closures)
# A = annual (automatic Celery Beat, aggregates monthly closures)
JOURNALIERE = 'J'
MENSUELLE = 'M'
ANNUELLE = 'A'
NIVEAU_CHOICES = [
    (JOURNALIERE, _('Daily')),
    (MENSUELLE, _('Monthly')),
    (ANNUELLE, _('Annual')),
]
niveau = models.CharField(
    max_length=1, choices=NIVEAU_CHOICES, default=JOURNALIERE,
    verbose_name=_("Closure level"),
    help_text=_(
        "J = journaliere (caissier), M = mensuelle (auto), A = annuelle (auto). "
        "/ J = daily (cashier), M = monthly (auto), A = annual (auto)."
    ),
)

# Numero sequentiel par PV et par niveau, sans trou (conformite LNE exigence 6)
# / Sequential number per POS and per level, no gap (LNE compliance req. 6)
numero_sequentiel = models.PositiveIntegerField(
    default=0,
    verbose_name=_("Sequential number"),
    help_text=_(
        "Numero sequentiel par point de vente et par niveau. Sans trou. "
        "/ Sequential number per POS and per level. No gap."
    ),
)

# Total perpetuel snapshot au moment de la cloture (conformite LNE exigence 7)
# Le total perpetuel global est dans LaboutikConfiguration.total_perpetuel.
# Ce champ est une copie au moment de la cloture.
# / Perpetual total snapshot at closure time (LNE compliance req. 7)
total_perpetuel = models.IntegerField(
    default=0,
    verbose_name=_("Perpetual total (cents)"),
    help_text=_(
        "Total cumule depuis la mise en service, snapshot au moment de cette cloture. "
        "/ Cumulative total since first use, snapshot at this closure time."
    ),
)

# Hash SHA-256 des LigneArticle couvertes (filet de securite)
# Garantit qu'aucune ligne n'a ete modifiee entre le calcul et la sauvegarde.
# / SHA-256 hash of covered LigneArticle (safety net)
hash_lignes = models.CharField(
    max_length=64, blank=True, default='',
    verbose_name=_("Lines integrity hash"),
    help_text=_(
        "SHA-256 des LigneArticle couvertes. Filet de securite. "
        "/ SHA-256 of covered LigneArticle. Safety net."
    ),
)
```

- [ ] **Step 2: Modifier `datetime_cloture` de `auto_now_add=True` à `default=timezone.now`**

Remplacer :
```python
datetime_cloture = models.DateTimeField(
    auto_now_add=True,
    verbose_name=_("Closure datetime"),
)
```

Par :
```python
datetime_cloture = models.DateTimeField(
    default=timezone.now,
    verbose_name=_("Closure datetime"),
    help_text=_("Moment of the closure. Set explicitly, not auto_now_add."),
)
```

Ajouter l'import `timezone` en haut du fichier si absent :
```python
from django.utils import timezone
```

- [ ] **Step 3: Ajouter Meta unique_together**

Remplacer la classe Meta existante :
```python
class Meta:
    ordering = ('-datetime_cloture',)
    verbose_name = _('Cash register closure')
    verbose_name_plural = _('Cash register closures')
```

Par :
```python
class Meta:
    ordering = ('-datetime_cloture',)
    unique_together = [('point_de_vente', 'numero_sequentiel', 'niveau')]
    verbose_name = _('Cash register closure')
    verbose_name_plural = _('Cash register closures')
```

- [ ] **Step 4: Générer et appliquer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name=cloture_enrichie
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
```

Expected: 0 issues, migration appliquée sur tous les schémas.

**Note importante :** Les clôtures existantes auront `numero_sequentiel=0` et `niveau='J'`. Le `unique_together` risque de poser problème si plusieurs clôtures existantes ont déjà le même PV et `numero_sequentiel=0`. Dans ce cas, il faut d'abord les numéroter via une migration de données.

Pour gérer cela proprement, créer une migration de données avant d'ajouter la contrainte unique :

1. D'abord créer la migration avec les champs SANS le unique_together
2. Puis une 2ème migration de données qui numérote les clôtures existantes
3. Puis une 3ème migration qui ajoute le unique_together

**Alternative plus simple (recommandée)** : puisqu'on est en développement et que les clôtures existantes sont des données de test, on peut faire une seule migration en s'assurant que `default=0` est acceptable. Mais le `unique_together` doit être ajouté séparément APRÈS la numérotation.

Approche concrète :
- Migration 0010 : ajouter les 4 champs SANS unique_together
- Migration 0011 : RunPython pour numéroter les clôtures existantes par PV
- Migration 0012 : ajouter le unique_together

Pour simplifier (données de test uniquement en dev), on peut tout faire en 2 migrations :
- 0010 : champs + numérotation des existantes
- On ne met PAS le unique_together dans Meta pour l'instant (le `select_for_update` suffit à garantir l'unicité en production)

**Décision : pas de `unique_together` en Meta.** Le `select_for_update` dans `cloturer()` garantit l'unicité en runtime. Le unique_together sera ajouté plus tard quand les données seront propres (session consolidation).

→ La Meta reste comme avant, sans `unique_together`. On fait UNE seule migration.

---

## Task 2: Adapter le ClotureSerializer

**Files:**
- Modify: `laboutik/serializers.py:231-253`

- [ ] **Step 1: Retirer `datetime_ouverture` du serializer**

Remplacer le `ClotureSerializer` :

```python
class ClotureSerializer(serializers.Serializer):
    """
    Valide les donnees de cloture de caisse.
    Validates cash register closure data.

    LOCALISATION : laboutik/serializers.py

    Utilise par CaisseViewSet.cloturer() (POST).
    Le datetime_ouverture est calcule automatiquement (1ere vente apres derniere cloture).
    Used by CaisseViewSet.cloturer() (POST).
    datetime_ouverture is computed automatically (1st sale after last closure).
    """
    uuid_pv = serializers.UUIDField(
        error_messages={
            'required': _("L'UUID du point de vente est requis"),
            'invalid': _("UUID du point de vente invalide"),
        },
    )
```

---

## Task 3: Réécrire `cloturer()` avec RapportComptableService

**Files:**
- Modify: `laboutik/views.py:901-1121`

C'est la tâche la plus importante. La vue `cloturer()` est réécrite pour :
1. Calculer `datetime_ouverture` automatiquement
2. Utiliser `RapportComptableService` au lieu du calcul inline
3. Calculer le numéro séquentiel avec `select_for_update`
4. Incrémenter le total perpétuel atomiquement avec `F()`
5. Stocker le `hash_lignes`

- [ ] **Step 1: Ajouter les imports nécessaires en haut de views.py**

Vérifier que ces imports existent, les ajouter sinon :
```python
from django.db import transaction
from django.db.models import F
from laboutik.reports import RapportComptableService
```

- [ ] **Step 2: Réécrire la méthode `cloturer()`**

Remplacer tout le corps de `cloturer()` (lignes ~902-1121) par :

```python
@action(detail=False, methods=["post"], url_path="cloturer", url_name="cloturer")
def cloturer(self, request):
    """
    POST /laboutik/caisse/cloturer/
    Cloture le service en cours : calcule les totaux via RapportComptableService,
    ferme les tables, cree le rapport.
    Closes the current service: calculates totals via RapportComptableService,
    closes tables, creates the report.

    LOCALISATION : laboutik/views.py

    FLUX / FLOW :
    1. Valider avec ClotureSerializer (uuid_pv uniquement)
    2. Calculer datetime_ouverture = 1ere vente apres derniere cloture J
    3. Appeler RapportComptableService.generer_rapport_complet()
    4. Numero sequentiel atomique (select_for_update)
    5. Total perpetuel atomique (F expression)
    6. Creer ClotureCaisse avec hash_lignes
    7. Fermer tables et commandes OPEN
    8. Retourner le rapport (template partial)
    """
    serializer = ClotureSerializer(data=request.data)
    if not serializer.is_valid():
        premiere_erreur = next(iter(serializer.errors.values()))[0]
        context_erreur = {
            "msg_type": "warning",
            "msg_content": str(premiere_erreur),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

    uuid_pv = serializer.validated_data["uuid_pv"]

    # --- Verifier que la carte primaire a acces au PV ---
    # --- Check that the primary card has access to the PV ---
    tag_id_carte_manager = request.POST.get("tag_id_cm", "")
    _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

    # Charger le point de vente / Load the point of sale
    try:
        point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
    except PointDeVente.DoesNotExist:
        context_erreur = {
            "msg_type": "warning",
            "msg_content": _("Point de vente introuvable"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

    # --- Calculer datetime_ouverture automatiquement ---
    # = datetime de la 1ere LigneArticle apres la derniere cloture J du PV
    # / = datetime of the 1st LigneArticle after the last daily closure of this POS
    derniere_cloture = ClotureCaisse.objects.filter(
        point_de_vente=point_de_vente,
        niveau=ClotureCaisse.JOURNALIERE,
    ).order_by('-datetime_cloture').first()

    if derniere_cloture:
        datetime_ouverture = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gt=derniere_cloture.datetime_cloture,
            status=LigneArticle.VALID,
        ).order_by('datetime').values_list('datetime', flat=True).first()
    else:
        datetime_ouverture = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            status=LigneArticle.VALID,
        ).order_by('datetime').values_list('datetime', flat=True).first()

    if not datetime_ouverture:
        context_erreur = {
            "msg_type": "warning",
            "msg_content": _("Aucune vente à clôturer"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

    # --- Calculer le rapport via RapportComptableService ---
    # --- Calculate the report via RapportComptableService ---
    datetime_cloture = timezone.now()
    service = RapportComptableService(point_de_vente, datetime_ouverture, datetime_cloture)
    rapport = service.generer_rapport_complet()
    totaux = rapport['totaux_par_moyen']
    hash_lignes = service.calculer_hash_lignes()

    # --- Numero sequentiel + total perpetuel + creation (atomique) ---
    # --- Sequential number + perpetual total + creation (atomic) ---
    with transaction.atomic():
        # Numero sequentiel : select_for_update pour eviter les doublons
        # / Sequential number: select_for_update to prevent duplicates
        dernier = ClotureCaisse.objects.select_for_update().filter(
            point_de_vente=point_de_vente,
            niveau=ClotureCaisse.JOURNALIERE,
        ).order_by('-numero_sequentiel').first()
        dernier_num = dernier.numero_sequentiel if dernier else 0

        # Total perpetuel : F() pour eviter les race conditions
        # / Perpetual total: F() to prevent race conditions
        LaboutikConfiguration.objects.filter(
            pk=LaboutikConfiguration.get_solo().pk,
        ).update(
            total_perpetuel=F('total_perpetuel') + totaux['total'],
        )
        config = LaboutikConfiguration.get_solo()
        config.refresh_from_db()

        cloture = ClotureCaisse.objects.create(
            point_de_vente=point_de_vente,
            responsable=request.user if request.user.is_authenticated else None,
            datetime_ouverture=datetime_ouverture,
            datetime_cloture=datetime_cloture,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=dernier_num + 1,
            total_especes=totaux['especes'],
            total_carte_bancaire=totaux['carte_bancaire'],
            total_cashless=totaux['cashless'],
            total_general=totaux['total'],
            nombre_transactions=service.lignes.count(),
            rapport_json=rapport,
            hash_lignes=hash_lignes,
            total_perpetuel=config.total_perpetuel,
        )

    # --- Fermer les tables ouvertes (OCCUPEE ou SERVIE → LIBRE) ---
    # --- Close open tables (OCCUPIED or SERVED → FREE) ---
    Table.objects.filter(
        statut__in=[Table.OCCUPEE, Table.SERVIE],
    ).update(statut=Table.LIBRE)

    # --- Annuler les commandes encore ouvertes ---
    # --- Cancel still-open orders ---
    CommandeSauvegarde.objects.filter(
        statut=CommandeSauvegarde.OPEN,
    ).update(statut=CommandeSauvegarde.CANCEL)

    logger.info(
        f"Cloture caisse: PV={point_de_vente.name}, "
        f"niveau=J, seq={cloture.numero_sequentiel}, "
        f"total={totaux['total']}cts, perpetuel={config.total_perpetuel}cts"
    )

    # --- Convertir la TVA en euros pour l'affichage ---
    # --- Convert VAT to euros for display ---
    rapport_tva_euros = {}
    for taux_label, tva_data in rapport.get('tva', {}).items():
        rapport_tva_euros[taux_label] = {
            "total_ht_euros": f"{tva_data['total_ht'] / 100:.2f}",
            "total_tva_euros": f"{tva_data['total_tva'] / 100:.2f}",
            "total_ttc_euros": f"{tva_data['total_ttc'] / 100:.2f}",
        }

    # --- Retourner le rapport ---
    # --- Return the report ---
    context = {
        "cloture": cloture,
        "rapport": rapport,
        "rapport_tva_euros": rapport_tva_euros,
        "total_especes_euros": totaux['especes'] / 100,
        "total_cb_euros": totaux['carte_bancaire'] / 100,
        "total_nfc_euros": totaux['cashless'] / 100,
        "total_general_euros": totaux['total'] / 100,
        "nombre_transactions": service.lignes.count(),
        "currency_data": CURRENCY_DATA,
    }
    return render(request, "laboutik/partial/hx_cloture_rapport.html", context)
```

- [ ] **Step 3: Vérifier les imports en haut de views.py**

S'assurer que ces imports existent :
```python
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from laboutik.reports import RapportComptableService
```

Le `Sum` était déjà utilisé. `transaction` et `F` sont peut-être nouveaux.

---

## Task 4: Mettre à jour `ligne_couverte_par_cloture()` dans integrity.py

**Files:**
- Modify: `laboutik/integrity.py:168-183`

- [ ] **Step 1: Ajouter le filtre `niveau='J'` à la garde**

La garde ne doit vérifier que les clôtures journalières (les M/A sont des agrégats, pas des périodes de vente).

Remplacer :
```python
def ligne_couverte_par_cloture(ligne):
    """
    Verifie si une LigneArticle est couverte par une cloture existante.
    Retourne la ClotureCaisse si oui, None sinon.
    Utilisee comme garde pour interdire les corrections post-cloture.
    / Checks if a LigneArticle is covered by an existing closure.
    Returns the ClotureCaisse if yes, None otherwise.
    Used as a guard to prevent post-closure corrections.

    LOCALISATION : laboutik/integrity.py
    """
    from laboutik.models import ClotureCaisse
    return ClotureCaisse.objects.filter(
        datetime_ouverture__lte=ligne.datetime,
        datetime_cloture__gte=ligne.datetime,
    ).first()
```

Par :
```python
def ligne_couverte_par_cloture(ligne):
    """
    Verifie si une LigneArticle est couverte par une cloture journaliere existante.
    Retourne la ClotureCaisse si oui, None sinon.
    Utilisee comme garde pour interdire les corrections post-cloture.
    Seules les clotures J sont verifiees (M/A sont des agregats, pas des periodes).
    / Checks if a LigneArticle is covered by an existing daily closure.
    Returns the ClotureCaisse if yes, None otherwise.
    Used as a guard to prevent post-closure corrections.
    Only daily closures are checked (M/A are aggregates, not periods).

    LOCALISATION : laboutik/integrity.py
    """
    from laboutik.models import ClotureCaisse
    return ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.JOURNALIERE,
        datetime_ouverture__lte=ligne.datetime,
        datetime_cloture__gte=ligne.datetime,
    ).first()
```

---

## Task 5: Tâches Celery Beat — Clôtures M/A

**Files:**
- Modify: `laboutik/tasks.py`
- Modify: `TiBillet/celery.py`

- [ ] **Step 1: Ajouter les tâches M/A dans laboutik/tasks.py**

Ajouter à la fin du fichier :

```python
@shared_task
def generer_cloture_mensuelle():
    """
    Generee le 1er de chaque mois pour le mois precedent.
    Itere sur les tenants actifs avec module_caisse.
    Pour chaque PV, agrege les clotures J du mois precedent.
    / Generated on the 1st of each month for the previous month.
    Iterates over active tenants with module_caisse.
    For each POS, aggregates daily closures from the previous month.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from Customers.models import Client

    # Mois precedent / Previous month
    aujourd_hui = date.today()
    premier_jour_mois_courant = aujourd_hui.replace(day=1)
    premier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(months=1)
    dernier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(days=1)

    logger.info(
        f"Cloture mensuelle: {premier_jour_mois_precedent} → {dernier_jour_mois_precedent}"
    )

    # Iterer sur les tenants actifs / Iterate over active tenants
    tenants = Client.objects.exclude(schema_name='public')
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                _generer_cloture_agregee(
                    niveau='M',
                    niveau_source='J',
                    date_debut=premier_jour_mois_precedent,
                    date_fin=dernier_jour_mois_precedent,
                )
        except Exception as e:
            logger.exception(
                f"Erreur cloture mensuelle tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_annuelle():
    """
    Generee le 1er janvier pour l'annee precedente.
    Itere sur les tenants actifs avec module_caisse.
    Pour chaque PV, agrege les clotures M de l'annee precedente.
    / Generated on January 1st for the previous year.
    Iterates over active tenants with module_caisse.
    For each POS, aggregates monthly closures from the previous year.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import date
    from Customers.models import Client

    annee_precedente = date.today().year - 1
    date_debut = date(annee_precedente, 1, 1)
    date_fin = date(annee_precedente, 12, 31)

    logger.info(f"Cloture annuelle: {date_debut} → {date_fin}")

    tenants = Client.objects.exclude(schema_name='public')
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                _generer_cloture_agregee(
                    niveau='A',
                    niveau_source='M',
                    date_debut=date_debut,
                    date_fin=date_fin,
                )
        except Exception as e:
            logger.exception(
                f"Erreur cloture annuelle tenant {tenant.schema_name}: {e}"
            )


def _generer_cloture_agregee(niveau, niveau_source, date_debut, date_fin):
    """
    Fonction utilitaire : agrege les clotures d'un niveau inferieur
    pour creer une cloture de niveau superieur, par PV.
    / Utility: aggregates lower-level closures to create a higher-level closure, per POS.

    LOCALISATION : laboutik/tasks.py

    :param niveau: 'M' ou 'A' — le niveau de la cloture a creer
    :param niveau_source: 'J' ou 'M' — le niveau des clotures a agreger
    :param date_debut: date de debut de la periode (date, pas datetime)
    :param date_fin: date de fin de la periode (date, pas datetime)
    """
    from django.db import transaction
    from django.db.models import Sum, Min, Max
    from django.utils import timezone as tz
    import datetime

    from BaseBillet.models import Configuration
    from laboutik.models import ClotureCaisse, PointDeVente, LaboutikConfiguration

    # Verifier que le module caisse est actif / Check module_caisse is active
    config_base = Configuration.get_solo()
    if not config_base.module_caisse:
        return

    # Convertir dates en datetime aware / Convert dates to aware datetimes
    dt_debut = tz.make_aware(datetime.datetime.combine(date_debut, datetime.time.min))
    dt_fin = tz.make_aware(datetime.datetime.combine(date_fin, datetime.time.max))

    # Pour chaque PV qui a des clotures source dans la periode
    # / For each POS that has source closures in the period
    pvs_avec_clotures = ClotureCaisse.objects.filter(
        niveau=niveau_source,
        datetime_cloture__gte=dt_debut,
        datetime_cloture__lte=dt_fin,
    ).values_list('point_de_vente', flat=True).distinct()

    for pv_uuid in pvs_avec_clotures:
        point_de_vente = PointDeVente.objects.get(uuid=pv_uuid)

        # Agreger les clotures source / Aggregate source closures
        clotures_source = ClotureCaisse.objects.filter(
            point_de_vente=point_de_vente,
            niveau=niveau_source,
            datetime_cloture__gte=dt_debut,
            datetime_cloture__lte=dt_fin,
        )

        if not clotures_source.exists():
            continue

        aggregats = clotures_source.aggregate(
            total_especes=Sum('total_especes'),
            total_carte_bancaire=Sum('total_carte_bancaire'),
            total_cashless=Sum('total_cashless'),
            total_general=Sum('total_general'),
            nombre_transactions=Sum('nombre_transactions'),
            premiere_ouverture=Min('datetime_ouverture'),
            derniere_cloture=Max('datetime_cloture'),
        )

        with transaction.atomic():
            # Numero sequentiel atomique / Atomic sequential number
            dernier = ClotureCaisse.objects.select_for_update().filter(
                point_de_vente=point_de_vente,
                niveau=niveau,
            ).order_by('-numero_sequentiel').first()
            dernier_num = dernier.numero_sequentiel if dernier else 0

            config = LaboutikConfiguration.get_solo()

            ClotureCaisse.objects.create(
                point_de_vente=point_de_vente,
                responsable=None,
                datetime_ouverture=aggregats['premiere_ouverture'],
                datetime_cloture=aggregats['derniere_cloture'],
                niveau=niveau,
                numero_sequentiel=dernier_num + 1,
                total_especes=aggregats['total_especes'] or 0,
                total_carte_bancaire=aggregats['total_carte_bancaire'] or 0,
                total_cashless=aggregats['total_cashless'] or 0,
                total_general=aggregats['total_general'] or 0,
                nombre_transactions=aggregats['nombre_transactions'] or 0,
                rapport_json={
                    "type": f"cloture_{niveau}",
                    "periode": f"{date_debut} → {date_fin}",
                    "nb_clotures_source": clotures_source.count(),
                },
                hash_lignes='',
                total_perpetuel=config.total_perpetuel,
            )

        logger.info(
            f"Cloture {niveau} creee: PV={point_de_vente.name}, "
            f"seq={dernier_num + 1}, total={aggregats['total_general']}cts"
        )
```

- [ ] **Step 2: Enregistrer les tâches dans Celery Beat**

Dans `TiBillet/celery.py`, ajouter les 2 tâches périodiques dans `setup_periodic_tasks()` :

```python
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    logger.info(f'setup_periodic_tasks cron_morning at 5AM UTC')
    sender.add_periodic_task(
        crontab(hour=5, minute=0),
        cron_morning.s(),
    )

    # Cloture mensuelle : le 1er de chaque mois a 3h UTC
    # / Monthly closure: 1st of each month at 3am UTC
    logger.info(f'setup_periodic_tasks cloture_mensuelle at 3AM UTC, 1st of month')
    sender.add_periodic_task(
        crontab(day_of_month=1, hour=3, minute=0),
        cloture_mensuelle_task.s(),
    )

    # Cloture annuelle : le 1er janvier a 4h UTC
    # / Annual closure: January 1st at 4am UTC
    logger.info(f'setup_periodic_tasks cloture_annuelle at 4AM UTC, Jan 1st')
    sender.add_periodic_task(
        crontab(month_of_year=1, day_of_month=1, hour=4, minute=0),
        cloture_annuelle_task.s(),
    )

    logger.info(f'setup_periodic_tasks DONE')
```

Et ajouter les tâches proxy (nécessaires car les `@shared_task` sont dans `laboutik/tasks.py` et Celery Beat a besoin de les appeler) :

```python
@app.task
def cloture_mensuelle_task():
    from laboutik.tasks import generer_cloture_mensuelle
    generer_cloture_mensuelle()

@app.task
def cloture_annuelle_task():
    from laboutik.tasks import generer_cloture_annuelle
    generer_cloture_annuelle()
```

**Alternative plus simple :** importer directement les tâches dans celery.py et les utiliser dans `add_periodic_task`. Mais attention aux imports circulaires au démarrage de Celery. Le pattern proxy est plus sûr.

- [ ] **Step 3: Vérifier que `python-dateutil` est disponible**

```bash
docker exec lespass_django poetry run python -c "from dateutil.relativedelta import relativedelta; print('OK')"
```

Si erreur : `docker exec lespass_django poetry add python-dateutil`. Normalement déjà présent (dépendance de Django).

---

## Task 6: Enrichir ClotureCaisseAdmin

**Files:**
- Modify: `Administration/admin/laboutik.py:327-353`

- [ ] **Step 1: Enrichir l'admin avec les nouveaux champs**

Remplacer `ClotureCaisseAdmin` :

```python
@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """Admin lecture seule pour les clotures de caisse.
    Document comptable immuable — aucune modification possible.
    Read-only admin for cash register closures.
    Immutable accounting document — no modification allowed.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = (
        'point_de_vente', 'niveau', 'numero_sequentiel',
        'responsable', 'datetime_cloture',
        'total_general', 'total_perpetuel',
        'nombre_transactions', 'badge_integrite',
    )
    list_filter = ['point_de_vente', 'niveau']
    search_fields = ['point_de_vente__name', 'responsable__email']
    ordering = ('-datetime_cloture',)
    readonly_fields = (
        'uuid', 'point_de_vente', 'responsable',
        'datetime_ouverture', 'datetime_cloture',
        'niveau', 'numero_sequentiel',
        'total_especes', 'total_carte_bancaire', 'total_cashless',
        'total_general', 'total_perpetuel',
        'nombre_transactions', 'hash_lignes', 'rapport_json',
    )

    fieldsets = (
        (_('Identification'), {
            'fields': (
                'uuid', 'point_de_vente', 'responsable',
                'niveau', 'numero_sequentiel',
            ),
        }),
        (_('Period'), {
            'fields': (
                'datetime_ouverture', 'datetime_cloture',
            ),
        }),
        (_('Totals (cents)'), {
            'fields': (
                'total_especes', 'total_carte_bancaire', 'total_cashless',
                'total_general', 'total_perpetuel',
            ),
        }),
        (_('Details'), {
            'fields': (
                'nombre_transactions', 'hash_lignes', 'rapport_json',
            ),
        }),
    )

    @admin.display(description=_("Integrity"))
    def badge_integrite(self, obj):
        """
        Badge vert si hash_lignes est present, rouge si vide (clotures anciennes).
        Pour les clotures M/A, le hash n'est pas applicable.
        / Green badge if hash_lignes present, red if empty.
        For M/A closures, hash is not applicable.
        """
        from django.utils.html import format_html
        if obj.niveau != ClotureCaisse.JOURNALIERE:
            return format_html('<span style="color: gray;">—</span>')
        if obj.hash_lignes:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: orange;">—</span>')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

---

## Task 7: Adapter les tests existants

**Files:**
- Modify: `tests/pytest/test_cloture_caisse.py`

Les 7 tests existants envoient `datetime_ouverture` dans le POST. Il faut retirer ce champ du payload puisque c'est maintenant calculé automatiquement.

- [ ] **Step 1: Adapter les tests**

Dans `test_cloture_caisse.py`, pour chaque test qui fait un POST vers `/laboutik/caisse/cloturer/`, remplacer le `post_data` :

**Avant** (dans chaque test) :
```python
post_data = {
    'datetime_ouverture': datetime_ouverture.isoformat(),
    'uuid_pv': str(premier_pv.uuid),
}
```

**Après** :
```python
post_data = {
    'uuid_pv': str(premier_pv.uuid),
}
```

Les tests suivants sont concernés (7 classes, chacune avec 1 test) :
1. `TestClotureTotauxCorrects.test_cloture_totaux_corrects`
2. `TestClotureNombreTransactions.test_cloture_nombre_transactions`
3. `TestClotureFermeTables.test_cloture_ferme_tables`
4. `TestClotureRapportJSON.test_cloture_rapport_json_complet`
5. `TestClotureFiltreDatetime.test_cloture_filtre_par_datetime`
6. `TestDoubleClotureMmePeriode.test_double_cloture_meme_periode`
7. `TestClotureAnnuleCommandes.test_cloture_annule_commandes_ouvertes`

**Important — test_cloture_rapport_json_complet :** Ce test vérifie les clés `par_categorie`, `par_produit`, `par_moyen_paiement`, `par_tva`, `commandes`. Le rapport JSON du `RapportComptableService` utilise des clés différentes :
- `totaux_par_moyen` (au lieu de `par_moyen_paiement`)
- `detail_ventes` (au lieu de `par_produit`)
- `tva` (au lieu de `par_tva`)
- Pas de clé `commandes` ni `par_categorie` ni `par_produit`

→ Il faut adapter les assertions de `test_cloture_rapport_json_complet` aux nouvelles clés du `RapportComptableService.generer_rapport_complet()` :

```python
rapport = cloture.rapport_json
# Les 13 cles du RapportComptableService
assert 'totaux_par_moyen' in rapport
assert 'detail_ventes' in rapport
assert 'tva' in rapport
assert 'solde_caisse' in rapport
assert 'recharges' in rapport
assert 'adhesions' in rapport
assert 'remboursements' in rapport
assert 'habitus' in rapport
assert 'billets' in rapport
assert 'synthese_operations' in rapport
assert 'operateurs' in rapport
assert 'ventilation_par_pv' in rapport
assert 'infos_legales' in rapport

# Structure totaux_par_moyen
totaux = rapport['totaux_par_moyen']
assert 'especes' in totaux
assert 'carte_bancaire' in totaux
assert 'cashless' in totaux

# Structure TVA
tva = rapport['tva']
assert isinstance(tva, dict)
for cle_taux, donnees_tva in tva.items():
    assert 'taux' in donnees_tva
    assert 'total_ttc' in donnees_tva
    assert 'total_ht' in donnees_tva
    assert 'total_tva' in donnees_tva
```

- [ ] **Step 2: Lancer les tests existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_caisse.py -v
```

Expected: 7 tests PASS.

---

## Task 8: Écrire les nouveaux tests

**Files:**
- Create: `tests/pytest/test_cloture_enrichie.py`

- [ ] **Step 1: Écrire les 7 tests**

```python
"""
tests/pytest/test_cloture_enrichie.py — Tests Session 13 : clotures enrichies.
tests/pytest/test_cloture_enrichie.py — Tests Session 13: enriched closures.

Couvre : niveau, numero_sequentiel, total_perpetuel, hash_lignes,
         datetime_ouverture auto, cloture M, garde correction post-cloture.
Covers: level, sequential number, perpetual total, lines hash,
        auto datetime_ouverture, monthly closure, post-closure correction guard.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_cloture_enrichie.py -v
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest

from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, ClotureCaisse, LaboutikConfiguration,
)
from laboutik.integrity import ligne_couverte_par_cloture


# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
        email = 'admin-test-cloture-enrichie@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(premier_pv):
    """Premier produit du PV avec son prix.
    / First product of the PV with its price."""
    with schema_context(TENANT_SCHEMA):
        produit = premier_pv.products.filter(
            methode_caisse__isnull=False,
        ).first()
        prix = Price.objects.filter(
            product=produit,
            publish=True,
            asset__isnull=True,
        ).order_by('order').first()
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, dt=None, pv=None):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Creates a LigneArticle directly in DB (without going through the view).
    """
    product_sold, _ = ProductSold.objects.get_or_create(
        product=produit,
        event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=1,
        amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK,
        payment_method=payment_method_code,
        status=LigneArticle.VALID,
        point_de_vente=pv,
    )
    if dt is not None:
        LigneArticle.objects.filter(pk=ligne.pk).update(datetime=dt)
        ligne.refresh_from_db()
    return ligne


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestClotureNumeroSequentiel:
    """Verifie que 2 clotures J ont des numeros sequentiels 1 et 2.
    / Verify that 2 daily closures have sequential numbers 1 and 2."""

    def test_cloture_journal_numero_sequentiel(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Nettoyer les clotures existantes pour ce PV (test isole)
            # / Clean existing closures for this POS (isolated test)
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()

            # Creer une vente et cloturer / Create a sale and close
            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            # Premiere cloture : seq = 1
            cloture1 = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture1.numero_sequentiel == 1
            assert cloture1.niveau == ClotureCaisse.JOURNALIERE

            # Creer une autre vente et cloturer / Create another sale and close
            _creer_ligne_article_directe(produit, prix, 300, PaymentMethod.CC, pv=premier_pv)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            # Deuxieme cloture : seq = 2
            cloture2 = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture2.numero_sequentiel == 2


@pytest.mark.usefixtures("test_data")
class TestClotureTotalPerpetuel:
    """Verifie que le total perpetuel s'incremente correctement.
    / Verify that the perpetual total increments correctly."""

    def test_cloture_journal_total_perpetuel(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Reset le total perpetuel / Reset perpetual total
            config = LaboutikConfiguration.get_solo()
            config.total_perpetuel = 0
            config.save(update_fields=['total_perpetuel'])
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()

            # Cloture 1 : 5000 centimes
            _creer_ligne_article_directe(produit, prix, 5000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture1 = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture1.total_perpetuel == 5000

            # Cloture 2 : 3000 centimes
            _creer_ligne_article_directe(produit, prix, 3000, PaymentMethod.CC, pv=premier_pv)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture2 = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture2.total_perpetuel == 8000

            # Verifier la config aussi / Verify config too
            config.refresh_from_db()
            assert config.total_perpetuel == 8000


@pytest.mark.usefixtures("test_data")
class TestClotureMensuelle:
    """Verifie qu'une cloture M agrege les J du mois.
    / Verify that a monthly closure aggregates daily closures."""

    def test_cloture_mensuelle(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            from laboutik.tasks import _generer_cloture_agregee
            from datetime import date

            produit, prix = premier_produit_et_prix

            # Nettoyer / Clean
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()
            config = LaboutikConfiguration.get_solo()
            config.total_perpetuel = 0
            config.save(update_fields=['total_perpetuel'])

            # Creer 2 clotures J manuellement / Create 2 daily closures manually
            _creer_ligne_article_directe(produit, prix, 2000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            _creer_ligne_article_directe(produit, prix, 3000, PaymentMethod.CC, pv=premier_pv)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            # Generer la cloture M pour ce mois / Generate monthly closure for this month
            aujourd_hui = date.today()
            _generer_cloture_agregee(
                niveau='M',
                niveau_source='J',
                date_debut=aujourd_hui.replace(day=1),
                date_fin=aujourd_hui,
            )

            # Verifier la cloture M / Verify monthly closure
            cloture_m = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv,
                niveau=ClotureCaisse.MENSUELLE,
            ).first()
            assert cloture_m is not None
            assert cloture_m.numero_sequentiel == 1
            assert cloture_m.total_general == 5000
            assert cloture_m.nombre_transactions == 2


@pytest.mark.usefixtures("test_data")
class TestDatetimeOuvertureAuto:
    """Verifie que datetime_ouverture = datetime de la 1ere vente apres derniere cloture.
    / Verify datetime_ouverture = datetime of 1st sale after last closure."""

    def test_datetime_ouverture_auto(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Nettoyer / Clean
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()
            config = LaboutikConfiguration.get_solo()
            config.total_perpetuel = 0
            config.save(update_fields=['total_perpetuel'])

            # Creer une vente et cloturer / Create a sale and close
            _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            # Creer une nouvelle vente (apres cloture) / Create a new sale (after closure)
            ligne = _creer_ligne_article_directe(produit, prix, 2000, PaymentMethod.CC, pv=premier_pv)

            # Cloturer a nouveau / Close again
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            # La 2eme cloture doit avoir datetime_ouverture = datetime de la ligne
            cloture = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()

            # datetime_ouverture doit etre >= datetime de la ligne (pas de la 1ere cloture)
            # / datetime_ouverture must be >= line datetime (not from 1st closure)
            assert cloture.datetime_ouverture is not None
            # Le datetime_ouverture doit etre apres la 1ere cloture
            premiere_cloture = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('numero_sequentiel').first()
            assert cloture.datetime_ouverture > premiere_cloture.datetime_cloture


@pytest.mark.usefixtures("test_data")
class TestPasDeVentePasDeCloture:
    """Verifie que cloturer() retourne 400 s'il n'y a aucune vente a cloturer.
    / Verify cloturer() returns 400 if there are no sales to close."""

    def test_pas_de_vente_pas_de_cloture(
        self, admin_user, tenant, premier_pv,
    ):
        with schema_context(TENANT_SCHEMA):
            # S'assurer qu'il y a une cloture recente qui couvre toutes les ventes
            # Pour ca, on verifie que rien n'est a cloturer
            # D'abord, cloturer tout ce qui traine
            client = _make_client(admin_user, tenant)
            # Tenter de cloturer (peut reussir s'il y a des ventes)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            # Maintenant, tenter a nouveau : pas de vente depuis la derniere cloture
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 400


@pytest.mark.usefixtures("test_data")
class TestGardeCorrectionPostCloture:
    """Verifie que ligne_couverte_par_cloture() retourne la cloture.
    / Verify that ligne_couverte_par_cloture() returns the closure."""

    def test_garde_correction_post_cloture(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Nettoyer / Clean
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()
            config = LaboutikConfiguration.get_solo()
            config.total_perpetuel = 0
            config.save(update_fields=['total_perpetuel'])

            # Creer une vente / Create a sale
            ligne = _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)

            # Pas encore de cloture → ligne NON couverte
            assert ligne_couverte_par_cloture(ligne) is None

            # Cloturer / Close
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            # Maintenant la ligne EST couverte par la cloture
            ligne.refresh_from_db()
            cloture_trouvee = ligne_couverte_par_cloture(ligne)
            assert cloture_trouvee is not None
            assert cloture_trouvee.point_de_vente == premier_pv


@pytest.mark.usefixtures("test_data")
class TestRapportJson13Cles:
    """Verifie que le rapport JSON stocke a bien 13 sections.
    / Verify that the stored JSON report has 13 sections."""

    def test_rapport_json_13_cles(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Nettoyer / Clean
            ClotureCaisse.objects.filter(point_de_vente=premier_pv).delete()
            config = LaboutikConfiguration.get_solo()
            config.total_perpetuel = 0
            config.save(update_fields=['total_perpetuel'])

            # Creer une vente et cloturer / Create a sale and close
            _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture = ClotureCaisse.objects.filter(
                point_de_vente=premier_pv, niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            rapport = cloture.rapport_json

            # 13 cles attendues du RapportComptableService
            cles_attendues = [
                'totaux_par_moyen', 'detail_ventes', 'tva', 'solde_caisse',
                'recharges', 'adhesions', 'remboursements', 'habitus',
                'billets', 'synthese_operations', 'operateurs',
                'ventilation_par_pv', 'infos_legales',
            ]
            for cle in cles_attendues:
                assert cle in rapport, f"Cle manquante dans rapport_json: {cle}"

            assert len(rapport) == 13
```

- [ ] **Step 2: Lancer les nouveaux tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_enrichie.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 3: Lancer tous les tests laboutik**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

Expected: 0 régression.

---

## Task 9: Vérification finale

- [ ] **Step 1: Vérifier les migrations et le check Django**

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 2: Lancer tous les tests pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v
```

Expected: 276 + 7 = ~283 tests, 0 fail.

---

## Résumé des critères de succès

- [ ] ClotureCaisse enrichi (niveau, numero_sequentiel, total_perpetuel, hash_lignes)
- [ ] datetime_cloture : `default=timezone.now` (plus `auto_now_add`)
- [ ] datetime_ouverture calculé automatiquement
- [ ] cloturer() utilise RapportComptableService
- [ ] Numéro séquentiel protégé par select_for_update
- [ ] Total perpétuel incrémenté atomiquement avec F(), jamais remis à 0
- [ ] Clôtures M/A automatiques (Celery Beat tasks)
- [ ] Garde correction post-clôture prête (avec filtre niveau='J')
- [ ] Admin Unfold enrichi avec badge intégrité
- [ ] 7+ tests pytest verts (test_cloture_enrichie.py)
- [ ] Tous les tests existants passent (0 régression)
