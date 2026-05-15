# Plan d'implémentation — S2 (Chantier 01 / App `comptabilite`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.
>
> **Hub :** [`INDEX.md`](INDEX.md) — **Spec :** [`SPEC.md`](SPEC.md) §3-4-7-9
>
> **Garde-fous projet (rappel maintainer) :**
> - **JAMAIS d'opération `git`** (commit/add/push/checkout--/stash/reset/clean). Output suggested commit at the end.
> - **Pas de `runserver_plus`** — serveur byobu sur port 8002.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs (`services.py`, `tasks.py`, `management/commands/generer_cloture.py`, `test_comptabilite_service.py`).

**Goal :** Implémenter le service `RapportComptableService` (queryset, 8 méthodes `calculer_*`, `generer_rapport_complet`, `calculer_hash_lignes`), la tâche Celery `generer_cloture_pour_tenant`, et la management command `generer_cloture`. À la fin de S2 : `manage.py generer_cloture --niveau=J --tenant=lespass` crée une `ClotureCaisse` en base avec un `rapport_json` valide.

**Architecture :**
- Service stateless instancié sur `(datetime_debut, datetime_fin)` → retourne un dict prêt à stocker.
- Queryset de base : `LigneArticle.objects.filter(datetime__range, status IN [V,P,F,N]).exclude(sale_origin=LABOUTIK)`
- Tâche Celery + management command appellent le service dans un `tenant_context`, gèrent numéro séquentiel + hash + total perpétuel, créent la `ClotureCaisse`.

**Tech Stack :** Django ORM (Sum/Count/F/Q/Coalesce), Celery shared_task, multi-tenant via `django_tenants.utils.tenant_context`, hashlib SHA-256, pytest avec live dev DB pattern (même conftest pattern que S1).

---

## File structure produite par S2

```
comptabilite/
├── services.py                                       # nouveau (RapportComptableService)
├── tasks.py                                          # nouveau (Celery + helpers _bornes/_numero/_perpetuel)
└── management/
    ├── __init__.py                                   # nouveau (vide)
    └── commands/
        ├── __init__.py                               # nouveau (vide)
        └── generer_cloture.py                        # nouveau (BaseCommand)

tests/pytest/
└── test_comptabilite_service.py                      # nouveau (tests service + tâche)
```

Pas de modification de modèle, de migration, ni de fichier existant en dehors de `tests/pytest/`.

---

## Découpage en 4 blocs subagent

| Bloc | Tasks | Modèle | Sortie |
|---|---|---|---|
| **B1** | Squelette service + `_base_queryset` + `calculer_totaux_par_moyen` + tests TDD (RED→GREEN) | sonnet | Service utilisable pour 1 section |
| **B2** | 5 méthodes : `calculer_tva`, `calculer_remboursements`, `calculer_adhesions`, `calculer_billets`, `calculer_detail_ventes` + tests | sonnet | 6/8 sections du rapport calculables |
| **B3** | 2 dernières méthodes : `calculer_synthese_operations`, `calculer_infos_legales` + `calculer_hash_lignes` + `generer_rapport_complet` + tests | sonnet | Service complet, dict prêt à stocker |
| **B4** | `tasks.py` + management command + test E2E (génération clôture en base) | sonnet | `manage.py generer_cloture --niveau=J` produit une ClotureCaisse |

---

## Bloc B1 — Squelette service + totaux par moyen de paiement (TDD)

**Files :**
- Create: `comptabilite/services.py`
- Create: `tests/pytest/test_comptabilite_service.py`

### Tests à écrire (TDD RED)

Réutiliser le pattern « live dev DB » avec `django_db_setup` + `_enable_db_access` fixtures (cf. `test_comptabilite_admin.py`).

Tests à ajouter dans `test_comptabilite_service.py` :

1. **`test_service_instanciation_ok`** : on peut instancier `RapportComptableService(debut, fin)` ; `service.queryset` est un QuerySet sur `LigneArticle`.
2. **`test_base_queryset_filtre_status`** : sur 4 LigneArticle créées en fixture (status V, P, U, C), seules V et P entrent dans le queryset (et F si présent).
3. **`test_base_queryset_exclut_laboutik`** : une ligne avec `sale_origin=SaleOrigin.LABOUTIK` est exclue.
4. **`test_calculer_totaux_par_moyen_basique`** : 3 lignes (CASH 1000c, CC 2000c, STRIPE_FED 500c) → retourne un dict avec ces 3 clés (`CASH`, `CC`, `STRIPE_FED`), montants et `nb`, plus `total=3500` et `currency_code="EUR"`.
5. **`test_calculer_totaux_par_moyen_avec_qty_decimal`** : ligne CASH amount=1000c qty=2 → total=2000c (test que `Sum(F('amount')*F('qty'))` est utilisé, pas `Sum('amount')` seul).

