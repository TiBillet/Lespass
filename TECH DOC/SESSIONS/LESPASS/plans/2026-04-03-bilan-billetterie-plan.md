# Bilan Billetterie — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fournir un bilan de billetterie complet par événement dans l'admin Django Unfold, avec exports PDF/CSV.

**Architecture:** Un service `RapportBilletterieService` dans `BaseBillet/reports.py` (même pattern que `laboutik/reports.py`), exposé via des URLs custom dans `EventAdmin` (`get_urls()`). Les graphiques utilisent Chart.js natif d'Unfold. Une migration ajoute `scanned_at` sur `Ticket`.

**Tech Stack:** Django 4.2, DRF, django-unfold (Chart.js natif), WeasyPrint (PDF), django-tenants, pytest.

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-03-bilan-billetterie-design.md`

---

## Session 01 — Migration + Service de calcul

### Tâche 1.1 : Migration `scanned_at` sur Ticket

**Fichiers :**
- Modifier : `BaseBillet/models.py` (classe `Ticket`, ligne ~2588)
- Créer : `BaseBillet/migrations/XXXX_ticket_scanned_at.py` (auto-généré)
- Modifier : `BaseBillet/views_scan.py:275` (ajouter `scanned_at`)

**Contexte :** Le modèle `Ticket` est dans `BaseBillet/models.py`. Les constantes sont à la ligne 2598 : `CREATED, NOT_ACTIV, NOT_SCANNED, SCANNED, CANCELED = 'C', 'N', 'K', 'S', 'R'`. Le scan se fait dans `BaseBillet/views_scan.py` lignes 274-277.

- [ ] **Étape 1 : Ajouter le champ `scanned_at` sur Ticket**

Dans `BaseBillet/models.py`, classe `Ticket` (ligne ~2588), ajouter après le champ `status` :

```python
scanned_at = models.DateTimeField(
    null=True,
    blank=True,
    help_text=_("Date et heure du scan / Date and time of scan"),
)
```

- [ ] **Étape 2 : Générer et appliquer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name ticket_scanned_at
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

Attendu : migration créée et appliquée sans erreur.

- [ ] **Étape 3 : Modifier le code de scan pour écrire `scanned_at`**

Dans `BaseBillet/views_scan.py`, lignes 274-277. Le code actuel :

```python
scan_app = request.scan_app  # Set by HasScanApi permission
ticket.status = Ticket.SCANNED
ticket.scanned_by = scan_app
ticket.save()
```

Ajouter `scanned_at` :

```python
scan_app = request.scan_app  # Set by HasScanApi permission
ticket.status = Ticket.SCANNED
ticket.scanned_by = scan_app
ticket.scanned_at = timezone.now()
ticket.save()
```

Vérifier que `from django.utils import timezone` est importé en tête de fichier.

- [ ] **Étape 4 : Vérifier que les tests existants passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : tous les tests passent (le champ est nullable, pas d'impact).

---

### Tâche 1.2 : `RapportBilletterieService` — structure et synthèse

**Fichiers :**
- Créer : `BaseBillet/reports.py`
- Créer : `tests/pytest/test_rapport_billetterie_service.py`

**Contexte :** Le pattern à suivre est `laboutik/reports.py` (`RapportComptableService`). Source de données : `LigneArticle` filtrées par `reservation__event`. Les montants sont en **centimes** (IntegerField). Les choices sont dans `BaseBillet/models.py` : `SaleOrigin` (ligne 69), `PaymentMethod` (ligne 81).

- [ ] **Étape 1 : Écrire le test pour un event sans ventes**

```python
# tests/pytest/test_rapport_billetterie_service.py
"""
Tests du service de rapport de billetterie.
/ Tests for the ticketing report service.

LOCALISATION : tests/pytest/test_rapport_billetterie_service.py
"""
import pytest
from django.utils import timezone
from datetime import timedelta

from BaseBillet.models import Event, Ticket, Reservation, LigneArticle
from BaseBillet.reports import RapportBilletterieService


@pytest.mark.django_db
class TestRapportBilletterieSynthese:
    """
    Tests de la methode calculer_synthese().
    / Tests for calculer_synthese() method.
    """

    def test_synthese_event_sans_ventes(self, event_without_sales):
        """
        Un event sans aucune vente retourne tous les compteurs a zero.
        / An event with no sales returns all counters at zero.
        """
        service = RapportBilletterieService(event_without_sales)
        synthese = service.calculer_synthese()

        assert synthese["jauge_max"] == event_without_sales.jauge_max
        assert synthese["billets_vendus"] == 0
        assert synthese["billets_scannes"] == 0
        assert synthese["no_show"] == 0
        assert synthese["ca_ttc"] == 0
        assert synthese["remboursements"] == 0
        assert synthese["ca_net"] == 0
        assert synthese["taux_remplissage"] == 0.0
