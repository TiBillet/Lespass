# Booking — Findings archivés / Archived Findings

> Sections déplacées depuis `tibillet-booking-finding.md` car le problème
> est résolu ou précisé dans la spécification.
> / Sections moved from `tibillet-booking-finding.md` because the issue
> is resolved or clarified in the spec.
>
> Les numéros de section sont inchangés.
> / Section numbers are unchanged.

---

## §2. start_datetime est un DateTimeField timezone-aware (Obsolète)

**Source :** `booking/models.py` — classe `Booking`

Le champ `start_datetime` est un `DateTimeField` (pas `DateField` + `TimeField`
séparés). TiBillet définit un fuseau horaire par tenant dans la configuration —
toutes les dates de réservation doivent être timezone-aware. `timezone.now()`
et `django.utils.timezone` sont les seuls outils à utiliser pour manipuler ce
champ.

Obsolète : cela a été précisé dans la spécification.


## §3. Capacity = 0 autorisé (Obsolète)

**Source :** `booking/models.py` — classe `Resource`

Capacity=0 désactive silencieusement les réservations sans toucher au
Calendar ni au WeeklyOpening. Le slot engine vérifie `remaining_capacity > 0`
— pas besoin d'un flag `is_active` séparé.

Obsolète : cela a été précisé dans la spécification.


## §7. Règle de génération des créneaux de plusieurs jours (Obsolète)

**Source :** `booking/slot_engine.py` — `generate_theoretical_slots`

Un créneau est généré **uniquement si chaque jour qu'il intersecte est
ouvert** (absent des `closed_dates`). Un créneau peut durer plusieurs
jours tant qu'aucun de ces jours n'est fermé.

Vérification : pour chaque slot généré, itérer de `start_datetime.date()`
à `end_datetime.date()` inclus et vérifier qu'aucune de ces dates n'est
dans `closed_dates`. Si l'un de ces jours est fermé, le slot est exclu.

