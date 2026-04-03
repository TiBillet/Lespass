# Session 01 — Migration `scanned_at` + Service de calcul

> **Chantier :** Bilan billetterie interne (sous-projet 1/3)
> **Spec :** `../specs/2026-04-03-bilan-billetterie-design.md`
> **Plan global :** `../plans/2026-04-03-bilan-billetterie-plan.md`
> **Dépend de :** rien (première session)
> **Produit :** `BaseBillet/reports.py` + migration `scanned_at` + ~10 tests pytest

---

## Objectif

Poser les fondations du bilan : le service de calcul et la migration du champ de scan. À la fin de cette session, `RapportBilletterieService` est complet (8 méthodes), testé, et `scanned_at` est disponible sur le modèle `Ticket`.

---

## Contexte technique

### Modèles impliqués

- **`Event`** (`BaseBillet/models.py:1518`) : `jauge_max`, `datetime`, `uuid` PK
- **`Ticket`** (`BaseBillet/models.py:2588`) : `status` (C/N/K/S/R), `scanned_by` FK→ScanApp, `reservation` FK→Reservation. Constantes ligne 2598 : `CREATED, NOT_ACTIV, NOT_SCANNED, SCANNED, CANCELED = 'C', 'N', 'K', 'S', 'R'`
- **`Reservation`** (`BaseBillet/models.py:2205`) : `event` FK→Event, `user_commande` FK→User, `status`
- **`LigneArticle`** (`BaseBillet/models.py:2920`) : `amount` (centimes IntegerField), `sale_origin` (SaleOrigin choices), `payment_method` (PaymentMethod choices), `status` (V/R/N/C...), `vat` (DecimalField), `promotional_code` FK→PromotionalCode, `reservation` FK→Reservation (nullable), `datetime` (auto_now_add)
- **`PriceSold`** (`BaseBillet/models.py:2112`) : `price` FK→Price, `prix` (Decimal)
- **`Price`** (`BaseBillet/models.py:1311`) : `name`, `prix` (Decimal euros), `uuid`
- **`PromotionalCode`** (`BaseBillet/models.py:1233`) : `name`, `discount_rate` (Decimal %), `usage_count`

### Choices importants

```python
# BaseBillet/models.py:69
class SaleOrigin(models.TextChoices):
    LESPASS = "LP"    # En ligne
    LABOUTIK = "LB"   # Caisse POS
    ADMIN = "AD"      # Administration
    EXTERNAL = "EX"   # Externe
    # ... (9 valeurs au total)

# BaseBillet/models.py:81
class PaymentMethod(models.TextChoices):
    FREE = "NA"           # Offert
    CASH = "CA"           # Espèces
    CC = "CC"             # CB terminal
    STRIPE_NOFED = "SN"   # Stripe carte
    STRIPE_SEPA = "SP"    # Stripe SEPA
    # ... (13 valeurs au total)

# LigneArticle status
VALID = 'V'
REFUNDED = 'R'
CREDIT_NOTE = 'N'
CANCELED = 'C'
```

### Code de scan existant

Le scan se fait dans `BaseBillet/views_scan.py`, lignes 274-277 :

```python
scan_app = request.scan_app  # Set by HasScanApi permission
ticket.status = Ticket.SCANNED
ticket.scanned_by = scan_app
ticket.save()
```

C'est le seul endroit où un ticket passe en SCANNED. LaBoutik crée les tickets en NOT_SCANNED (`laboutik/views.py:3071`) mais ne scanne pas.

### Pattern à suivre

`laboutik/reports.py` — `RapportComptableService` (805 lignes, 13 méthodes). Même pattern : init avec un filtre, méthodes qui retournent des dicts. Montants en centimes. Calcul HT : `TTC / (1 + taux/100)`.

---

## Tâches

### 1.1 — Migration `scanned_at` sur Ticket

**Fichiers :**
- Modifier : `BaseBillet/models.py` (classe Ticket, après le champ `status`)
- Modifier : `BaseBillet/views_scan.py:274-277` (ajouter `scanned_at = timezone.now()`)

**Champ :**
```python
scanned_at = models.DateTimeField(
    null=True,
    blank=True,
    help_text=_("Date et heure du scan / Date and time of scan"),
)
```

**Commandes :**
```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name ticket_scanned_at
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

**Vérification :** `docker exec lespass_django poetry run pytest tests/pytest/ -q` — 0 régression.

---

### 1.2 — `RapportBilletterieService` : structure + `calculer_synthese()`

**Fichiers :**
- Créer : `BaseBillet/reports.py`
- Créer : `tests/pytest/test_rapport_billetterie_service.py`

**Le service :**
```python
class RapportBilletterieService:
    def __init__(self, event: Event):
        self.event = event
        self.lignes = LigneArticle.objects.filter(
            reservation__event=event,
        ).select_related(
            'pricesold__price__product',
            'pricesold__productsold',
            'promotional_code',
            'reservation',
        )
        self.tickets = Ticket.objects.filter(reservation__event=event)
