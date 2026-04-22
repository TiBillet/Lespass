# Booking — Finding, Issues and Architecture Decisions

> **Convention :** ce document est en ajout uniquement. Ne jamais
> renuméroter ni supprimer une section existante. Toujours ajouter à
> la fin.
> / **Convention:** append-only. Never renumber or remove an existing
> section. Always add at the end.

## §1. Annulation = suppression de la ligne de la table Booking (Futur)

**Source :** `booking/models.py` — classe `Booking`

L'annulation supprime la réservation. Pas de statut `cancelled`.

Risque : perte de traçabilité (litiges remboursement, analytics).
Migration future si besoin : ajouter `cancelled_at` (DateTimeField nullable).
Non-null = annulé, null = actif.

À prendre en compte après la v1.


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


## §4. Tags sur Resource et ResourceGroup — JSONField provisoire (Futur)

**Source :** `booking/models.py` — classes `Resource` et `ResourceGroup`

`tags = JSONField(default=list)` est un champ provisoire. Le système de tags
existant dans TiBillet (`BaseBillet.Tag`) est une vraie relation
`ManyToManyField` avec nom, slug et couleur — c'est ce qu'utilisent les
événements.

Migration future : remplacer le JSONField par un `ManyToManyField` vers
`BaseBillet.Tag`, comme sur `BaseBillet.Product`. Cela donnera un sélecteur
de tags dans l'admin et une cohérence avec le reste de la plateforme.

En attendant, le champ est masqué dans l'admin (non listé dans `fields`).


## §5. Traductions françaises du module booking (en attente)

**Source :** `locale/fr/LC_MESSAGES/django.po`

Le fichier PO contient des conflits git non résolus qui empêchent
`makemessages` de fonctionner. Les chaînes du module booking (verbose names,
help texts, statuts) ne sont donc pas encore traduites en français.

Action future : une fois les conflits résolus en amont, lancer
`python manage.py makemessages -l fr` puis ajouter les traductions
manquantes dans `locale/fr/LC_MESSAGES/django.po` et recompiler avec
`compilemessages`.


## §6. Formulaire de réservation dans l'admin (Futur)

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

Obsolète : cela a été précisé dans la spécification et implémenté


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
Obsolète : cela a été précisé dans la spécification et implémenté


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

Action future : ajouter des tests unitaires pour ces fonctions, en
conservant les tests d'intégration existants pour couvrir l'interaction
avec la base (fermetures réelles, ouvertures réelles, réservations réelles).

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

Action future : réécrire ces deux tests en définissant explicitement
`cal`, `wop` et leurs `OpeningEntry` inline, sans référence aux fixtures.
Les tests `pytest.skip` conditionnels disparaîtront en même temps.

Obsolète : les test ont été mise à jour


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

Action future : appliquer ce changement à `compute_slots` et
`validate_new_booking`, puis réécrire les tests de validation avec
des dates fixes.

Obsolète : les test ont été mise à jour


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

Obsolète : Cela a été implémenté.

## §15 - problème de performance sur calcul de dispo

les réservations (Booking) peuvent avoir des durées arbitraires.
Dans le modèle, il y a juste le datetime du début. Donc
Pour calculer les créneaux libres, il faut charger la totalité
des réservations puis calculer leur datetime de fin.

On peut éviter cela en ajouter la datetime de fin de chaque
réservation en BDD. Attention : c'est une donnée qui sera redondante
avec la durée des slot et leur nombre.

## §16 - problème début des créneaux à l'heure pret

Il faut prendre en compte l'heure dans la fenetre de calcul
des créneaux ouvert.

## §16 - manque des tags dans le fixture

Il faut ajouter les tags "salle" et "machine" par exemple.


## §17 - vue des réservations 

Y'a aucune raison pour que ca soit dans /my_account/my_resources/
plutot que /booking/SOMETHING

Suffit de mettre un lien dans /my_account qui amène vers la bonne
page de booking


## §18 - mise à jour vue des booking

ca ne se met pas à jour immédiatement lorsqu'on réserve plusieurs slots
seul le slot cliqué se màj. Les suivants non


## §19 — Annulation en un clic — confirmation obligatoire selon la spec

**Source :** `booking/templates/booking/views/my_bookings.html`

La spec §7.3 est explicite : "the action should require a deliberate step —
not a single accidental click." Le bouton "Annuler" actuel déclenche le
`hx-post` immédiatement au clic, sans confirmation.