### Implémentation (GREEN)

Squelette `comptabilite/services.py` :

```python
"""
Service de calcul des rapports comptables — app comptabilite V1.
/ Accounting report calculation service — comptabilite app V1.

LOCALISATION : comptabilite/services.py

Adapte de laboutik/reports.py (V2) pour le perimetre V1 :
- Reservations evenements + adhesions uniquement
- Pas de POS (LaBoutik), pas de stats NFC/Fedow
- Pas de fond de caisse, pas de recharges cashless

Tous les montants sont en CENTIMES (int). Jamais de float.
/ All amounts are in CENTS (int). Never float.
"""
import hashlib
import logging
from decimal import Decimal

from django.db import connection
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)


class RapportComptableService:
    """
    Calcule un rapport comptable agrege pour une periode.
    / Calculates an aggregated accounting report for a period.
    """

    def __init__(self, datetime_debut, datetime_fin):
        self.datetime_debut = datetime_debut
        self.datetime_fin = datetime_fin
        self.queryset = self._base_queryset()

    def _base_queryset(self):
        """
        Queryset de base : lignes eligibles pour la cloture comptable V1.
        Exclut LABOUTIK (POS), garde V/P/F/N.
        / Base queryset: lines eligible for the V1 accounting closure.
        """
        from BaseBillet.models import LigneArticle, SaleOrigin
        return LigneArticle.objects.filter(
            datetime__gte=self.datetime_debut,
            datetime__lt=self.datetime_fin,
            status__in=[
                LigneArticle.VALID,
                LigneArticle.PAID,
                LigneArticle.FREERES,
                LigneArticle.CREDIT_NOTE,
            ],
        ).exclude(sale_origin=SaleOrigin.LABOUTIK).select_related(
            "pricesold__productsold__product",
            "reservation__event",
            "membership__price",
        )

    def calculer_totaux_par_moyen(self) -> dict:
        """
        Totaux par PaymentMethod (12 valeurs possibles).
        / Totals per PaymentMethod (12 possible values).

        Calcule total = Sum(amount * qty) car amount est unitaire (centimes),
        qty est decimal. Convertion finale en int.
        """
        from BaseBillet.models import PaymentMethod

        agrege = (
            self.queryset
            .values("payment_method")
            .annotate(
                total_decimal=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
                nb=Count("pk"),
            )
        )

        resultats = {}
        total_global = 0
        labels = dict(PaymentMethod.choices)

        for ligne in agrege:
            code = ligne["payment_method"] or PaymentMethod.UNKNOWN
            total_centimes = int(ligne["total_decimal"])
            resultats[code] = {
                "label": str(labels.get(code, code)),
                "total": total_centimes,
                "nb": ligne["nb"],
            }
            total_global += total_centimes

        resultats["total"] = total_global
        resultats["currency_code"] = "EUR"
        return resultats
```

Note technique : `Sum(F("amount") * F("qty"))` renvoie un Decimal (car qty est Decimal). On caste en int après pour rester en centimes.

### Acceptance

- [ ] 5 tests passent (en plus des 5 de S1 : 10 total)
- [ ] `manage.py check` OK
- [ ] Code commenté FR+EN selon djc.md

---

## Bloc B2 — 5 méthodes calculer (TVA, Remboursements, Adhésions, Billets, Détail ventes)

**Files :**
- Modify: `comptabilite/services.py` (append 5 méthodes)
- Modify: `tests/pytest/test_comptabilite_service.py` (append tests)

### Tests à écrire (TDD RED)