```

- [ ] **Étape 2 : Écrire la fixture `event_without_sales`**

Dans le même fichier de test, ou dans `tests/pytest/conftest.py` si une fixture partagée existe déjà pour les events. Vérifier d'abord :

```bash
docker exec lespass_django poetry run python -c "
from django_tenants.utils import schema_context
with schema_context('lespass'):
    from BaseBillet.models import Event
    print(Event.objects.first())
"
```

Si des events de test existent déjà dans la DB, utiliser une fixture qui en crée un frais :

```python
@pytest.fixture
def event_without_sales(db, tenant_lespass):
    """
    Cree un event de test sans aucune reservation ni vente.
    / Creates a test event with no reservations or sales.
    """
    from django_tenants.utils import tenant_context
    with tenant_context(tenant_lespass):
        event = Event.objects.create(
            name="Test Bilan Vide",
            datetime=timezone.now() + timedelta(days=7),
            jauge_max=100,
            published=True,
        )
        return event
```

Note : adapter selon les fixtures existantes dans `tests/pytest/conftest.py`. Le `tenant_lespass` doit exister — vérifier dans le conftest.

- [ ] **Étape 3 : Lancer le test pour vérifier qu'il échoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py::TestRapportBilletterieSynthese::test_synthese_event_sans_ventes -v
```

Attendu : `ImportError: cannot import name 'RapportBilletterieService' from 'BaseBillet.reports'`

- [ ] **Étape 4 : Créer `BaseBillet/reports.py` avec `calculer_synthese()`**

```python
"""
Service de rapport de billetterie.
Calcule les statistiques d'un evenement : ventes, scans, CA, remboursements.
/ Ticketing report service.
/ Computes event statistics: sales, scans, revenue, refunds.

LOCALISATION : BaseBillet/reports.py

Ce service est l'equivalent de laboutik/reports.py (RapportComptableService)
mais pour la billetterie. Il est initialise avec un Event et chaque methode
retourne un dict serialisable JSON.

DEPENDENCIES :
- BaseBillet.models : Event, Ticket, LigneArticle, Reservation
- Utilise par : Administration/admin/events.py (page bilan)
"""
from django.db.models import Sum, Count, Q

from BaseBillet.models import (
    Event, Ticket, LigneArticle,
)


class RapportBilletterieService:
    """
    Calcule les statistiques de billetterie pour un evenement.
    Initialise avec un Event, chaque methode retourne un dict.
    / Computes ticketing statistics for an event.

    LOCALISATION : BaseBillet/reports.py
    """

    def __init__(self, event: Event):
        self.event = event

        # Queryset de base : toutes les LigneArticle liees a cet event
        # via la reservation. On inclut VALID et REFUNDED pour les calculs.
        # / Base queryset: all LigneArticle linked to this event via reservation.
        self.lignes = LigneArticle.objects.filter(
            reservation__event=event,
        ).select_related(
            'pricesold__price__product',
            'pricesold__productsold',
            'promotional_code',
            'reservation',
        )

        # Queryset des tickets pour les statistiques de scan
        # / Ticket queryset for scan statistics
        self.tickets = Ticket.objects.filter(
            reservation__event=event,
        )

    def calculer_synthese(self):
        """
        Calcule les totaux globaux de l'evenement.
        Retourne un dict avec jauge, vendus, scannes, CA, remboursements.
        / Computes global event totals.

        LOCALISATION : BaseBillet/reports.py

        Billets vendus = Tickets avec status NOT_SCANNED ou SCANNED (= valides).
        CA TTC = somme des montants des LigneArticle VALID uniquement.
        Remboursements = somme des montants des LigneArticle REFUNDED.
        CA net = CA TTC - remboursements (en valeur absolue).
        """
        # Compter les billets par statut
        # / Count tickets by status
        billets_vendus = self.tickets.filter(
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
        ).count()

        billets_scannes = self.tickets.filter(
            status=Ticket.SCANNED,
        ).count()

        billets_annules = self.tickets.filter(
            status=Ticket.CANCELED,
        ).count()

        # No-show = billets valides non scannes
        # (pertinent uniquement apres l'event)
        # / No-show = valid tickets not scanned (relevant after the event)
        no_show = self.tickets.filter(
            status=Ticket.NOT_SCANNED,
        ).count()

        # CA TTC = somme des montants des lignes VALID (en centimes)
        # / Revenue = sum of VALID line amounts (in cents)
        ca_ttc_resultat = self.lignes.filter(
            status=LigneArticle.VALID,
        ).aggregate(
            total=Sum('amount'),
        )
        ca_ttc = ca_ttc_resultat['total'] or 0

        # Remboursements = somme des montants des lignes REFUNDED (en centimes)
        # Les montants rembourses sont positifs dans la base,
        # on les affiche en negatif dans le rapport.
        # / Refunds = sum of REFUNDED line amounts (in cents)
        remboursements_resultat = self.lignes.filter(
            status=LigneArticle.REFUNDED,
        ).aggregate(
            total=Sum('amount'),
        )
        remboursements = remboursements_resultat['total'] or 0

        # CA net = CA TTC - remboursements
        # / Net revenue = revenue - refunds
        ca_net = ca_ttc - remboursements

        # Taux de remplissage (en pourcentage, 0 si jauge_max = 0)
        # / Fill rate (percentage, 0 if jauge_max = 0)
        jauge_max = self.event.jauge_max or 0
        if jauge_max > 0:
            taux_remplissage = round((billets_vendus / jauge_max) * 100, 1)
        else:
            taux_remplissage = 0.0

        return {
            "jauge_max": jauge_max,
            "billets_vendus": billets_vendus,
            "billets_scannes": billets_scannes,
            "billets_annules": billets_annules,
            "no_show": no_show,
            "ca_ttc": ca_ttc,
            "remboursements": remboursements,
            "ca_net": ca_net,
            "taux_remplissage": taux_remplissage,
        }
```