Action future : ajouter une étape de confirmation avant l'envoi de la
requête HTMX. Options envisageables : modale Bootstrap, bouton bascule
inline (un clic = affiche "Êtes-vous sûr ? Confirmer / Annuler"), ou
`hx-confirm` natif HTMX (simple mais non stylisable).


## §20 — Deadline d'annulation non affichée sur la page mes-réservations

**Source :** `booking/templates/booking/views/my_bookings.html`,
`booking/views.py` — `my_bookings()`

La spec §7.3 : "The deadline must be visible without entering a
cancellation flow." Le template n'affiche que `resource.name` et
`start_datetime`. La deadline (calculée comme
`start_datetime − cancellation_deadline_hours`) n'est visible qu'en
cas d'échec de l'annulation (réponse 422), pas avant.

Action future : calculer la deadline par réservation dans la vue
`my_bookings()` (annoter le queryset ou construire une liste de
tuples `(booking, deadline)`) et l'afficher dans chaque ligne de la
liste, par exemple : "Annulation possible jusqu'au mer. 29/04 14:00".


## §21 — Panier affiché sur la page mes-réservations — choix UX à arbitrer

**Source :** `booking/templates/booking/booking_base.html`

`booking_base.html` inclut systématiquement `{% include "booking/partial/basket.html" %}`
en haut de toutes les vues du module, y compris `/booking/my-bookings/`.
La page mes-réservations est centrée sur les réservations `confirmed` ; le
panier (réservations `new`) n'est pas mentionné dans la spec §7.3 pour cette
vue.

Question ouverte : le panier doit-il apparaître sur la page
mes-réservations ? Arguments pour : cohérence visuelle dans le module,
le membre voit tout au même endroit. Arguments contre : charge cognitive
inutile sur une page de gestion, risque d'interaction concurrente entre
le bouton "Retirer du panier" et le bouton "Annuler" si les deux sont
déclenchés simultanément (requête abandon silencieuse via HX-Redirect).

Décision à prendre avec l'équipe avant la finalisation du template.


## §22 — Filtre "à venir" trop strict — réservations en cours et passées masquées

**Source :** `booking/views.py` — `my_bookings()`

Le queryset filtre `start_datetime__gt=now()` : une réservation disparaît
de la liste à la seconde où elle commence. Un membre qui a réservé une
salle de 14h à 16h ne la voit plus à 14h01, alors qu'il l'occupe encore.

La spec dit "upcoming confirmed bookings" sans définir le seuil précisément.
L'utilisateur souhaite également afficher les réservations passées récentes.

Action future : ajuster le filtre pour inclure les réservations en cours
et éventuellement un historique. Options :
- Filtrer par `end_datetime > now()` une fois `end_datetime` disponible en
  base (voir §15 sur la redondance) ;
- Ou séparer l'affichage : section "À venir / en cours" +
  section "Passées" (30 derniers jours par exemple), chacune avec son filtre.
- Le filtre actuel peut rester pour la section "à venir" mais une section
  "aujourd'hui" ou "en cours" devrait afficher les créneaux démarrés et
  non encore terminés.


## §23 — compute_slots appelé sans contrainte de date dans booking_form et cancel_form (Connu, non bloquant)

**Source :** `booking/views.py` — `booking_form()` et ancienne version de
`cancel_form()` (résolue dans cancel_form — voir ci-dessous)

`compute_slots(ressource)` est appelé sans passer de fenêtre de dates
explicite. La fonction calcule les créneaux sur la plage
`[aujourd'hui, aujourd'hui + booking_horizon_days]`. Pour une ressource
avec `booking_horizon_days=365` et des créneaux de 30 minutes, cela
peut générer plusieurs milliers d'intervalles par requête. La liste est
ensuite parcourue linéairement pour trouver un seul créneau.

**cancel_form résolu :** depuis la refonte du `cancel_form` (avril 2026),
cette vue ne fait plus appel à `compute_slots`. Elle reconstruit le
`BookableInterval` directement depuis les paramètres GET encodés au
moment du rendu du formulaire — coût O(1).

**booking_form non résolu :** `booking_form` et `add_to_basket` appellent
toujours `compute_slots` en entier. À surveiller si les ressources ont
des horizons longs (> 90 jours) et des durées de créneau courtes.

Action future possible :
- Passer une fenêtre `[start_datetime - 1 jour, start_datetime + 1 jour]`
  à `compute_slots` quand on cherche un créneau précis (booking_form,
  add_to_basket) — réduit le calcul à quelques créneaux.
- Ou accepter le coût si les horizons restent ≤ 30 jours en pratique.
