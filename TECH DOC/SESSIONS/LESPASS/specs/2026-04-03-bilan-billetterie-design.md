# Design Spec — Bilan de billetterie interne

> **Sous-projet 1/3** du chantier "Rapports billetterie".
> Les sous-projets 2 (Export SIBIL) et 3 (Calculs fiscaux CNM/ASTP/TVA) viendront après.
>
> Date : 2026-04-03
> Auteurs : Jonas (mainteneur) + Claude Code (brainstorming)

---

## 1. Objectif

Fournir à l'organisateur d'événements un **bilan de billetterie complet** accessible dans l'admin Django Unfold. Le bilan est lié à un événement unique et s'adapte naturellement au cycle de vie de l'event (avant = pilotage des ventes, pendant = suivi des entrées, après = bilan définitif).

**Ce que ce n'est pas :**
- Pas un rapport comptable (c'est le job de laboutik)
- Pas une déclaration SIBIL (sous-projet 2)
- Pas un calcul de taxes (sous-projet 3)

---

## 2. Décisions prises

| # | Décision | Justification |
|---|----------|---------------|
| 1 | Admin Unfold uniquement (pas de frontend public) | Les organisateurs passent par l'admin |
| 2 | 1 bilan = 1 event (pas d'agrégation parent/enfants) | Simple. L'agrégation par période peut venir plus tard |
| 3 | Adaptation naturelle au cycle de vie | Pas de machine à états. Les sections vides parlent d'elles-mêmes |
| 4 | Migration `scanned_at` incluse | Débloque la courbe d'affluence horaire |
| 5 | Graphiques natifs Unfold (Chart.js inclus) | Pas de dépendance JS externe |
| 6 | Export PDF (WeasyPrint) + CSV (`;` UTF-8 BOM) | PDF pour les humains, CSV pour les tableurs |
| 7 | Sections conditionnelles | Les sections sans données ne s'affichent pas (codes promo vides, canal unique) |

---

## 3. Architecture

### 3.1 — Service : `BaseBillet/reports.py`

Classe `RapportBilletterieService` initialisée avec un `Event`. Chaque méthode retourne un dict sérialisable JSON. Calcul temps réel à chaque affichage (pas de snapshot — les données d'un event terminé ne bougent plus).

```
RapportBilletterieService(event)
│
├── calculer_synthese()
│   Jauge max, billets vendus (Ticket status K+S), scannés (S), no-show (K après event),
│   CA TTC total (LigneArticle VALID uniquement), remboursements (REFUNDED), CA net (TTC - remb).
│   Retourne aussi les données pour la progress bar (taux remplissage).
│
├── calculer_courbe_ventes()
│   LigneArticle VALID groupées par jour (datetime__date), cumulées.
│   Retourne labels (dates) + datasets (count cumulé, CA cumulé).
│   Format Chart.js ready.
│
├── calculer_ventes_par_tarif()
│   GROUP BY pricesold__price__uuid.
│   Pour chaque tarif : nom, vendus, offerts (payment_method=FREE), CA TTC, HT, TVA, remboursés.
│   Calcul HT : TTC / (1 + taux_tva/100). Taux TVA depuis LigneArticle.vat.
│
├── calculer_par_moyen_paiement()
│   GROUP BY payment_method.
│   Pour chaque moyen : label humain (PaymentMethod.label), montant, %, nb billets.
│
├── calculer_par_canal()
│   GROUP BY sale_origin.
│   Pour chaque canal : label humain (SaleOrigin.label), nb billets, montant.
│   Retourne None si un seul canal (section masquée).
│
├── calculer_scans()
│   Ticket counts par status (K, S, R).
│   Tranches horaires 30min depuis scanned_at pour le bar chart.
│   Retourne None pour les tranches si aucun scanned_at renseigné.
│
├── calculer_codes_promo()
│   GROUP BY promotional_code.
│   Pour chaque code : nom, utilisations, taux réduction, manque à gagner.
│   Manque à gagner = prix_catalogue (pricesold.price.prix) - prix_payé (amount).
│   Retourne None si aucun code promo utilisé.
│
└── calculer_remboursements()
    LigneArticle status=REFUNDED + credit_note_for.
    Nombre, montant total, taux de remboursement (remboursés / vendus).
```

**Source de données principale :** `LigneArticle.objects.filter(reservation__event=event)`

Le queryset de base est construit dans `__init__` avec les `select_related` nécessaires :
```python
self.lignes = LigneArticle.objects.filter(
    reservation__event=event,
).select_related(
    'pricesold__price__product',
    'pricesold__productsold',
    'promotional_code',
    'reservation',
)
```

Les Tickets sont requêtés séparément pour les scans :
```python
self.tickets = Ticket.objects.filter(
    reservation__event=event,
)
```

### 3.2 — Admin : page dédiée via `get_urls()`

URLs ajoutées à EventAdmin :
```
/admin/basebillet/event/{uuid}/bilan/        → page rapport complète
/admin/basebillet/event/{uuid}/bilan/pdf/    → export PDF (WeasyPrint)
/admin/basebillet/event/{uuid}/bilan/csv/    → export CSV
```

**Accès depuis la changelist :** colonne "Bilan" avec lien-icône (Material Symbol `assessment`). Visible si l'event a au moins 1 réservation.

**Accès depuis la fiche Event :** carte discrète dans `change_form_before_template` avec lien "Voir le bilan".

**Permissions :** `TenantAdminPermissionWithRequest(request)` — mêmes droits que EventAdmin.

### 3.3 — Templates

```
Administration/templates/admin/event/
├── bilan.html                  → page complète (extends unfold layout)
├── bilan_pdf.html              → version WeasyPrint (pas de JS)
├── bilan_link_changelist.html  → colonne lien dans la changelist
├── bilan_link_changeform.html  → carte lien dans change_form_before
└── partials/
    ├── synthese.html           → card + progress bar + line chart
    ├── ventes_tarif.html       → tableau
    ├── moyens_paiement.html    → tableau
    ├── canaux_vente.html       → tableau (conditionnel)
    ├── scans.html              → stats + bar chart affluence
    └── codes_promo.html        → tableau (conditionnel)
```

**Composants Unfold utilisés :**
- `unfold/components/card.html` — conteneur de chaque section
- `unfold/components/chart/line.html` — courbe de ventes cumulées
- `unfold/components/chart/bar.html` — affluence par tranche horaire
- `unfold/components/progress.html` — jauge de remplissage

**Styles :** inline uniquement (pas de Tailwind custom dans Unfold). Variables CSS Unfold pour les couleurs (`var(--color-primary-600)`, etc.).

### 3.4 — Migration

Un seul champ ajouté :

```python
# BaseBillet/models.py — classe Ticket
scanned_at = models.DateTimeField(
    null=True,
    blank=True,
    help_text=_("Date et heure du scan / Date and time of scan"),
)
```

Modification du code de scan : quand `Ticket.status` passe de `K` à `S`, écrire `ticket.scanned_at = timezone.now()`.

Les tickets déjà scannés conservent `scanned_at=None` — la courbe d'affluence ne fonctionne que pour les scans futurs. Acceptable.

---

## 4. Contenu détaillé des 6 sections

### 4.1 — Synthèse

```
┌── SYNTHÈSE ──────────────────────────────────────────────────────┐
│  [progress bar ████████████████░░░░  84,6 %]                     │
│  Jauge : 500 — Vendus : 423 — Scannés : 387 — No-show : 36     │
│                                                                  │
│  CA TTC :     4 230,00 €                                        │
│  Remboursements : -120,00 €                                     │
│  CA net :     4 110,00 €                                        │
│                                                                  │
│  [line chart ── courbe de ventes cumulées J-30 → J]              │
└──────────────────────────────────────────────────────────────────┘
```

**Courbe de ventes :**
- Axe X : dates (jour par jour)
- Axe Y gauche : nombre de billets (cumulé)
- Dataset unique, format Chart.js natif Unfold

**Billets vendus :** `Ticket.objects.filter(reservation__event=event, status__in=[NOT_SCANNED, SCANNED]).count()`

### 4.2 — Ventes par tarif

```
┌── VENTES PAR TARIF ──────────────────────────────────────────────┐
│  Tarif            Vendus  Offerts  CA TTC    HT       TVA  Remb. │
│  ────────────────────────────────────────────────────────────────│
│  Plein tarif        300       0   3 000 €  2 727 €   273 €    2  │
│  Réduit             100       0     800 €    727 €    73 €    8  │
│  Invitation           0      23       0 €      0 €     0 €    2  │
│  ────────────────────────────────────────────────────────────────│
│  TOTAL              400      23   3 800 €  3 454 €   346 €   12  │
└──────────────────────────────────────────────────────────────────┘
```

**Query :**
```python
LigneArticle.objects.filter(
    reservation__event=event,
    status__in=[VALID, REFUNDED],
).values(
    'pricesold__price__uuid',
    'pricesold__price__name',
).annotate(
    vendus=Count('uuid', filter=~Q(payment_method='NA') & Q(status=VALID)),
    offerts=Count('uuid', filter=Q(payment_method='NA', status=VALID)),
    ca_ttc=Sum('amount', filter=Q(status=VALID)),
    rembourses=Count('uuid', filter=Q(status=REFUNDED)),
)
```

**Calcul HT/TVA :** par ligne, pas en agrégé (chaque ligne a son propre `vat`).

### 4.3 — Par moyen de paiement

Tableau simple. Labels humains via `PaymentMethod(code).label`.
Pourcentage = montant du moyen / CA TTC total × 100.

### 4.4 — Par canal de vente

Tableau simple. Labels humains via `SaleOrigin(code).label`.
**Conditionnel :** masqué si un seul canal de vente sur toutes les lignes de l'event.

### 4.5 — Scans / Affluence

```
┌── SCANS ─────────────────────────────────────────────────────────┐
│  Scannés :          387  (91,5 %)                                │
│  Non scannés :       36   (8,5 %)                                │
│  Annulés :           12                                          │
│                                                                  │
│  [bar chart ── affluence par tranche de 30 min]                  │
│  ▐█▌                                                             │
│  ▐██▌    ▐█▌                                                     │
│  ▐███▌   ▐██▌  ▐█▌                                               │
│  19h00  19h30  20h00  20h30  21h00                               │
└──────────────────────────────────────────────────────────────────┘
```

**Tranches 30 min :** Django n'a pas de `Trunc30Min`. On utilise `ExtractHour` + `ExtractMinute` avec floor à 30 :
```python
# Pseudo-code — la query exacte sera affinée à l'implémentation
tickets_scannes.annotate(
    heure=ExtractHour('scanned_at'),
    demi=Case(
        When(minute__lt=30, then=Value(0)),
        default=Value(30),
    ),
).values('heure', 'demi').annotate(count=Count('uuid')).order_by('heure', 'demi')
```

**Bar chart masqué** si aucun `scanned_at` renseigné (tickets scannés avant la migration).

### 4.6 — Codes promo

Tableau conditionnel (masqué si aucun code promo utilisé).

**Manque à gagner :** `prix_catalogue - prix_payé` pour chaque LigneArticle avec un `promotional_code`. Le prix catalogue vient de `pricesold.price.prix` (converti en centimes), le prix payé de `LigneArticle.amount`.

---

## 5. Exports

### 5.1 — PDF (WeasyPrint)

- Template `bilan_pdf.html` — même contenu que la page admin, sans graphiques JS
- Les graphiques sont remplacés par leurs données tabulaires (la courbe de ventes devient un tableau jour/vendus/CA)
- CSS print : A4 paysage, marges 15mm, police sans-serif
- En-tête : nom event, date, lieu, logo structure (si dispo)
- Pied : "Généré par TiBillet le {date}"
- Généré à la volée, pas stocké

### 5.2 — CSV

- Délimiteur `;`, UTF-8 BOM (Excel français)
- Sections séparées par ligne vide + titre de section en majuscules
- Nombres décimaux avec point (pas virgule) — c'est un CSV, pas un affichage
- Monnaie en euros, 2 décimales
- Généré à la volée, pas stocké

---

## 6. Tests

### pytest (DB-only)

- `test_rapport_billetterie_service.py` — tests du service :
  - Event sans ventes → tous les compteurs à 0
  - Event avec ventes mixtes (plein/réduit/gratuit) → vérifier synthèse, tarifs, moyens
  - Remboursements → vérifier le CA net et le taux
  - Codes promo → vérifier le manque à gagner
  - Scans avec `scanned_at` → vérifier les tranches horaires
  - Multi-canal (Lespass + LaBoutik) → vérifier la ventilation

- `test_bilan_admin_views.py` — tests des vues admin :
  - Accès à la page bilan (200)
  - Accès non autorisé (403/302)
  - Export PDF (content-type application/pdf)
  - Export CSV (content-type text/csv, vérifier le contenu)
  - Event sans réservation → page bilan affiche "Aucune donnée"

### E2E (Playwright)

- Navigation vers la changelist events → clic sur le lien Bilan → page s'affiche
- Vérifier la présence des 6 sections (data-testid)
- Clic Export PDF → téléchargement déclenché
- Clic Export CSV → téléchargement déclenché

---

## 7. Fichiers à créer / modifier

| Fichier | Action |
|---|---|
| `BaseBillet/reports.py` | **Créer** — `RapportBilletterieService` |
| `BaseBillet/models.py` | **Modifier** — ajouter `scanned_at` sur Ticket |
| `BaseBillet/migrations/XXXX_ticket_scanned_at.py` | **Créer** — migration |
| `Administration/admin/events.py` | **Modifier** — `get_urls()`, colonne bilan, `change_form_before_template` |
| `Administration/templates/admin/event/bilan.html` | **Créer** |
| `Administration/templates/admin/event/bilan_pdf.html` | **Créer** |
| `Administration/templates/admin/event/bilan_link_*.html` | **Créer** (2 fichiers) |
| `Administration/templates/admin/event/partials/*.html` | **Créer** (6 fichiers) |
| Code de scan (à localiser) | **Modifier** — ajouter `scanned_at = timezone.now()` |
| `tests/pytest/test_rapport_billetterie_service.py` | **Créer** |
| `tests/pytest/test_bilan_admin_views.py` | **Créer** |
| `tests/e2e/test_bilan_billetterie.py` | **Créer** |

---

## 8. Ce qui est explicitement hors périmètre

- Agrégation multi-events / par période
- Export SIBIL (sous-projet 2)
- Calculs fiscaux CNM/ASTP/TVA (sous-projet 3)
- Rapport par point de vente (c'est le job de laboutik)
- Dashboard temps réel avec WebSocket (la page se rafraîchit au reload)
- Graphique de comparaison entre events
- HelloAsso comme SaleOrigin dédié (les ventes HelloAsso arrivent via EXTERNAL ou WEBHOOK)

---

## 9. Questions résolues

| Question | Réponse |
|---|---|
| Qui utilise le bilan ? | L'organisateur, dans l'admin Unfold |
| Quand ? | Avant (pilotage), pendant (suivi), après (bilan définitif) |
| Par event ou par période ? | Par event uniquement |
| Adaptation au cycle de vie ? | Naturelle — pas de machine à états |
| Graphiques ? | Oui, natifs Unfold (Chart.js inclus) |
| `scanned_at` ? | Oui, migration incluse |
| Exports ? | PDF + CSV |
| Events hiérarchiques ? | Pas d'agrégation — chaque event a son propre bilan |