- [ ] **Étape 5 : Relancer le test — doit passer**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py::TestRapportBilletterieSynthese::test_synthese_event_sans_ventes -v
```

Attendu : PASS.

---

### Tâche 1.3 : `calculer_ventes_par_tarif()`

**Fichiers :**
- Modifier : `BaseBillet/reports.py`
- Modifier : `tests/pytest/test_rapport_billetterie_service.py`

**Contexte :** Les montants sont en centimes. Le taux TVA est sur `LigneArticle.vat` (DecimalField). Les offerts ont `payment_method='NA'` (FREE). La jointure vers le nom du tarif passe par `pricesold__price__name`.

- [ ] **Étape 1 : Écrire le test avec des ventes mixtes**

```python
def test_ventes_par_tarif_avec_donnees(self, event_with_mixed_sales):
    """
    Un event avec des ventes plein tarif, reduit et gratuit.
    Verifie la ventilation par tarif.
    / An event with full price, reduced and free sales.
    """
    service = RapportBilletterieService(event_with_mixed_sales)
    tarifs = service.calculer_ventes_par_tarif()

    assert len(tarifs) >= 2  # Au moins 2 tarifs differents

    # Verifier que chaque tarif a les cles attendues
    # / Verify each tarif has expected keys
    for tarif in tarifs:
        assert "nom" in tarif
        assert "vendus" in tarif
        assert "offerts" in tarif
        assert "ca_ttc" in tarif
        assert "ca_ht" in tarif
        assert "tva" in tarif
        assert "rembourses" in tarif

    # Verifier le total vendus = somme des tarifs
    # / Verify total sold = sum of tarifs
    total_vendus = sum(t["vendus"] for t in tarifs)
    total_offerts = sum(t["offerts"] for t in tarifs)
    synthese = service.calculer_synthese()
    assert total_vendus + total_offerts == synthese["billets_vendus"]
```

La fixture `event_with_mixed_sales` crée un event avec :
- 3 tickets "Plein tarif" à 1000 centimes (10€), TVA 5.5%, payment_method=STRIPE_NOFED, status=VALID
- 2 tickets "Réduit" à 500 centimes (5€), TVA 5.5%, payment_method=CASH, status=VALID
- 1 ticket "Invitation" à 0 centimes, payment_method=FREE, status=VALID
- 1 ticket "Plein tarif" remboursé : status=REFUNDED

La fixture doit créer : Event + Product(BILLET) + Price + PriceSold + ProductSold + Reservation + Ticket + LigneArticle pour chaque cas. Adapter selon les fixtures existantes du conftest.

- [ ] **Étape 2 : Lancer le test — doit échouer (méthode pas encore créée)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py::TestRapportBilletterieSynthese::test_ventes_par_tarif_avec_donnees -v
```

Attendu : `AttributeError: 'RapportBilletterieService' object has no attribute 'calculer_ventes_par_tarif'`

- [ ] **Étape 3 : Implémenter `calculer_ventes_par_tarif()`**

Ajouter à la classe `RapportBilletterieService` dans `BaseBillet/reports.py` :

