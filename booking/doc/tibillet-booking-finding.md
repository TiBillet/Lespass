# Booking — Finding, Issues and Architecture Decisions

> **Convention :** ce document est en ajout uniquement. Ne jamais
> renuméroter ni supprimer une section existante. Toujours ajouter à
> la fin.
> / **Convention:** append-only. Never renumber or remove an existing
> section. Always add at the end.

## §1. Annulation = suppression de la ligne de la table Booking

**Source :** `booking/models.py` — classe `Booking`

L'annulation supprime la réservation. Pas de statut `cancelled`.

Risque : perte de traçabilité (litiges remboursement, analytics).
Migration future si besoin : ajouter `cancelled_at` (DateTimeField nullable).
Non-null = annulé, null = actif.

## §2. start_datetime est un DateTimeField timezone-aware

**Source :** `booking/models.py` — classe `Booking`

Le champ `start_datetime` est un `DateTimeField` (pas `DateField` + `TimeField`
séparés). TiBillet définit un fuseau horaire par tenant dans la configuration —
toutes les dates de réservation doivent être timezone-aware. `timezone.now()`
et `django.utils.timezone` sont les seuls outils à utiliser pour manipuler ce
champ.

## §3. Capacity = 0 autorisé

**Source :** `booking/models.py` — classe `Resource`

Capacity=0 désactive silencieusement les réservations sans toucher au
Calendar ni au WeeklyOpening. Le slot engine vérifie `remaining_capacity > 0`
— pas besoin d'un flag `is_active` séparé.

## §4. Tags sur Resource et ResourceGroup — JSONField provisoire

**Source :** `booking/models.py` — classes `Resource` et `ResourceGroup`

`tags = JSONField(default=list)` est un champ provisoire. Le système de tags
existant dans TiBillet (`BaseBillet.Tag`) est une vraie relation
`ManyToManyField` avec nom, slug et couleur — c'est ce qu'utilisent les
événements.

Migration future : remplacer le JSONField par un `ManyToManyField` vers
`BaseBillet.Tag`, comme sur `BaseBillet.Product`. Cela donnera un sélecteur
de tags dans l'admin et une cohérence avec le reste de la plateforme.

En attendant, le champ est masqué dans l'admin (non listé dans `fields`).

## §5. Traductions françaises du module booking — en attente

**Source :** `locale/fr/LC_MESSAGES/django.po`

Le fichier PO contient des conflits git non résolus qui empêchent
`makemessages` de fonctionner. Les chaînes du module booking (verbose names,
help texts, statuts) ne sont donc pas encore traduites en français.

Action future : une fois les conflits résolus en amont, lancer
`python manage.py makemessages -l fr` puis ajouter les traductions
manquantes dans `locale/fr/LC_MESSAGES/django.po` et recompiler avec
`compilemessages`.

## §6. Formulaire de réservation dans l'admin — ergonomie à améliorer

**Source :** `booking/admin.py` — classe `BookingAdmin`

Le formulaire actuel expose directement les champs bruts du modèle
(`start_datetime`, `slot_duration_minutes`, `slot_count`, etc.). Ce n'est pas
pratique pour un gestionnaire : il faut saisir une date/heure en ISO, un
nombre de minutes, un nombre de créneaux.

Amélioration future : remplacer le formulaire par un sélecteur de créneaux
calculés (liste déroulante des créneaux disponibles pour une ressource et une
date donnée, générée par le slot engine de la Session 5). Le formulaire
admin deviendrait alors cohérent avec l'interface publique de réservation.

Le champ `status` pose également problème : l'admin peut manuellement choisir
n'importe quel statut (`new`, `validated`, `confirmed`) sans passer par le
flux de paiement. Cela peut créer des incohérences (réservation marquée
`confirmed` sans paiement enregistré). À terme, le statut devrait être
en lecture seule dans l'admin, ou les transitions autorisées devraient être
limitées (ex : seul `confirmed → annulation` via suppression).

## §7. Règle de génération des créneaux — tous les jours intersectés doivent être ouverts

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

## §8. ⚠️ MAJEUR — Contrainte manquante sur ClosedPeriod.end_date

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

## §9. Durée totale d'un OpeningEntry ne doit pas dépasser une semaine

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

## §10. Tests d'intégration uniquement — des tests unitaires seraient bénéfiques

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

Les deux modules suivants bénéficieraient d'une stratégie mixte :

- `booking/slot_engine.py` — les fonctions `generate_theoretical_slots`,
  `compute_remaining_capacity` et `_slot_intersects_closed_date` sont pures
  (pas d'accès DB). Des tests unitaires avec des objets Python simples
  (dataclasses, listes) permettraient de cibler l'algorithme seul.

- `booking/booking_validator.py` — la logique de validation (parcours des
  créneaux, lookup par clé, vérification de capacité) est séparable de
  l'accès DB. Des tests unitaires pourraient construire des `Slot` factices
  et tester `validate_new_booking` sans passer par `compute_slots`.

Action future : ajouter des tests unitaires pour ces deux modules, en
conservant les tests d'intégration existants pour couvrir l'interaction
avec la base (fermetures réelles, ouvertures réelles, réservations réelles).

## §11. ⚠️ Ambiguïté dans la spec — alignement des réservations sur les créneaux

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

Action future : corriger la section 5 de la spec pour distinguer
explicitement les deux acteurs. Le `booking_validator.py` implémente
la règle membre — il ne doit pas être utilisé pour valider les
réservations créées par un volontaire via l'admin.

## §12. ⚠️ Tests couplés aux fixtures — `test_slot_engine.py`

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

Action future : réécrire ces deux tests en définissant explicitement
`cal`, `wop` et leurs `OpeningEntry` inline, sans référence aux fixtures.
Les tests `pytest.skip` conditionnels disparaîtront en même temps.

## §13. 💡 Clock injection dans `compute_slots` et `validate_new_booking`

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

Action future : appliquer ce changement à `compute_slots` et
`validate_new_booking`, puis réécrire les tests de validation avec
des dates fixes.