1. **`test_calculer_tva_par_taux`** : 2 lignes (vat=5.5, vat=20.0) → dict avec 2 clés `"5.50"` et `"20.00"`, chaque clé contient `{taux, total_ttc, total_ht, total_tva}`. Vérifier `total_ttc - total_ht == total_tva` (à l'arrondi près).
2. **`test_calculer_remboursements_status_negatifs`** : lignes avec `status=REFUNDED` et `status=CREDIT_NOTE` regroupées en 2 sous-clés `refunded` et `credit_notes`, chaque sous-clé contient `{total, nb}`. Total négatif attendu.
3. **`test_calculer_adhesions_avec_membership`** : 1 ligne avec `membership__isnull=False` → dict `detail` clé composite `<uuid_produit>__<uuid_tarif>__<moyen>`, avec `nom_produit`, `nom_tarif`, `moyen_paiement`, `total`, `nb`. Champ `total` et `nb` au niveau racine.
4. **`test_calculer_billets_avec_reservation`** : 1 ligne avec `reservation__isnull=False` → dict `detail` clé composite `<uuid_event>__<uuid_produit>__<uuid_tarif>`, avec `nom_event`, `date_event`, `nom_produit`, `nom_tarif`, `nb`, `total`.
5. **`test_calculer_detail_ventes_groupe_par_categorie`** : 3 lignes (2 events « Concert », 1 adhésion) → dict groupé par catégorie article (`BILLET`, `FREERES`, `ADHESION`), chaque catégorie liste ses articles avec `qty_payants`, `qty_offerts`, `qty_total`, `total_ttc`, `total_ht`, `total_tva`, `taux_tva`. Catégorie d'origine : `Product.categorie_article` via `pricesold__productsold__product__categorie_article`.

### Implémentation (GREEN)

Méthodes à ajouter à `RapportComptableService` :

```python
def calculer_tva(self) -> dict:
    """
    Ventilation par taux de TVA.
    vat est un pourcentage (5.5 = 5.5%). Conversion HT/TVA :
      total_ht = total_ttc * 100 / (100 + vat)
      total_tva = total_ttc - total_ht
    """
    from collections import defaultdict
    agrege = (
        self.queryset
        .values("vat")
        .annotate(total_decimal=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")))
    )
    resultats = {}
    for ligne in agrege:
        vat = ligne["vat"] or Decimal("0")
        total_ttc = int(ligne["total_decimal"])
        if total_ttc == 0:
            continue
        total_ht = int(round(total_ttc * 100 / (100 + float(vat))))
        total_tva = total_ttc - total_ht
        key = f"{float(vat):.2f}"
        resultats[key] = {
            "taux": float(vat),
            "total_ttc": total_ttc,
            "total_ht": total_ht,
            "total_tva": total_tva,
        }
    return resultats


def calculer_remboursements(self) -> dict:
    """
    Avoirs (status=CREDIT_NOTE) et remboursements (status=REFUNDED).
    On filtre directement la queryset interne. CREDIT_NOTE est inclus dans
    _base_queryset. REFUNDED ne l'est pas — on requete a part.
    """
    from BaseBillet.models import LigneArticle

    credit_notes = (
        self.queryset
        .filter(status=LigneArticle.CREDIT_NOTE)
        .aggregate(
            total=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
            nb=Count("pk"),
        )
    )

    # Les REFUNDED ne sont PAS dans _base_queryset (status REFUNDED 'R' exclu).
    # On les recupere via une requete dediee respectant les autres filtres.
    refunded = (
        LigneArticle.objects.filter(
            datetime__gte=self.datetime_debut,
            datetime__lt=self.datetime_fin,
            status=LigneArticle.REFUNDED,
        )
        .exclude(sale_origin__in=["LB"])  # cf. SaleOrigin.LABOUTIK
        .aggregate(
            total=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
            nb=Count("pk"),
        )
    )

    return {
        "credit_notes": {
            "total": int(credit_notes["total"]),
            "nb": credit_notes["nb"],
        },
        "refunded": {
            "total": int(refunded["total"]),
            "nb": refunded["nb"],
        },
    }


def calculer_adhesions(self) -> dict:
    """
    Lignes liees a une Membership (LigneArticle.membership IS NOT NULL).
    Groupage par (produit_uuid, tarif_uuid, moyen_paiement).
    """
    from BaseBillet.models import PaymentMethod

    qs = self.queryset.filter(membership__isnull=False).select_related(
        "pricesold__productsold__product",
        "pricesold__price",
    )

    labels = dict(PaymentMethod.choices)
    detail = {}
    total_global = 0
    nb_global = 0

    for ligne in qs:
        if not ligne.pricesold:
            continue
        produit = ligne.pricesold.productsold.product if ligne.pricesold.productsold else None
        tarif = ligne.pricesold.price if ligne.pricesold else None
        produit_uuid = str(produit.uuid) if produit else "_"
        tarif_uuid = str(tarif.uuid) if tarif else "_"
        moyen = ligne.payment_method or PaymentMethod.UNKNOWN
        key = f"{produit_uuid}__{tarif_uuid}__{moyen}"
        ligne_total = int(ligne.amount * ligne.qty)

        if key not in detail:
            detail[key] = {
                "nom_produit": produit.name if produit else "—",
                "nom_tarif": tarif.name if tarif else "—",
                "moyen_paiement": moyen,
                "moyen_paiement_label": str(labels.get(moyen, moyen)),
                "total": 0,
                "nb": 0,
            }
        detail[key]["total"] += ligne_total
        detail[key]["nb"] += 1
        total_global += ligne_total
        nb_global += 1

    return {
        "detail": detail,
        "total": total_global,
        "nb": nb_global,
    }


def calculer_billets(self) -> dict:
    """
    Lignes liees a une Reservation (LigneArticle.reservation IS NOT NULL).
    Groupage par (event_uuid, produit_uuid, tarif_uuid).
    """
    qs = self.queryset.filter(reservation__isnull=False).select_related(
        "reservation__event",
        "pricesold__productsold__product",
        "pricesold__price",
    )

    detail = {}
    total_global = 0
    nb_global = 0

    for ligne in qs:
        event = ligne.reservation.event if ligne.reservation else None
        produit = (
            ligne.pricesold.productsold.product
            if ligne.pricesold and ligne.pricesold.productsold
            else None
        )
        tarif = ligne.pricesold.price if ligne.pricesold else None
        event_uuid = str(event.uuid) if event else "_"
        produit_uuid = str(produit.uuid) if produit else "_"
        tarif_uuid = str(tarif.uuid) if tarif else "_"
        key = f"{event_uuid}__{produit_uuid}__{tarif_uuid}"
        ligne_total = int(ligne.amount * ligne.qty)

        if key not in detail:
            detail[key] = {
                "nom_event": event.name if event else "—",
                "date_event": (
                    event.datetime.strftime("%Y-%m-%d %H:%M")
                    if event and event.datetime else "—"
                ),
                "nom_produit": produit.name if produit else "—",
                "nom_tarif": tarif.name if tarif else "—",
                "nb": 0,
                "total": 0,
            }
        detail[key]["nb"] += 1
        detail[key]["total"] += ligne_total
        total_global += ligne_total
        nb_global += 1

    return {
        "detail": detail,
        "nb": nb_global,
        "total": total_global,
    }


def calculer_detail_ventes(self) -> dict:
    """
    Detail des ventes groupe par Product.categorie_article (BILLET, ADHESION,
    FREERES, etc.). Pour chaque categorie : liste d'articles avec quantites
    payantes/offertes/total + HT/TVA/TTC + taux_tva.
    """
    from BaseBillet.models import PaymentMethod

    qs = self.queryset.select_related(
        "pricesold__productsold__product",
    )

    par_categorie = {}

    for ligne in qs:
        if not ligne.pricesold or not ligne.pricesold.productsold:
            continue
        produit = ligne.pricesold.productsold.product
        if not produit:
            continue
        categorie = produit.categorie_article or "ZZZ"
        nom_produit = produit.name
        ligne_total_ttc = int(ligne.amount * ligne.qty)
        offert = ligne.payment_method == PaymentMethod.FREE
        qty_decimal = float(ligne.qty)

        par_categorie.setdefault(categorie, {
            "nom_categorie": produit.get_categorie_article_display() if hasattr(produit, "get_categorie_article_display") else categorie,
            "articles": {},
            "total_ttc": 0,
        })

        articles = par_categorie[categorie]["articles"]
        articles.setdefault(nom_produit, {
            "nom_produit": nom_produit,
            "qty_payants": 0.0,
            "qty_offerts": 0.0,
            "qty_total": 0.0,
            "total_ttc": 0,
            "total_ht": 0,
            "total_tva": 0,
            "taux_tva": float(ligne.vat or 0),
        })

        a = articles[nom_produit]
        if offert:
            a["qty_offerts"] += qty_decimal
        else:
            a["qty_payants"] += qty_decimal
        a["qty_total"] += qty_decimal
        a["total_ttc"] += ligne_total_ttc

        # Conversion TTC -> HT pour cet article specifique
        vat = float(ligne.vat or 0)
        if vat > 0 and ligne_total_ttc != 0:
            ht = int(round(ligne_total_ttc * 100 / (100 + vat)))
        else:
            ht = ligne_total_ttc
        a["total_ht"] += ht
        a["total_tva"] += ligne_total_ttc - ht

        par_categorie[categorie]["total_ttc"] += ligne_total_ttc

    # Conversion articles dict -> list
    for cat in par_categorie.values():
        cat["articles"] = list(cat["articles"].values())

    return par_categorie
```

### Acceptance

- [ ] 5 tests passent (15 total avec S1+B1)
- [ ] `manage.py check` OK

---

## Bloc B3 — Synthèse + infos légales + hash + generer_rapport_complet

**Files :**
- Modify: `comptabilite/services.py` (append 4 méthodes)
- Modify: `tests/pytest/test_comptabilite_service.py` (append tests)

### Tests à écrire

1. **`test_calculer_synthese_operations`** : tableau croisé par type d'opération (`vente_billets`, `vente_adhesions`, `remboursements`) × moyen de paiement. Vérifier que les totaux croisés cohérents avec `calculer_billets()` et `calculer_adhesions()`.
2. **`test_calculer_infos_legales_depuis_configuration`** : récupère depuis `Configuration.get_solo()` les champs `organisation`, `adresse`, `code_postal`, `ville`, `siren`, `tva_number`, `email`, `phone`. Si certains sont vides, retourne `""`. Vérifier les 8 clés du dict.
3. **`test_calculer_hash_lignes_stable`** : même queryset → même hash. Modifier une ligne (changer amount) → hash différent. Hash est une string de 64 hex chars.
4. **`test_generer_rapport_complet_structure`** : retourne dict avec exactement ces clés au niveau racine : `totaux_par_moyen`, `detail_ventes`, `tva`, `adhesions`, `billets`, `remboursements`, `synthese_operations`, `infos_legales`, `meta`. Pas de clé en plus.
5. **`test_generer_rapport_complet_serialisable_json`** : `json.dumps(rapport)` ne lève pas d'exception (test que tous les Decimal/datetime sont convertis).

### Implémentation

```python
def calculer_synthese_operations(self) -> dict:
    """
    Tableau croise : type d'operation x moyen de paiement.
    Sections : vente_billets, vente_adhesions, remboursements.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod

    def _agrege_par_moyen(qs):
        result = {}
        rows = qs.values("payment_method").annotate(
            total=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
        )
        for r in rows:
            code = r["payment_method"] or PaymentMethod.UNKNOWN
            result[code] = int(r["total"])
        return result

    return {
        "vente_billets": _agrege_par_moyen(self.queryset.filter(reservation__isnull=False)),
        "vente_adhesions": _agrege_par_moyen(self.queryset.filter(membership__isnull=False)),
        "remboursements": _agrege_par_moyen(
            self.queryset.filter(status=LigneArticle.CREDIT_NOTE)
        ),
    }


def calculer_infos_legales(self) -> dict:
    """
    Recupere les infos legales du tenant (Configuration.get_solo()).
    """
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()
    return {
        "organisation": str(config.organisation or ""),
        "adresse": str(config.adresse or "") if hasattr(config, "adresse") else "",
        "code_postal": str(config.postal_code or "") if hasattr(config, "postal_code") else "",
        "ville": str(config.city or "") if hasattr(config, "city") else "",
        "siren": str(config.siren or "") if hasattr(config, "siren") else "",
        "tva_number": str(config.tva_number or "") if hasattr(config, "tva_number") else "",
        "email": str(config.email or "") if hasattr(config, "email") else "",
        "phone": str(config.phone or "") if hasattr(config, "phone") else "",
    }


def calculer_hash_lignes(self) -> str:
    """
    SHA-256 des tuples (pk, amount, qty, status) tries.
    """
    lignes = list(
        self.queryset
        .order_by("pk")
        .values("pk", "amount", "qty", "status")
    )
    payload = "|".join(
        f"{l['pk']}:{l['amount']}:{l['qty']}:{l['status']}"
        for l in lignes
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generer_rapport_complet(self) -> dict:
    """
    Compose le rapport complet (8 sections + meta).
    Resultat directement stockable dans ClotureCaisse.rapport_json (JSONField).
    """
    return {
        "totaux_par_moyen": self.calculer_totaux_par_moyen(),
        "detail_ventes": self.calculer_detail_ventes(),
        "tva": self.calculer_tva(),
        "adhesions": self.calculer_adhesions(),
        "billets": self.calculer_billets(),
        "remboursements": self.calculer_remboursements(),
        "synthese_operations": self.calculer_synthese_operations(),
        "infos_legales": self.calculer_infos_legales(),
        "meta": {
            "datetime_debut": self.datetime_debut.isoformat(),
            "datetime_fin": self.datetime_fin.isoformat(),
            "schema": connection.schema_name,
        },
    }
```

**Attention `infos_legales`** : les noms exacts des champs sur `Configuration` (adresse, postal_code, city, etc.) doivent être vérifiés dans le code V1 par le subagent (utiliser `Read BaseBillet/models.py` autour de `class Configuration`). Si un champ n'existe pas, retourner `""` plutôt qu'AttributeError.

### Acceptance

- [ ] 5 tests passent (20 total)
- [ ] `manage.py check` OK
- [ ] `json.dumps(rapport)` valide

---

## Bloc B4 — Tasks Celery + management command + test E2E

**Files :**
- Create: `comptabilite/tasks.py`
- Create: `comptabilite/management/__init__.py` (vide)
- Create: `comptabilite/management/commands/__init__.py` (vide)
- Create: `comptabilite/management/commands/generer_cloture.py`
- Modify: `tests/pytest/test_comptabilite_service.py` (append 2 tests E2E)

### Tests E2E

1. **`test_generer_cloture_pour_tenant_cree_une_cloture`** : appelle `generer_cloture_pour_tenant(schema_name='lespass', niveau='J', datetime_debut_iso=..., datetime_fin_iso=...)`. Vérifier qu'une `ClotureCaisse` est créée avec `niveau='J'`, `numero_sequentiel >= 1`, `rapport_json` non vide (8 sections), `hash_lignes` non vide.
2. **`test_generer_cloture_idempotent`** : appelle 2x la même fonction avec les mêmes bornes → 1 seule clôture en base (idempotence via le check `ClotureCaisse.objects.filter(niveau, datetime_debut, datetime_fin).exists()`).

### Implémentation `tasks.py`

```python
"""
Taches Celery + helpers de calcul pour la generation de clotures.
/ Celery tasks + calculation helpers for closure generation.

LOCALISATION : comptabilite/tasks.py
"""
import logging
from datetime import datetime, timedelta, time as dt_time

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

logger = logging.getLogger(__name__)


def _bornes_pour_niveau(niveau, datetime_debut_iso=None, datetime_fin_iso=None):
    """
    Calcule (datetime_debut, datetime_fin) pour le niveau J/H/M/A.
    Override possible via les parametres iso.
    / Compute (start, end) datetimes for J/H/M/A. Optional override via iso strings.
    """
    if datetime_debut_iso and datetime_fin_iso:
        return (
            datetime.fromisoformat(datetime_debut_iso),
            datetime.fromisoformat(datetime_fin_iso),
        )

    now_local = timezone.localtime()
    today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    if niveau == "J":
        # Journalier : [hier 00:00, aujourd'hui 00:00)
        return (today_midnight - timedelta(days=1), today_midnight)
    elif niveau == "H":
        # Hebdomadaire : [lundi semaine derniere 00:00, lundi semaine courante 00:00)
        # weekday() retourne 0=lundi
        lundi_courant = today_midnight - timedelta(days=today_midnight.weekday())
        return (lundi_courant - timedelta(days=7), lundi_courant)
    elif niveau == "M":
        # Mensuel : [1er du mois precedent, 1er du mois courant)
        premier_courant = today_midnight.replace(day=1)
        # premier du mois precedent
        if premier_courant.month == 1:
            premier_precedent = premier_courant.replace(year=premier_courant.year - 1, month=12)
        else:
            premier_precedent = premier_courant.replace(month=premier_courant.month - 1)
        return (premier_precedent, premier_courant)
    elif niveau == "A":
        # Annuel : [1er janvier annee precedente, 1er janvier courant)
        premier_janvier_courant = today_midnight.replace(month=1, day=1)
        premier_janvier_precedent = premier_janvier_courant.replace(
            year=premier_janvier_courant.year - 1
        )
        return (premier_janvier_precedent, premier_janvier_courant)
    else:
        raise ValueError(f"Niveau inconnu : {niveau}")


def _prochain_numero_sequentiel():
    """
    Lit le dernier numero sequentiel du tenant courant + 1 (avec verrou).
    A appeler dans transaction.atomic().
    / Read the last sequential number of the current tenant + 1 (with lock).
    """
    from comptabilite.models import ClotureCaisse
    derniere = (
        ClotureCaisse.objects
        .select_for_update()
        .order_by("-numero_sequentiel")
        .first()
    )
    return (derniere.numero_sequentiel + 1) if derniere else 1


def _calculer_total_perpetuel(niveau, total_general):
    """
    Total cumule depuis la creation du tenant (sur les clotures journalieres).
    Pour J : derniere J + total_general. Pour H/M/A : copie depuis la derniere J incluse.
    / Cumulative total since tenant creation (daily closures).
    """
    from comptabilite.models import ClotureCaisse
    derniere_journaliere = (
        ClotureCaisse.objects
        .filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        .order_by("-datetime_fin")
        .first()
    )
    base = derniere_journaliere.total_perpetuel if derniere_journaliere else 0
    if niveau == ClotureCaisse.NIVEAU_JOURNALIER:
        return base + total_general
    # H/M/A : on copie le total perpetuel de la derniere journaliere (pas d'addition)
    return base


@shared_task
def generer_cloture_pour_tenant(
    schema_name,
    niveau,
    datetime_debut_iso=None,
    datetime_fin_iso=None,
):
    """
    Genere 1 cloture pour 1 tenant donne.
    / Generate 1 closure for 1 given tenant.
    """
    from Customers.models import Client
    tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        from comptabilite.services import RapportComptableService
        from BaseBillet.models import Configuration

        config = Configuration.get_solo()
        if not (config.module_billetterie or config.module_adhesion):
            logger.info(f"[{schema_name}] Modules billetterie/adhesion desactives, skip.")
            return None

        datetime_debut, datetime_fin = _bornes_pour_niveau(
            niveau, datetime_debut_iso, datetime_fin_iso,
        )

        # Idempotence : si deja cree pour cette periode + niveau, on retourne sans erreur
        existante = ClotureCaisse.objects.filter(
            niveau=niveau,
            datetime_debut=datetime_debut,
            datetime_fin=datetime_fin,
        ).first()
        if existante:
            logger.info(f"[{schema_name}] Cloture {niveau} {datetime_debut} deja existante (#{existante.numero_sequentiel}), skip.")
            return str(existante.uuid)

        # Generation atomique : numero sequentiel + hash + persistance
        service = RapportComptableService(datetime_debut, datetime_fin)
        rapport = service.generer_rapport_complet()
        hash_lignes = service.calculer_hash_lignes()
        total_general = rapport["totaux_par_moyen"]["total"]

        # Total HT / TVA agreges depuis le rapport TVA
        total_ht = sum(t["total_ht"] for t in rapport["tva"].values())
        total_tva = sum(t["total_tva"] for t in rapport["tva"].values())

        with transaction.atomic():
            numero = _prochain_numero_sequentiel()
            perpetuel = _calculer_total_perpetuel(niveau, total_general)

            cloture = ClotureCaisse.objects.create(
                niveau=niveau,
                numero_sequentiel=numero,
                datetime_debut=datetime_debut,
                datetime_fin=datetime_fin,
                total_general=total_general,
                total_ht=total_ht,
                total_tva=total_tva,
                nombre_transactions=service.queryset.count(),
                total_perpetuel=perpetuel,
                hash_lignes=hash_lignes,
                rapport_json=rapport,
            )

        logger.info(f"[{schema_name}] Cloture {niveau} #{numero} creee (total={total_general}c, {cloture.nombre_transactions} txns).")
        return str(cloture.uuid)
```

### Implémentation `management/commands/generer_cloture.py`

```python
"""
Management command : generer une (ou plusieurs) cloture(s) manuellement.
/ Management command: manually generate one or more closures.

Usage :
    manage.py generer_cloture --niveau=J
    manage.py generer_cloture --niveau=J --tenant=lespass
    manage.py generer_cloture --niveau=M --datetime-debut=2026-04-01T00:00:00+00:00 \\
                              --datetime-fin=2026-05-01T00:00:00+00:00
"""
import logging
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Genere une cloture comptable pour un ou tous les tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--niveau",
            choices=["J", "H", "M", "A"],
            required=True,
            help="Niveau de cloture : J (jour), H (semaine), M (mois), A (annee).",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="schema_name d'un tenant precis. Si absent, tous les tenants actifs.",
        )
        parser.add_argument(
            "--datetime-debut",
            default=None,
            help="ISO datetime debut (override des bornes automatiques).",
        )
        parser.add_argument(
            "--datetime-fin",
            default=None,
            help="ISO datetime fin (override des bornes automatiques).",
        )

    def handle(self, *args, **opts):
        from Customers.models import Client
        from comptabilite.tasks import generer_cloture_pour_tenant

        if opts.get("tenant"):
            tenants = Client.objects.filter(schema_name=opts["tenant"])
            if not tenants.exists():
                self.stderr.write(f"Tenant {opts['tenant']} introuvable.")
                return
        else:
            tenants = Client.objects.exclude(schema_name="public")

        for tenant in tenants:
            self.stdout.write(f"-> {tenant.schema_name} (niveau={opts['niveau']})")
            uuid = generer_cloture_pour_tenant(
                schema_name=tenant.schema_name,
                niveau=opts["niveau"],
                datetime_debut_iso=opts.get("datetime_debut"),
                datetime_fin_iso=opts.get("datetime_fin"),
            )
            if uuid:
                self.stdout.write(self.style.SUCCESS(f"   cloture {uuid}"))
            else:
                self.stdout.write(self.style.WARNING(f"   skipped (modules inactifs)"))
```

### Acceptance

- [ ] 2 tests E2E passent (22 total)
- [ ] `manage.py generer_cloture --niveau=J --tenant=lespass` crée une `ClotureCaisse` en base avec rapport_json valide (vérification shell)
- [ ] 2e appel idempotent (ne crée pas de doublon)
- [ ] `manage.py check` OK

---

## Vérifications finales (à la sortie du Bloc B4)

```bash
# 1. Tests comptabilite (S1 + S2)
docker exec lespass_django bash -c "cd /DjangoFiles && /home/tibillet/.cache/pypoetry/virtualenvs/lespass-LcPHtxiF-py3.11/bin/pytest tests/pytest/test_comptabilite_*.py -v"
# Attendu : ~22 PASS

# 2. Check Django
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
# Attendu : 0 issues

# 3. Pas de migration manquante
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
# Attendu : No changes detected

# 4. Validation manuelle E2E
docker exec lespass_django poetry run python /DjangoFiles/manage.py generer_cloture --niveau=J --tenant=lespass
# Attendu : "-> lespass (niveau=J)" puis "cloture <uuid>"
# Verifier dans l'admin /admin/comptabilite/cloturecaisse/ qu'une cloture #1 (ou +1) apparait
# dans la liste, avec un total et un nombre de transactions.
```

## i18n S2

Les chaines ajoutees en S2 sont minimes (help text de la management command,
logs). Lancer `makemessages` + traduire + `compilemessages` en fin de S2.

## Message de commit suggéré (à fournir par le dernier subagent)

```
feat(comptabilite): S2 — service RapportComptableService + Celery task + management command

- comptabilite/services.py : RapportComptableService avec 8 méthodes
  calculer_* (totaux_par_moyen, detail_ventes, tva, adhesions, billets,
  remboursements, synthese_operations, infos_legales) +
  calculer_hash_lignes (SHA-256) + generer_rapport_complet (dict prêt à
  stocker dans ClotureCaisse.rapport_json).
- comptabilite/tasks.py : generer_cloture_pour_tenant (Celery shared_task)
  + helpers _bornes_pour_niveau (J/H/M/A), _prochain_numero_sequentiel
  (avec select_for_update), _calculer_total_perpetuel.
- comptabilite/management/commands/generer_cloture.py : commande manuelle
  --niveau --tenant --datetime-debut --datetime-fin.
- tests/pytest/test_comptabilite_service.py : 17 tests TDD (service +
  tâche + idempotence). Pattern live dev DB (cohérent avec S1).

Référence : TECH_DOC/SESSIONS/COMPTABILITE/SPEC.md §3-4-7, §9 (S2).
Plan : TECH_DOC/SESSIONS/COMPTABILITE/PLAN-S2-service-rapport.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Pièges anticipés pour S2

1. **`Sum(F('amount') * F('qty'))`** : retourne Decimal (à cause de qty Decimal). Caster en `int()` après aggregate, pas avant.
2. **`vat` est un pourcentage (5.5 = 5.5%)**, pas un coefficient (0.055). Conversion HT : `ht = ttc * 100 / (100 + vat)`.
3. **Champs `Configuration` possibles à ne pas exister** : `adresse`, `postal_code`, `city`, `siren`, `tva_number`, `email`, `phone` — utiliser `getattr(config, 'champ', '')` ou `hasattr()` pour éviter `AttributeError`.
4. **REFUNDED hors queryset de base** : `_base_queryset()` n'inclut que V/P/F/N. Pour les remboursements, requête dédiée.
5. **JSON serialization** : tester `json.dumps(rapport)` à la fin. Tout Decimal, datetime non-isoformaté, ou objet Django doit lever un test.
6. **Idempotence Celery** : check `exists()` avant `create()` mais accepter `IntegrityError` au cas où (concurrence).
7. **Numéro séquentiel** : `select_for_update()` dans `transaction.atomic()` indispensable.
8. **Total perpétuel** : ne s'applique pas pareil pour J vs H/M/A (cf. §3.5).
9. **Bornes temporelles** : `timezone.localtime()` puis truncate à minuit. UTC seul donnerait des résultats faux pour les tenants en zone non-UTC.
10. **`tasks.py` import circulaire** : importer les modèles à l'intérieur des fonctions (pas au top du fichier) pour éviter les soucis de chargement d'app au démarrage de Celery.

## Estimation

- Bloc B1 : ~30 min
- Bloc B2 : ~45 min
- Bloc B3 : ~30 min
- Bloc B4 : ~40 min

**Total : ~2h25 min** (hors validation maintaineur).