```

**`calculer_synthese()` retourne :**
```python
{
    "jauge_max": int,           # Event.jauge_max
    "billets_vendus": int,      # Ticket status in [K, S]
    "billets_scannes": int,     # Ticket status = S
    "billets_annules": int,     # Ticket status = R
    "no_show": int,             # Ticket status = K
    "ca_ttc": int,              # Sum(amount) where status=VALID (centimes)
    "remboursements": int,      # Sum(amount) where status=REFUNDED (centimes)
    "ca_net": int,              # ca_ttc - remboursements (centimes)
    "taux_remplissage": float,  # (vendus / jauge_max) * 100
}
```

**Tests :**
- `test_synthese_event_sans_ventes` : tous les compteurs à 0
- `test_synthese_event_avec_ventes` : vérifier les totaux

---

### 1.3 — `calculer_ventes_par_tarif()`

**Retourne** une liste de dicts :
```python
[{
    "nom": str,            # Price.name
    "price_uuid": str,     # Price.uuid
    "vendus": int,         # Count where VALID and payment_method != FREE
    "offerts": int,        # Count where VALID and payment_method = FREE
    "ca_ttc": int,         # Sum(amount) where VALID (centimes)
    "ca_ht": int,          # TTC / (1 + taux_tva/100) (centimes)
    "tva": int,            # ca_ttc - ca_ht (centimes)
    "taux_tva": float,     # depuis LigneArticle.vat
    "rembourses": int,     # Count where REFUNDED
}]
```

**Query :** GROUP BY `pricesold__price__uuid`, `pricesold__price__name`.

**Tests :**
- `test_ventes_par_tarif_avec_donnees` : au moins 2 tarifs, clés présentes, total vendus cohérent avec synthèse

---

### 1.4 — `calculer_par_moyen_paiement()` et `calculer_par_canal()`

**`calculer_par_moyen_paiement()` retourne :**
```python
[{
    "code": str,         # PaymentMethod code (ex: "SN")
    "label": str,        # PaymentMethod.label (ex: "Online: Stripe CC")
    "montant": int,      # Sum(amount) centimes
    "pourcentage": float,
    "nb_billets": int,
}]
```

**`calculer_par_canal()` retourne :** même structure, GROUP BY `sale_origin`. **Retourne `None`** si un seul canal (section masquée).

**Tests :**
- `test_par_moyen_paiement` : total montants = CA TTC synthèse
- `test_par_canal_masque_si_canal_unique` : retourne None

---

### 1.5 — `calculer_scans()` avec tranches horaires

**Retourne :**
```python
{
    "scannes": int,
    "non_scannes": int,
    "annules": int,
    "tranches_horaires": {        # None si aucun scanned_at
        "labels": ["19h00", "19h30", ...],
        "data": [45, 120, ...],
    } | None,
}
```

**Tranches 30 min :** `ExtractHour('scanned_at')` + `Case/When` pour floor à 0 ou 30.

**Tests :**
- `test_scans_avec_scanned_at` : tranches non nulles, labels et data présents

---

### 1.6 — `calculer_codes_promo()`, `calculer_remboursements()`, `calculer_courbe_ventes()`

**`calculer_codes_promo()` retourne :** `None` si aucun promo, sinon liste de dicts `{nom, taux_reduction, utilisations, manque_a_gagner}`.

**`calculer_remboursements()` retourne :** `{nombre, montant_total, taux}`.

**`calculer_courbe_ventes()` retourne :** `{labels: [dates], datasets: [{label, data: [cumulé]}]}` — format Chart.js ready.

**Tests :**
- `test_codes_promo_retourne_none_si_aucun`
- `test_remboursements`
- `test_courbe_ventes` : données cumulées (chaque valeur >= précédente)

---

## Vérification finale

```bash
# Tous les tests du service
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v

# Suite complète — 0 régression
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résultat attendu

- `BaseBillet/reports.py` : ~200 lignes, 8 méthodes, 0 dépendance externe
- `BaseBillet/migrations/XXXX_ticket_scanned_at.py` : 1 champ nullable
- `BaseBillet/views_scan.py` : 1 ligne ajoutée
- `tests/pytest/test_rapport_billetterie_service.py` : ~10 tests
- Tous les tests existants passent (0 régression)