Conséquences :
- Un créneau qui déborde sur le lendemain fermé est exclu.
- Un créneau multi-jours dont un jour du milieu est fermé est exclu.
- Un créneau multi-jours dont tous les jours sont ouverts est **retourné**.
- La vérification se fait **slot par slot** (pas sur la date de l'entry) :
  un `OpeningEntry` peut produire des slots dont le `start_datetime.date()`
  diffère de la date de l'entry (bleed-over) — chaque slot est évalué
  indépendamment.

Obsolète : cela a été précisé dans la spécification.


## §8. Contrainte manquante sur ClosedPeriod.end_date (Obsolète)

**Source :** `booking/models.py` — classe `ClosedPeriod`

Le modèle `ClosedPeriod` n'a actuellement **aucune contrainte** qui empêche
`end_date` d'être antérieure à `start_date`. Une période avec
`start_date=2026-06-10` et `end_date=2026-06-08` est acceptée en base sans
erreur. Le slot engine (`get_closed_dates_for_resource`) itère de `start`
à `end` : si `end < start`, la boucle ne s'exécute jamais et la fermeture
est silencieusement ignorée.

Action à faire : ajouter une validation dans `ClosedPeriod.clean()` :

```python
def clean(self):
    if self.end_date is not None and self.end_date < self.start_date:
        raise ValidationError(
            _('End date must be equal to or later than start date.')
        )
```

Ajouter également un test dans `booking/tests/test_models.py`.

Option complémentaire : ajouter une contrainte base de données via
`Meta.constraints` avec `CheckConstraint` pour garantir l'intégrité même
en dehors de Django (imports directs, migrations, shell).

```python
class Meta:
    constraints = [
        models.CheckConstraint(
            check=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F('start_date')),
            name='closed_period_end_date_gte_start_date',
        )
    ]
```

Obsolète : cela a été précisé dans la spécification et implémenté.


## §9. Durée totale d'un OpeningEntry ne doit pas dépasser une semaine (Obsolète)

**Source :** `booking/models.py` — classe `OpeningEntry`

La durée totale d'un `OpeningEntry` est
`slot_duration_minutes × slot_count`. Si cette valeur dépasse
`WEEK_MINUTES` (10 080 min = 7 × 24 × 60), l'entry « déborde sur
elle-même » : le dernier slot empiète sur le prochain cycle hebdomadaire
du même entry, créant un chevauchement logique de l'opening avec lui-même.

La contrainte de non-chevauchement inter-entries (`OpeningEntry.clean()`,
voir session 2) détecte déjà les débordements excessifs dans certains cas,
mais elle ne garantit pas explicitement que la durée totale d'un seul entry
reste ≤ `WEEK_MINUTES`.

Action future : ajouter dans `OpeningEntry.clean()` :

```python
if self.slot_duration_minutes * self.slot_count > WEEK_MINUTES:
    raise ValidationError(
        _('Total duration (slot_duration_minutes × slot_count) '
          'must not exceed one week (%(week)d minutes).')
        % {'week': WEEK_MINUTES}
    )
```

Obsolète : cela a été précisé dans la spécification et implémenté.


## §10. Tests d'intégration uniquement — des tests unitaires seraient bénéfiques (Obsolète)

**Source :** `booking/tests/`

Tous les tests actuels sont des tests d'intégration : ils accèdent à la
base de données via `schema_context('lespass')` et testent les fonctions
à travers la pile complète (modèles Django, ORM, contraintes DB).

Cette approche garantit que le comportement réel en base est correct, mais
elle présente deux limites pour les modules à forte logique algorithmique :

- **Lenteur** : chaque test effectue des requêtes DB, même pour des fonctions
  pures.
- **Couplage** : un échec peut venir de la DB, du modèle ou de l'algorithme —
  le diagnostic est moins direct.

Les fonctions pures de `booking/booking_engine.py` bénéficieraient d'une
stratégie mixte : `compute_open_intervals`, `generate_theoretical_slots` et
`compute_remaining_capacity` n'ont pas d'accès DB. Des tests unitaires avec
des objets Python simples (`types.SimpleNamespace`) permettraient de cibler
l'algorithme seul.

Obsolète : `test_booking_engine.py` a été réécrit avec une stratégie mixte.
Les fonctions pures sont couvertes par des tests unitaires sans DB
(`_cp`/`_oe`/`_bk` SimpleNamespace, `PARIS_TZ` injecté). Les
orchestrateurs (`compute_slots`, `validate_new_booking`) conservent leurs
tests d'intégration.


## §11. Ambiguïté dans la spec — alignement des réservations sur les créneaux (Obsolète)

**Source :** `booking/doc/tibillet-booking-spec.md` — section 5 (Business Rules)

La spec indique : "Bookings are not required to be aligned with computed
slots." Cette phrase est ambiguë : elle décrit le comportement du
volontaire (admin), pas du membre (interface publique).

La règle correcte est :

- **Membre** (interface publique) : chaque créneau réservé doit être
  exactement l'un des intervalles calculés dans **E** (issu du
  `WeeklyOpening`). L'alignement est garanti par construction — le membre
  sélectionne un créneau affiché, il ne saisit pas un `[p, q)` arbitraire.
- **Volontaire** (admin Django) : aucune contrainte d'alignement. Le
  volontaire peut créer une réservation ad hoc à n'importe quelle heure
  et durée, indépendamment du `WeeklyOpening`.

Obsolète : la distinction membre / volontaire est désormais documentée
dans `§3.2.4 B` (spec v0.6) et dans la section 5 "Business Rules /
Availability" de la spec. Le `booking_validator.py` implémente la règle
membre — il ne doit pas être utilisé pour valider les réservations créées
par un volontaire via l'admin.


## §12. Tests couplés aux fixtures — `test_slot_engine.py` (Obsolète)

**Source :** `booking/tests/test_slot_engine.py` — fonctions
`test_compute_slots_end_to_end_with_fixture_coworking_resource` et
`test_compute_slots_end_to_end_with_fixture_petite_salle`

Ces deux tests ne construisent pas leurs propres données : ils lisent
directement les ressources `"Coworking"` et `"Petite salle"` depuis la
base via `Resource.objects.filter(name=...).first()`. Si la fixture est
absente, le test est ignoré (`pytest.skip`). Si la fixture est modifiée
(ajout d'une entrée, changement d'horaire, changement de capacité), le
test peut passer silencieusement avec des assertions devenues fausses.

Ce couplage viole le principe d'isolation des tests : un test doit
définir inline toutes les données dont il dépend pour être reproductible
indépendamment de l'état de la base.

Obsolète : les tests ont été mis à jour.


## §13. 💡 Clock injection dans `compute_slots` et `validate_new_booking` (Obsolète)

**Source :** `booking/slot_engine.py:376`, `booking/booking_validator.py`

`compute_slots` appelle `timezone.localdate()` en interne pour calculer
`horizon_end = today + booking_horizon_days`. Ce couplage au clock système
force les tests de `validate_new_booking` à utiliser des dates relatives
(`next_weekday`) plutôt que des dates fixes, ce qui rend le catalogue de
tests moins lisible et les assertions moins précises.