```python
def calculer_ventes_par_tarif(self):
    """
    Ventile les ventes par tarif (Price).
    Retourne une liste de dicts, un par tarif ayant genere au moins une vente.
    / Breaks down sales by price tier.

    LOCALISATION : BaseBillet/reports.py

    Chaque dict contient : nom, vendus, offerts, ca_ttc, ca_ht, tva, rembourses.
    Les montants sont en centimes.
    Calcul HT : TTC / (1 + taux_tva / 100).
    """
    from django.db.models import F, Value, DecimalField
    from django.db.models.functions import Coalesce

    # Recuperer toutes les lignes VALID ou REFUNDED avec leur tarif
    # / Get all VALID or REFUNDED lines with their price tier
    lignes_avec_tarif = self.lignes.filter(
        status__in=[LigneArticle.VALID, LigneArticle.REFUNDED],
    ).values(
        'pricesold__price__uuid',
        'pricesold__price__name',
    ).annotate(
        vendus=Count(
            'uuid',
            filter=Q(status=LigneArticle.VALID) & ~Q(payment_method='NA'),
        ),
        offerts=Count(
            'uuid',
            filter=Q(status=LigneArticle.VALID, payment_method='NA'),
        ),
        ca_ttc=Coalesce(
            Sum('amount', filter=Q(status=LigneArticle.VALID)),
            0,
        ),
        rembourses=Count(
            'uuid',
            filter=Q(status=LigneArticle.REFUNDED),
        ),
    ).order_by('pricesold__price__name')

    # Construire la liste de resultats avec calcul HT/TVA
    # / Build result list with HT/VAT calculation
    resultats = []
    for ligne in lignes_avec_tarif:
        ca_ttc = ligne['ca_ttc']

        # Recuperer le taux de TVA moyen pour ce tarif
        # (toutes les lignes d'un meme tarif ont normalement le meme taux)
        # / Get average VAT rate for this price tier
        taux_tva = self.lignes.filter(
            pricesold__price__uuid=ligne['pricesold__price__uuid'],
            status=LigneArticle.VALID,
        ).values_list('vat', flat=True).first()
        taux_tva = float(taux_tva) if taux_tva else 0.0

        # Calcul HT = TTC / (1 + taux / 100)
        # / HT = TTC / (1 + rate / 100)
        if taux_tva > 0:
            ca_ht = int(round(ca_ttc / (1 + taux_tva / 100)))
        else:
            ca_ht = ca_ttc

        tva_montant = ca_ttc - ca_ht

        resultats.append({
            "nom": ligne['pricesold__price__name'] or "Sans tarif",
            "price_uuid": str(ligne['pricesold__price__uuid']),
            "vendus": ligne['vendus'],
            "offerts": ligne['offerts'],
            "ca_ttc": ca_ttc,
            "ca_ht": ca_ht,
            "tva": tva_montant,
            "taux_tva": taux_tva,
            "rembourses": ligne['rembourses'],
        })

    return resultats
```

- [ ] **Étape 4 : Relancer le test — doit passer**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v
```

Attendu : tous les tests passent.

---

### Tâche 1.4 : `calculer_par_moyen_paiement()` et `calculer_par_canal()`

**Fichiers :**
- Modifier : `BaseBillet/reports.py`
- Modifier : `tests/pytest/test_rapport_billetterie_service.py`

- [ ] **Étape 1 : Écrire les tests**

```python
def test_par_moyen_paiement(self, event_with_mixed_sales):
    """
    Verifie la ventilation par moyen de paiement.
    / Verifies breakdown by payment method.
    """
    service = RapportBilletterieService(event_with_mixed_sales)
    moyens = service.calculer_par_moyen_paiement()

    assert len(moyens) >= 2  # Au moins Stripe + Especes

    # Chaque moyen a les cles attendues
    for moyen in moyens:
        assert "code" in moyen
        assert "label" in moyen
        assert "montant" in moyen
        assert "pourcentage" in moyen
        assert "nb_billets" in moyen

    # Le total des montants = CA TTC de la synthese
    # / Total amounts = revenue from synthese
    total_montants = sum(m["montant"] for m in moyens)
    synthese = service.calculer_synthese()
    assert total_montants == synthese["ca_ttc"]


def test_par_canal_masque_si_canal_unique(self, event_with_mixed_sales_single_channel):
    """
    Si toutes les ventes viennent du meme canal, la methode retourne None.
    / If all sales come from the same channel, method returns None.
    """
    service = RapportBilletterieService(event_with_mixed_sales_single_channel)
    canaux = service.calculer_par_canal()

    assert canaux is None
```

- [ ] **Étape 2 : Implémenter les deux méthodes**

```python
def calculer_par_moyen_paiement(self):
    """
    Ventile les ventes par moyen de paiement.
    Retourne une liste de dicts, un par moyen present.
    / Breaks down sales by payment method.

    LOCALISATION : BaseBillet/reports.py
    """
    from BaseBillet.models import PaymentMethod

    lignes_valides = self.lignes.filter(status=LigneArticle.VALID)

    # GROUP BY payment_method
    par_moyen = lignes_valides.values(
        'payment_method',
    ).annotate(
        montant=Sum('amount'),
        nb_billets=Count('uuid'),
    ).order_by('-montant')

    # CA total pour calculer les pourcentages
    # / Total revenue for percentage calculation
    ca_total = sum(m['montant'] or 0 for m in par_moyen)

    resultats = []
    for moyen in par_moyen:
        code = moyen['payment_method']
        montant = moyen['montant'] or 0

        # Label humain depuis les TextChoices
        # / Human label from TextChoices
        try:
            label = PaymentMethod(code).label
        except ValueError:
            label = code or "Inconnu"

        pourcentage = round((montant / ca_total) * 100, 1) if ca_total > 0 else 0.0

        resultats.append({
            "code": code,
            "label": label,
            "montant": montant,
            "pourcentage": pourcentage,
            "nb_billets": moyen['nb_billets'],
        })

    return resultats