Le pattern **clock injection** résout ce problème : ajouter un paramètre
optionnel `reference_date=None` à `compute_slots` (et en cascade à
`validate_new_booking`). En production, `reference_date=None` → la
fonction utilise `timezone.localdate()` comme aujourd'hui. Dans les
tests, `reference_date="2026-06-01"` → toutes les dates deviennent
statiques et les `next_weekday` disparaissent.

```python
def compute_slots(resource, date_from, date_to, reference_date=None):
    today = reference_date or timezone.localdate()
    horizon_end = today + datetime.timedelta(days=resource.booking_horizon_days)
    ...
```

Aucun site d'appel en production n'est modifié (paramètre optionnel).

Obsolète : les tests ont été mis à jour.


## §14. ⚠️ MAJEUR — Race condition sur la capacité restante (Obsolète)

**Source :** `booking/doc/tibillet-booking-spec.md` — section 3.2.4 (B)

E est calculé à partir d'un snapshot de la base au moment de la
requête. Deux requêtes HTTP concurrentes qui demandent le dernier
créneau disponible (`remaining_capacity = 1`) peuvent toutes les deux
passer la validation et créer chacune une réservation — laissant la
ressource en sur-réservation (`remaining_capacity = -1`).

La règle `B ⊆ E'` est une vérification correcte mais pas atomique :
entre le moment où E' est calculé et le moment où la ligne `Booking`
est insérée, un autre processus peut avoir consommé la capacité.

Action à faire : re-vérifier `remaining_capacity` à l'intérieur d'une
transaction base de données avec un verrou au niveau de la ligne sur
les créneaux concernés, juste avant d'insérer la réservation. En
Django, le pattern recommandé est :

```python
from django.db import transaction

with transaction.atomic():
    # Re-calcule remaining_capacity avec SELECT FOR UPDATE
    # sur les réservations existantes qui chevauchent le créneau
    overlapping_count = (
        Booking.objects
        .select_for_update()
        .filter(
            resource=resource,
            start_datetime__lt=slot_end,
            end_datetime__gt=slot_start,
            status__in=['new', 'validated', 'confirmed'],
        )
        .count()
    )
    if overlapping_count >= resource.capacity:
        raise ValidationError(_('This slot is no longer available.'))
    Booking.objects.create(...)
```

Sans ce verrou, la contrainte de capacité n'est pas garantie sous
charge concurrente.

Obsolète : cela a été implémenté.


## §4. Tags sur Resource et ResourceGroup — OBSOLÈTE

**Source :** `booking/models.py` — classes `Resource` et `ResourceGroup`

`tags = JSONField(default=list)` est un champ provisoire. Le système de tags
existant dans TiBillet (`BaseBillet.Tag`) est une vraie relation
`ManyToManyField` avec nom, slug et couleur — c'est ce qu'utilisent les
événements.

Migration future : remplacer le JSONField par un `ManyToManyField` vers
`BaseBillet.Tag`, comme sur `BaseBillet.Product`. Cela donnera un sélecteur
de tags dans l'admin et une cohérence avec le reste de la plateforme.

En attendant, le champ est masqué dans l'admin (non listé dans `fields`).

**Obsolète (avril 2026) :** les tags sont supprimés entièrement du module
booking (migration 0003). Ce n'est pas un report à plus tard mais une
suppression définitive. Les tags sont hors périmètre (voir spec §9).


## §15 - problème de performance sur calcul de dispo — RÉSOLU

Les réservations (Booking) peuvent avoir des durées arbitraires.
Dans le modèle, il y a juste le datetime du début. Pour calculer les
créneaux libres, il faut charger la totalité des réservations puis
calculer leur datetime de fin.

On peut éviter cela en ajoutant la datetime de fin de chaque réservation
en BDD. Attention : c'est une donnée redondante avec la durée des slots
et leur nombre.

**État antérieur :** `get_existing_bookings_for_resource` chargeait
toutes les réservations sans filtre de date. L'ancien filtre
`start_datetime__date__range` était incomplet (manquait les réservations
démarrant avant la fenêtre mais s'étendant à l'intérieur).

**Résolu (avril 2026) :** `end_datetime` ajouté au modèle `Booking`
(migration 0004). Calculé automatiquement par `Booking.save()` —
jamais écrit directement. `get_existing_bookings_for_resource` accepte
maintenant un paramètre `window` optionnel et applique le filtre exact
`start_datetime < window.end AND end_datetime > window.start` quand il
est fourni. Les deux points d'appel (`compute_slots` et
`validate_new_booking`) passent leur fenêtre respective.


## §16 - problème début des créneaux à l'heure près — RÉSOLU

Il faut prendre en compte l'heure dans la fenêtre de calcul des créneaux
ouverts.

**Résolu :** `compute_slots` utilise une fenêtre `Interval` avec un
`start` timezone-aware qui inclut l'heure courante, pas seulement la
date. Les créneaux déjà commencés sont exclus.


## §16b - manque des tags dans le fixture — OBSOLÈTE

Il faut ajouter les tags "salle" et "machine" par exemple.

**Obsolète (avril 2026) :** les tags sont supprimés entièrement (voir §4).
Note : deux sections portaient le numéro §16 par erreur. La seconde
est renommée §16b pour respecter la convention append-only.


## §17 - vue des réservations — RÉSOLU

Y'a aucune raison pour que ça soit dans /my_account/my_resources/
plutôt que /booking/SOMETHING. Suffit de mettre un lien dans /my_account
qui amène vers la bonne page de booking.

**Résolu (avril 2026) :** la vue des réservations est à
`/booking/my-bookings/` (spec v0.1, `BookingViewSet.my_bookings()`).


## §18 - mise à jour vue des booking — OBSOLÈTE

Ça ne se met pas à jour immédiatement lorsqu'on réserve plusieurs slots :
seul le slot cliqué se màj, les suivants non.

**Obsolète (avril 2026) :** ce problème était lié à l'approche HTMX
inline avec OOB swap. En v0.1, les réservations utilisent une navigation
pleine page — il n'y a plus de mise à jour partielle à gérer.


## §19 — Annulation en un clic — RÉSOLU en v0.1

**Source :** `booking/templates/booking/views/my_bookings.html`

La spec §7.3 est explicite : "the action should require a deliberate step
— not a single accidental click." Le bouton "Annuler" déclenchait le
`hx-post` immédiatement au clic, sans confirmation.

**Résolu (avril 2026) :** en v0.1, l'annulation passe par une page
dédiée (`/booking/cancel/<booking_pk>/`) avec un formulaire GET + POST
explicite. L'étape de confirmation est structurelle — pas un seul clic.


## §20 — Deadline d'annulation non affichée — RÉSOLU en v0.1

**Source :** `booking/templates/booking/views/my_bookings.html`

La spec §7.3 : "The deadline must be visible without entering a
cancellation flow." Le template n'affichait que `resource.name` et
`start_datetime`. La deadline n'était visible qu'en cas d'échec de
l'annulation (réponse 422), pas avant.

**Résolu (avril 2026) :** en v0.1, la deadline est affichée sur la page
de confirmation d'annulation (`/booking/cancel/<booking_pk>/`), avant
que l'utilisateur confirme. Si la deadline est déjà passée, la page
l'indique explicitement et n'affiche pas de formulaire.


## §21 — Panier affiché sur la page mes-réservations — OBSOLÈTE

**Source :** `booking/templates/booking/booking_base.html`

`booking_base.html` incluait systématiquement le panier en haut de toutes
les vues, y compris `/booking/my-bookings/`. Question ouverte : le panier
devait-il apparaître sur cette page ?

**Obsolète (avril 2026) :** le panier est supprimé en v0.1. La question
ne se pose plus jusqu'à l'intégration du système de paiement (v0.2+).


## §22 — Filtre "à venir" trop strict — RÉSOLU en v0.1

**Source :** `booking/views.py` — `my_bookings()`

Le queryset filtrait `start_datetime__gt=now()` : une réservation
disparaissait de la liste à la seconde où elle commençait.

**Résolu (avril 2026) :** `end_datetime` est maintenant disponible en
base (migration 0004, voir §15). La vue `my_bookings()` utilisera
`end_datetime > now()` pour la section "à venir / en cours" et
`end_datetime <= now()` pour la section "passées". Les deux sections
sont spécifiées dans `booking/doc/ui/views/my-bookings.md`.


## §23 — compute_slots appelé sans contrainte de date — RÉSOLU

**Source :** `booking/views.py`

Les vues qui ne cherchaient qu'un seul créneau scannaient l'horizon
entier inutilement.

**Résolu :** toutes les vues concernées passent maintenant une fenêtre
`Interval` à `compute_slots`. Rendu possible par l'introduction du
paramètre `window: Interval` sur `compute_slots`.