def calculer_par_canal(self):
    """
    Ventile les ventes par canal de vente (sale_origin).
    Retourne None si un seul canal (section masquee dans le template).
    / Breaks down sales by sale origin. Returns None if single channel.

    LOCALISATION : BaseBillet/reports.py
    """
    from BaseBillet.models import SaleOrigin

    lignes_valides = self.lignes.filter(status=LigneArticle.VALID)

    # Compter le nombre de canaux distincts
    # / Count distinct channels
    canaux_distincts = lignes_valides.values(
        'sale_origin'
    ).distinct().count()

    # Si un seul canal, pas la peine d'afficher la section
    # / If single channel, no need to show this section
    if canaux_distincts <= 1:
        return None

    # GROUP BY sale_origin
    par_canal = lignes_valides.values(
        'sale_origin',
    ).annotate(
        montant=Sum('amount'),
        nb_billets=Count('uuid'),
    ).order_by('-montant')

    resultats = []
    for canal in par_canal:
        code = canal['sale_origin']
        try:
            label = SaleOrigin(code).label
        except ValueError:
            label = code or "Inconnu"

        resultats.append({
            "code": code,
            "label": label,
            "montant": canal['montant'] or 0,
            "nb_billets": canal['nb_billets'],
        })

    return resultats
```

- [ ] **Étape 3 : Relancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v
```

---

### Tâche 1.5 : `calculer_scans()` avec tranches horaires

**Fichiers :**
- Modifier : `BaseBillet/reports.py`
- Modifier : `tests/pytest/test_rapport_billetterie_service.py`

- [ ] **Étape 1 : Écrire le test**

```python
def test_scans_avec_scanned_at(self, event_with_scanned_tickets):
    """
    Verifie les compteurs de scan et les tranches horaires.
    / Verifies scan counters and time slots.
    """
    service = RapportBilletterieService(event_with_scanned_tickets)
    scans = service.calculer_scans()

    assert scans["scannes"] > 0
    assert scans["non_scannes"] >= 0
    assert scans["annules"] >= 0
    assert scans["scannes"] + scans["non_scannes"] > 0

    # Les tranches horaires sont presentes si scanned_at est renseigne
    # / Time slots present if scanned_at is set
    assert scans["tranches_horaires"] is not None
    assert len(scans["tranches_horaires"]["labels"]) > 0
    assert len(scans["tranches_horaires"]["data"]) > 0
```

La fixture `event_with_scanned_tickets` crée des tickets avec `scanned_at` renseigné à différentes heures (19h00, 19h15, 19h45, 20h10).

- [ ] **Étape 2 : Implémenter `calculer_scans()`**

```python
def calculer_scans(self):
    """
    Statistiques de scan : compteurs par statut + tranches horaires 30 min.
    Retourne None pour les tranches si aucun scanned_at n'est renseigne.
    / Scan statistics: counters by status + 30min time slots.

    LOCALISATION : BaseBillet/reports.py
    """
    from django.db.models.functions import ExtractHour, ExtractMinute
    from django.db.models import Case, When, Value, IntegerField

    scannes = self.tickets.filter(status=Ticket.SCANNED).count()
    non_scannes = self.tickets.filter(status=Ticket.NOT_SCANNED).count()
    annules = self.tickets.filter(status=Ticket.CANCELED).count()

    # Tranches horaires : uniquement si au moins un scanned_at est renseigne
    # / Time slots: only if at least one scanned_at is set
    tickets_avec_scan_at = self.tickets.filter(
        status=Ticket.SCANNED,
        scanned_at__isnull=False,
    )

    tranches_horaires = None
    if tickets_avec_scan_at.exists():
        # Annoter chaque ticket avec sa tranche de 30 minutes
        # heure = ExtractHour, demi = 0 si minute < 30, sinon 30
        # / Annotate each ticket with its 30-minute slot
        par_tranche = tickets_avec_scan_at.annotate(
            heure=ExtractHour('scanned_at'),
            demi=Case(
                When(
                    **{'scanned_at__minute__lt': 30},
                    then=Value(0),
                ),
                default=Value(30),
                output_field=IntegerField(),
            ),
        ).values('heure', 'demi').annotate(
            count=Count('uuid'),
        ).order_by('heure', 'demi')

        # Construire les labels et les donnees pour Chart.js
        # / Build labels and data for Chart.js
        labels = []
        data = []
        for tranche in par_tranche:
            heure = tranche['heure']
            demi = tranche['demi']
            label = f"{heure:02d}h{demi:02d}"
            labels.append(label)
            data.append(tranche['count'])

        tranches_horaires = {
            "labels": labels,
            "data": data,
        }

    return {
        "scannes": scannes,
        "non_scannes": non_scannes,
        "annules": annules,
        "tranches_horaires": tranches_horaires,
    }
```

Note : le lookup `scanned_at__minute__lt` fonctionne car Django décompose le `__minute` en `ExtractMinute` automatiquement. Si ça ne marche pas dans l'annotate `Case/When`, on passera par une annotation préalable `minute=ExtractMinute('scanned_at')` puis `When(minute__lt=30, ...)`.

- [ ] **Étape 3 : Relancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v
```

---

### Tâche 1.6 : `calculer_codes_promo()`, `calculer_remboursements()`, `calculer_courbe_ventes()`

**Fichiers :**
- Modifier : `BaseBillet/reports.py`
- Modifier : `tests/pytest/test_rapport_billetterie_service.py`

- [ ] **Étape 1 : Écrire les tests**

```python
def test_codes_promo_retourne_none_si_aucun(self, event_without_promos):
    """
    Si aucun code promo n'est utilise, retourne None.
    / If no promo code is used, returns None.
    """
    service = RapportBilletterieService(event_without_promos)
    promos = service.calculer_codes_promo()
    assert promos is None


def test_remboursements(self, event_with_refunds):
    """
    Verifie le calcul des remboursements.
    / Verifies refund calculation.
    """
    service = RapportBilletterieService(event_with_refunds)
    remb = service.calculer_remboursements()
    assert remb["nombre"] > 0
    assert remb["montant_total"] > 0
    assert 0 < remb["taux"] <= 100


def test_courbe_ventes(self, event_with_mixed_sales):
    """
    La courbe de ventes retourne des labels (dates) et des donnees cumulees.
    / Sales curve returns date labels and cumulated data.
    """
    service = RapportBilletterieService(event_with_mixed_sales)
    courbe = service.calculer_courbe_ventes()
    assert len(courbe["labels"]) > 0
    assert len(courbe["datasets"]) > 0

    # Les donnees sont cumulees : chaque valeur >= la precedente
    # / Data is cumulated: each value >= previous
    data = courbe["datasets"][0]["data"]
    for i in range(1, len(data)):
        assert data[i] >= data[i - 1]
```

- [ ] **Étape 2 : Implémenter les 3 méthodes**

```python
def calculer_codes_promo(self):
    """
    Ventile l'utilisation des codes promo.
    Retourne None si aucun code promo utilise.
    / Breaks down promotional code usage. Returns None if none used.

    LOCALISATION : BaseBillet/reports.py

    Manque a gagner = prix catalogue (pricesold.price.prix en centimes)
    moins le prix paye (LigneArticle.amount).
    """
    lignes_avec_promo = self.lignes.filter(
        status=LigneArticle.VALID,
        promotional_code__isnull=False,
    )

    if not lignes_avec_promo.exists():
        return None

    par_code = lignes_avec_promo.values(
        'promotional_code__uuid',
        'promotional_code__name',
        'promotional_code__discount_rate',
    ).annotate(
        utilisations=Count('uuid'),
        montant_paye=Sum('amount'),
    ).order_by('-utilisations')

    resultats = []
    for code in par_code:
        # Calculer le manque a gagner :
        # somme des prix catalogue - somme des montants payes
        # / Calculate revenue loss: catalog prices - paid amounts
        lignes_de_ce_code = lignes_avec_promo.filter(
            promotional_code__uuid=code['promotional_code__uuid'],
        ).select_related('pricesold__price')

        manque_a_gagner = 0
        for ligne in lignes_de_ce_code:
            prix_catalogue_centimes = int(round(ligne.pricesold.price.prix * 100))
            manque_a_gagner += prix_catalogue_centimes - ligne.amount

        resultats.append({
            "nom": code['promotional_code__name'],
            "taux_reduction": float(code['promotional_code__discount_rate']),
            "utilisations": code['utilisations'],
            "manque_a_gagner": manque_a_gagner,
        })

    return resultats


def calculer_remboursements(self):
    """
    Calcule le nombre et le montant des remboursements.
    / Computes refund count and total amount.

    LOCALISATION : BaseBillet/reports.py
    """
    lignes_remboursees = self.lignes.filter(
        status=LigneArticle.REFUNDED,
    )

    nombre = lignes_remboursees.count()
    montant_total = lignes_remboursees.aggregate(
        total=Sum('amount'),
    )['total'] or 0

    # Taux = rembourses / (valides + rembourses) * 100
    # / Rate = refunded / (valid + refunded) * 100
    total_lignes = self.lignes.filter(
        status__in=[LigneArticle.VALID, LigneArticle.REFUNDED],
    ).count()

    taux = round((nombre / total_lignes) * 100, 1) if total_lignes > 0 else 0.0

    return {
        "nombre": nombre,
        "montant_total": montant_total,
        "taux": taux,
    }


def calculer_courbe_ventes(self):
    """
    Ventes cumulees par jour pour le line chart.
    Retourne labels (dates) et datasets au format Chart.js.
    / Cumulated daily sales for line chart.

    LOCALISATION : BaseBillet/reports.py
    """
    from django.db.models.functions import TruncDate

    # Ventes par jour, triees chronologiquement
    # / Daily sales, ordered chronologically
    ventes_par_jour = self.lignes.filter(
        status=LigneArticle.VALID,
    ).annotate(
        jour=TruncDate('datetime'),
    ).values('jour').annotate(
        nb_ventes=Count('uuid'),
        montant=Sum('amount'),
    ).order_by('jour')

    # Cumuler les ventes
    # / Cumulate sales
    labels = []
    data_count = []
    data_montant = []
    cumul_count = 0
    cumul_montant = 0

    for jour in ventes_par_jour:
        cumul_count += jour['nb_ventes']
        cumul_montant += (jour['montant'] or 0)
        labels.append(jour['jour'].strftime('%d/%m'))
        data_count.append(cumul_count)
        data_montant.append(cumul_montant)

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Billets vendus",
                "data": data_count,
            },
        ],
    }
```

- [ ] **Étape 3 : Relancer tous les tests de la session**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v
```

- [ ] **Étape 4 : Lancer la suite complète pour vérifier 0 régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Session 02 — Admin Unfold : page bilan

### Tâche 2.1 : URLs custom et vue bilan dans EventAdmin

**Fichiers :**
- Modifier : `Administration/admin/events.py`
- Créer : `Administration/templates/admin/event/bilan.html`
- Créer : `Administration/templates/admin/event/partials/synthese.html`
- Créer : `Administration/templates/admin/event/partials/ventes_tarif.html`
- Créer : `Administration/templates/admin/event/partials/moyens_paiement.html`
- Créer : `Administration/templates/admin/event/partials/canaux_vente.html`
- Créer : `Administration/templates/admin/event/partials/scans.html`
- Créer : `Administration/templates/admin/event/partials/codes_promo.html`

**Contexte :** L'EventAdmin est dans `Administration/admin/events.py` (ligne 238). Il hérite de `ModelAdmin` Unfold + `ImportExportModelAdmin`. Les URLs custom utilisent `get_urls()` + `self.admin_site.admin_view()`. Les templates Unfold utilisent des inline styles (pas de Tailwind custom). Les composants chart sont dans `unfold/components/chart/line.html` et `bar.html`.

**Piège Unfold :** les helpers doivent être définis HORS de la classe (au niveau module). Ne jamais définir de méthode utilitaire dans le ModelAdmin.

- [ ] **Étape 1 : Écrire le test d'accès à la page bilan**

```python
# tests/pytest/test_bilan_admin_views.py
"""
Tests des vues admin du bilan de billetterie.
/ Tests for ticketing report admin views.

LOCALISATION : tests/pytest/test_bilan_admin_views.py
"""
import pytest
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite


@pytest.mark.django_db
class TestBilanAdminViews:

    def test_page_bilan_accessible(self, admin_client, event_with_mixed_sales):
        """
        La page bilan est accessible pour un admin connecte.
        / Bilan page is accessible for a logged-in admin.
        """
        url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/"
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_page_bilan_event_sans_ventes(self, admin_client, event_without_sales):
        """
        La page bilan s'affiche meme sans donnees (message "Aucune donnee").
        / Bilan page displays even without data.
        """
        url = f"/admin/basebillet/event/{event_without_sales.pk}/bilan/"
        response = admin_client.get(url)
        assert response.status_code == 200
```

Note : l'URL du site admin est `/admin/` (défini dans `TiBillet/urls_tenants.py:14`). Le nom du site est `staff_admin`.

- [ ] **Étape 2 : Ajouter `get_urls()` et la vue bilan dans EventAdmin**

Dans `Administration/admin/events.py`, ajouter avant la classe `EventAdmin` :

```python
from django.urls import path, re_path
from django.shortcuts import get_object_or_404
from BaseBillet.reports import RapportBilletterieService
```

Dans la classe `EventAdmin`, ajouter :

```python
def get_urls(self):
    urls = super().get_urls()
    custom_urls = [
        re_path(
            r'^(?P<object_id>[^/]+)/bilan/$',
            self.admin_site.admin_view(self.vue_bilan),
            name='basebillet_event_bilan',
        ),
    ]
    return custom_urls + urls

def vue_bilan(self, request, object_id):
    """
    Affiche le bilan de billetterie complet pour un evenement.
    / Displays the full ticketing report for an event.

    LOCALISATION : Administration/admin/events.py
    """
    from django.template.response import TemplateResponse

    event = get_object_or_404(Event, pk=object_id)
    service = RapportBilletterieService(event)

    # Calculer toutes les sections du rapport
    # / Compute all report sections
    contexte = {
        **self.admin_site.each_context(request),
        "event": event,
        "synthese": service.calculer_synthese(),
        "courbe_ventes": service.calculer_courbe_ventes(),
        "ventes_par_tarif": service.calculer_ventes_par_tarif(),
        "par_moyen_paiement": service.calculer_par_moyen_paiement(),
        "par_canal": service.calculer_par_canal(),
        "scans": service.calculer_scans(),
        "codes_promo": service.calculer_codes_promo(),
        "remboursements": service.calculer_remboursements(),
        "title": f"Bilan — {event.name}",
        "opts": self.model._meta,
    }

    return TemplateResponse(
        request,
        "admin/event/bilan.html",
        contexte,
    )
```

- [ ] **Étape 3 : Créer le template principal `bilan.html`**

Le template étend le layout Unfold. Les instructions détaillées pour chaque partial et les composants Chart.js seront dans les templates. Les inline styles suivent les variables CSS Unfold.

Ce fichier sera conséquent — créer d'abord une version minimale avec la synthèse, puis ajouter les partials un par un.

- [ ] **Étape 4 : Créer les 6 templates partials**

Chaque partial est un `{% include %}` dans `bilan.html`. Chaque partial utilise `unfold/components/card.html` comme conteneur. Les tableaux utilisent des inline styles. Les charts utilisent `unfold/components/chart/line.html` et `bar.html`.

- [ ] **Étape 5 : Ajouter la colonne "Bilan" dans la changelist**

Dans `EventAdmin.list_display`, ajouter `'display_bilan_link'`. Définir au niveau module (pas dans la classe !) une fonction helper, et dans la classe la méthode display :

```python
@display(description=_("Report"))
def display_bilan_link(self, obj):
    from django.utils.html import format_html
    has_reservations = Reservation.objects.filter(event=obj).exists()
    if not has_reservations:
        return "—"
    url = reverse('staff_admin:basebillet_event_bilan', args=[obj.pk])
    return format_html(
        '<a href="{}" title="{}"><span class="material-symbols-outlined">assessment</span></a>',
        url,
        _("Voir le bilan"),
    )
```

- [ ] **Étape 6 : Relancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bilan_admin_views.py tests/pytest/test_rapport_billetterie_service.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Session 03 — Exports PDF + CSV

### Tâche 3.1 : Export CSV

**Fichiers :**
- Modifier : `Administration/admin/events.py` (ajouter URL + vue)
- Créer : `tests/pytest/test_bilan_exports.py`

- [ ] **Étape 1 : Écrire le test**

```python
def test_export_csv(self, admin_client, event_with_mixed_sales):
    url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/csv/"
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    content = response.content.decode('utf-8-sig')
    assert "SYNTHESE" in content
    assert "VENTES PAR TARIF" in content
```

- [ ] **Étape 2 : Ajouter l'URL et la vue CSV dans EventAdmin**

La vue utilise `RapportBilletterieService` et écrit les sections dans un `csv.writer` avec délimiteur `;`.

- [ ] **Étape 3 : Relancer les tests**

### Tâche 3.2 : Export PDF (WeasyPrint)

**Fichiers :**
- Modifier : `Administration/admin/events.py` (ajouter URL + vue)
- Créer : `Administration/templates/admin/event/bilan_pdf.html`

- [ ] **Étape 1 : Écrire le test**

```python
def test_export_pdf(self, admin_client, event_with_mixed_sales):
    url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/pdf/"
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert len(response.content) > 1000  # Un PDF non vide
```

- [ ] **Étape 2 : Créer le template PDF et la vue**

Le template PDF reprend les mêmes données que la page admin, sans Chart.js. Les graphiques sont remplacés par des tableaux. CSS print A4 paysage.

- [ ] **Étape 3 : Relancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Session 04 — Tests E2E + Polish

### Tâche 4.1 : Tests E2E Playwright

**Fichiers :**
- Créer : `tests/e2e/test_bilan_billetterie.py`

- [ ] **Étape 1 : Écrire les tests E2E**

```python
def test_navigation_vers_bilan(self, page, admin_login):
    """
    Depuis la changelist events, cliquer sur le lien Bilan.
    / From events changelist, click on Report link.
    """
    page.goto("/admin/basebillet/event/")
    page.locator("[data-testid='bilan-link']").first.click()
    page.wait_for_url("**/bilan/")
    assert page.locator("[data-testid='bilan-synthese']").is_visible()
    assert page.locator("[data-testid='bilan-ventes-tarif']").is_visible()
```

- [ ] **Étape 2 : Ajouter `data-testid` sur tous les éléments interactifs des templates**

- [ ] **Étape 3 : Polish a11y et i18n**

Vérifier :
- `aria-label` sur les sections et tableaux
- `aria-live="polite"` sur les zones dynamiques
- `{% translate %}` sur tous les textes visibles
- `aria-hidden="true"` sur les icônes décoratives
- Contraste des textes dans les cartes

- [ ] **Étape 4 : Lancer la suite complète**

```bash
docker exec lespass_django poetry run pytest tests/ -q
```

---

## Récapitulatif des sessions

| Session | Tâches | Tests attendus | Fichiers créés/modifiés |
|---------|--------|----------------|------------------------|
| 01 | 1.1-1.6 | ~10 pytest | 3 créés, 2 modifiés |
| 02 | 2.1 | ~4 pytest | 8 créés, 1 modifié |
| 03 | 3.1-3.2 | ~4 pytest | 2 créés, 1 modifié |
| 04 | 4.1 | ~3 E2E | 1 créé, templates modifiés |
