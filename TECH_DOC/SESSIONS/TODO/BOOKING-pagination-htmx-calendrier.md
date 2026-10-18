# BOOKING — Calendrier d'une ressource : une semaine à la fois, en HTMX

> **Status :** spec du 2026-10-18, **validée par le mainteneur le 2026-10-18** (réponses au §5 :
> semaine en cours par défaut, pas de réservation à cheval sur deux semaines, templates orphelins
> supprimés, bug de minuit corrigé, pas de rafraîchissement après le panier).
> **Codée le 2026-10-18** : `CHANGELOG/2026-10-18-booking-calendrier-une-semaine.md`.
> **Consigne du mainteneur : pas de sur-ingénierie, conformité `djc` vérifiée (§12).**
> **Relue le 2026-10-18 par un agent Opus** (exactitude face au code, cas limites, tests, sur-ingénierie).
> Ses corrections sont intégrées : bug de fuseau de la fenêtre (§6.1), marge de fenêtre supprimée
> (inutile, §2.4), semaine par défaut sans boucle (D3), structure de la page (D11), JS (D13), tests (§9).
> **Pré-requis :** aucun. Le chantier « ressource bloquée par un événement »
> (`CHANGELOG/2026-10-18-event-champs-internes-ressource-bloquee.md`) est fait : la spec en tient compte.
> **Motif réutilisé :** la pagination par semaine du planning bénévole (chantier 7,
> `CHANGELOG/2026-10-17-benevolat-chantier-7-pagination-semaine.md`). Même app, même idée,
> mêmes fonctions : on ne réinvente rien.

---

## 1. Pourquoi ce chantier

La page de réservation d'une ressource (`GET /booking/<pk>/resource/`) **rend tout l'horizon de
réservation d'un coup**. Les boutons « semaine précédente / suivante » ne font que masquer ou
montrer, en JavaScript, des semaines déjà présentes dans la page. La vue mobile fait de même avec
un jour à la fois. Le tout est rendu **deux fois** (bloc desktop + bloc mobile).

Le poids de la page grandit donc avec l'horizon (mesures du 2026-10-18, base de dev) :

| Ressource | Horizon | Ouverture | HTML de la page |
|---|---|---|---|
| Petite salle #1 | 28 jours | samedi et dimanche, 3 créneaux | 285 Ko |
| Salle de résidence et concert | 90 jours | tous les jours, 2 créneaux | 2 Mo |
| Salle de résidence et concert | 550 jours | tous les jours, 2 créneaux | 8,7 Mo (un onglet Chrome s'est figé) |

Le **calcul** n'est pas le problème : `compute_slots` sur tout l'horizon prend de 7 à 23 ms par
ressource en dev. Le poids vient du **rendu** (gabarit + HTML envoyé + DOM).

**Objectif :** la page ne **rend qu'une semaine**. Changer de semaine recharge seulement la zone
du calendrier, en HTMX. Le poids ne dépend plus de l'horizon.

---

## 2. État actuel (code lu le 2026-10-18)

### 2.1 La vue — `booking/views.py`, `BookingViewSet.resource_page()` (l. ~347)

1. `compute_slots(resource)` **sans fenêtre** : tout l'horizon, de maintenant à
   `aujourd'hui + booking_horizon_days` (fenêtre par défaut, construite au fuseau du lieu).
2. `annotate_slots_for_display()` regroupe les créneaux contigus de même durée en
   `DisplaySlotGroup` (`booking/booking_engine.py`).
3. Marque `in_cart` sur les créneaux déjà dans le panier (`PanierSession`).
4. `_build_calendar_weeks(slot_groups)` → toutes les semaines (desktop) ; bornes horaires
   `min_hour` / `max_hour` calculées sur **tout** l'horizon.
5. `_build_mobile_days(slot_groups)` → tous les jours (mobile), avec leurs propres bornes horaires.
6. `mobile_day_bar` : un élément par jour **qui a des créneaux**.
7. `time_rows` : les lignes horaires de la grille desktop.
8. Rendu de `booking/views/resource.html` (page complète, via `booking/booking_base.html` qui étend
   `base_template` du skin).

Seuls les jours **qui ont au moins un créneau** apparaissent : une semaine sans créneau
(fermeture d'août, par exemple) n'existe pas dans la page.

### 2.2 Le gabarit — `booking/templates/booking/views/resource.html` (1037 lignes)

- `{% if calendar_weeks or mobile_days %}` (l. ~76 à ~790) englobe **tout** : le `<style>` du
  calendrier, `#booking-calendar` (qui porte `data-book-url`), les deux sélecteurs de ressource et
  la légende. Le `{% else %}` est l'état vide « Aucun créneau disponible prochainement. ».
- Bloc desktop (`d-none d-md-block`) : sélecteur de ressource **dans la carte** (l. ~498),
  navigation par semaine (`#calendar-prev-week`, `#calendar-next-week`, libellé
  `#calendar-week-label` calculé en JS), puis **une `div.calendar-week` par semaine**, toutes
  cachées sauf la première.
- Bloc mobile (`d-md-none`) : sélecteur **dans la carte** (l. ~631), barre de jours, **une
  `div.mobile-day` par jour**, toutes cachées sauf la première ; `.mobile-days` porte
  `aria-live="polite"` (l. ~695).
- Script en bas de page :
  - `showDesktopWeek()` et `showMobileDay()` masquent / montrent ;
  - le sélecteur de ressource redirige vers `/booking/<pk>/resource/` ;
  - un clic (ou Entrée / Espace) sur `.calendar-slot-free` ou `.mobile-slot-free` appelle
    `openBookingPopup()`. Celle-ci fait un `htmx.ajax('GET', <book>?start_datetime=…&group_end=…)`
    vers `#offcanvas-booking`, puis ouvre l'offcanvas `#bookingPanel`. Ce clic est **délégué** sur
    `#booking-calendar` : il survivra à un swap qui ne remplace que l'intérieur.
- La légende « Passé » n'a jamais d'équivalent dans la grille : aucun créneau passé n'est rendu
  (`generate_theoretical_slots` écarte ce qui commence avant la fenêtre). Défaut existant, hors sujet.

### 2.3 Le formulaire de réservation — `_book_get()` (l. ~463)

Il reçoit `start_datetime` et `group_end` (attribut `data-group-end` du créneau = fin de son
`DisplaySlotGroup`). Il recalcule les créneaux sur `[start_datetime, group_end)` et construit
`consecutive_slots` : les créneaux libres consécutifs, proposés dans le select « Heure de fin »
du formulaire (`max_slot_count` n'est plus affiché, `book_form.html` l. ~332-349 commentées).
**Sans `group_end`** (absent, ou illisible : le JS actuel envoie déjà `group_end=null` quand
l'attribut manque, et `parse_datetime('null')` renvoie `None`), il retombe sur tout l'horizon :
le résultat est exact, juste plus coûteux.

### 2.4 Le moteur — `booking/booking_engine.py`

- `compute_slots(resource, window, reference_now)` accepte une fenêtre. Il borne sa **fin** à
  l'horizon de la ressource, pas son début.
- **Le fuseau est tiré de la fenêtre** : `generate_theoretical_slots()` fait
  `tz = window.start.tzinfo` et `current_date = window.start.date()` ; `compute_open_intervals()`
  aussi. `compute_slots()` ne convertit au fuseau du lieu **que la fenêtre par défaut** (`now_local`),
  jamais une fenêtre passée en paramètre. **Une fenêtre doit donc être construite au fuseau du
  lieu** (voir §6.1).
- `OpeningEntry.clean()` (`booking/models.py` l. ~401-415) **refuse qu'un créneau finisse après
  minuit** (un créneau qui finit pile à minuit est accepté). L'admin passe par `full_clean`, les
  fixtures respectent la règle. **Une fenêtre `[lundi 0 h, lundi suivant 0 h)` contient donc tous
  les créneaux de la semaine** : aucune marge n'est nécessaire.
- Le blocage par un événement (`Event.ressource_bloquee`) est appliqué dans `compute_slots()` :
  une fenêtre d'une semaine en hérite.

### 2.5 Le panier

« Ajouter au panier » (`POST /panier/add/resource/`, `BaseBillet/views.py`, `add_resource`)
répond par `_render_badge_and_toast()` : badge + toast via l'en-tête `HX-Trigger` (événement
`panierToast`, envoyé aussi en cas d'erreur), avec `hx-swap="none"`. **Le calendrier n'est pas
rafraîchi** : le créneau reste « libre » à l'écran jusqu'au prochain chargement. Comportement
actuel ; ce chantier ne le change pas (voir Q3).

### 2.6 Code mort

`booking/templates/booking/views/resource_day.html` et
`booking/templates/booking/partials/resource_day_calendar.html` citent une méthode
`_render_resource_day_page()` qui n'existe plus (supprimée par le commit `2c99b791`
« Remove all booking day related codes »). Aucune vue ne les rend. Voir Q4.

### 2.7 Bug existant à ne pas attribuer à ce chantier

Un créneau qui finit à minuit donne `end_hour = 0` dans `_build_calendar_weeks` (l. ~117) et
`_build_mobile_days` (l. ~225) : `max_hour` est sous-estimé et le créneau déborde de la grille.
La « Salle de résidence et concert » des fixtures de démo (créneau 18 h – 24 h) le montre.
Hors périmètre (voir Q5) ; la vérification visuelle du chantier le verra.

### 2.8 Tests qui touchent la page

- `tests/e2e/test_panier_flow.py` (l. ~260) : ouvre `/booking/<pk>/resource/`, clique le premier
  `[data-testid="booking-calendar-slot-free"]`, ajoute au panier, recharge, attend
  `booking-calendar-slot-cart` avec le même `data-start-datetime`.
- `tests/e2e/test_booking_formulaire_dynamique.py` (l. ~94) : premier créneau libre → formulaire.
- `tests/pytest/test_parite_avec_sans_panier.py` (l. ~2314, ~2358) : GET de la page, lit le menu.

Aucun test n'utilise `booking-calendar-next-week`, `booking-mobile-day-bar` ni les fonctions
`_build_calendar_weeks` / `_build_mobile_days`. Les pages qui mènent à la page ressource (cartes V2
`pages/templates/cotton/V2/ressource_card.html`, « Mes réservations », `slot_unavailable`)
arrivent sur la semaine par défaut : aucun impact.

---

## 3. Le motif à réutiliser (bénévolat, chantier 7)

`booking/benevolat.py` et `booking/views_benevolat.py` font déjà « une semaine à la fois » :

- `?semaine=AAAA-MM-JJ` : **n'importe quel jour**, ramené à son lundi. Lisible, partageable.
- `lire_la_semaine_demandee(texte)` → `date` ou `None` (absent / illisible).
- `lundi_de_la_semaine(une_date)` → le lundi.
- (`choisir_la_semaine()` existe aussi, mais elle cherche la semaine du prochain besoin : **pas
  utilisée ici**, la semaine par défaut est la semaine en cours, D3.)
- `titre_de_la_semaine(lundi)` → « 20 – 26 octobre », avec l'année si la semaine change d'année.
- Les liens de semaine ont un `href` (marche sans JS) **et** un `hx-get` + `hx-push-url="true"`.
- La vue `retrieve` rend **la zone seule** quand l'en-tête `HX-Target` vaut l'id de la zone, et la
  **page entière** sinon.
- Retour arrière : les trois shells (`pages/templates/pages/{V2,classic,faire_festival}/shell.html`)
  ont `historyCacheSize: 0, refreshOnHistoryMiss: true` : le retour arrière **recharge la page
  entière** par le navigateur. La vue reçoit une requête normale et rend la page entière.
- Le titre de la semaine porte `tabindex="-1"` : après un **lien de semaine**, le focus y est posé
  (filtre dans `htmx:beforeSwap` sur `requestConfig.elt.closest(...)`, `planning.html` l. ~156-184),
  et le lecteur d'écran lit la nouvelle semaine. Les liens gardent le même `id` d'une semaine à
  l'autre.

Ces fonctions sont génériques (elles ne parlent pas de bénévolat). On les **importe** depuis
`booking/benevolat.py`. On ne les déplace pas : ce serait un refactoring hors sujet.

---

## 4. Décisions proposées (à valider)

| # | Décision | Pourquoi |
|---|---|---|
| D1 | Une seule URL : `GET /booking/<pk>/resource/?semaine=AAAA-MM-JJ`. Pas de nouvelle route. | Même motif que le bénévolat ; l'adresse se partage et survit au rechargement. |
| D2 | `resource_page()` rend le **partial de la semaine** si `request.headers.get("HX-Target") == "booking-calendrier-semaine"`, la **page entière** sinon. | Motif du bénévolat. Le `body` n'a pas d'id : la navigation vers la page par une carte (`hx-target="body"`) reçoit bien la page entière. |
| D3 | Semaine affichée : **avec un `?semaine=` lisible et pas passé**, son lundi, borné au lundi de la dernière semaine de l'horizon (D4). **Sinon** (absent, illisible, passé) : **la semaine en cours**, même vide (Q1). Dans tous les cas, on ne calcule **que cette semaine**. | Décision du mainteneur (Q1). Le plus simple : un seul petit calcul par page, aucune recherche de la « première semaine qui a des créneaux ». |
| D4 | Semaine demandée **après** la dernière semaine de l'horizon : la dernière semaine de l'horizon. | Pas d'erreur 404 pour un lien trop vieux. |
| D5 | Une semaine **sans créneau** reste affichée, avec « Aucun créneau cette semaine. » et la navigation. | Simple et honnête (motif du bénévolat). |
| D6 | « Semaine précédente » existe si le lundi affiché est après le lundi de la semaine en cours. « Semaine suivante » existe si le lundi suivant est au plus tard le lundi de la dernière semaine de l'horizon. Un lien absent n'est **pas rendu**. | Motif du bénévolat. |
| D7 | Fenêtre de calcul d'une semaine : `[max(lundi 0 h, maintenant), lundi suivant 0 h)`, **construite au fuseau du lieu** (§6.1). Pas de marge. | `OpeningEntry.clean()` interdit qu'un créneau dépasse minuit (§2.4). Le fuseau de la fenêtre pilote le moteur : en UTC, les créneaux de la semaine en cours seraient décalés. |
| D8 | `data-group-end` **inchangé** : il vaut la fin du groupe **dans la semaine**. Un groupe qui continue la semaine d'après est coupé au lundi 0 h : une réservation de plusieurs créneaux d'affilée **ne traverse pas** le dimanche à minuit. `_book_get()` et `openBookingPopup()` ne changent pas. | Décision du mainteneur (Q2). Le groupe affiché est inclus dans le groupe réel : le formulaire ne propose jamais trop de créneaux. Cas rare (créneaux de même durée qui se suivent à minuit). |
| D9 | On réutilise `_build_calendar_weeks()` et `_build_mobile_days()` **sans les modifier**, nourries avec les seuls groupes de la semaine. Les bornes horaires de la grille sont donc celles de la semaine (elles peuvent varier : semaine en cours partielle, dernière semaine coupée par l'horizon, fermetures). | Changement minimal ; faisable (`_build_calendar_weeks` crée ses propres dicts, la mutation de `row_start` par `_build_mobile_days` ne le gêne pas). |
| D10 | Mobile : la barre de jours ne montre que les jours **de la semaine affichée** (7 au plus). Les flèches « jour précédent / suivant » restent dans la semaine. On change de semaine avec la **même navigation de semaine** que le desktop, visible aussi sur mobile. La classe `active` du premier jour et le `disabled` des flèches sont **rendus côté serveur**. | Une seule navigation de semaine, un seul partial ; moins de JS. |
| D11 | Structure : le `<style>`, `#booking-calendar`, les deux sélecteurs de ressource (**sortis des cartes**, avec `d-none d-md-block` / `d-md-none`), la légende et le partial sont rendus **sans condition**. Le partial `booking/partials/resource_semaine.html` contient la navigation de semaine + le bloc desktop + le bloc mobile **de cette semaine**. L'état vide global « Aucun créneau disponible prochainement. » **disparaît** : une semaine vide montre « Aucun créneau cette semaine. » et la navigation (D5). | Si le `{% if calendar_weeks or mobile_days %}` actuel restait : une semaine vide afficherait l'état vide global sans navigation (contredit D5), et un swap HTMX d'une semaine vide vers une pleine donnerait une grille sans CSS. Savoir si **tout** l'horizon est vide demanderait un calcul de plus : pas nécessaire. |
| D12 | Le titre de la semaine est calculé **côté serveur** (`titre_de_la_semaine`). Le calcul en JS de `#calendar-week-label` est supprimé. | Python serveur > JS client. |
| D13 | Le JavaScript reste dans la page (pas dans le partial). Tous les écouteurs (clic sur un créneau, flèches et barre de jours mobiles) sont **délégués sur `#booking-calendar`**, jamais sur `body` ni `document`. `showDesktopWeek()` disparaît. Après chaque swap de la zone, le focus va sur le titre de la semaine (seuls les liens de semaine remplacent la zone : pas de filtre à écrire). | La page est souvent chargée par `hx-get` + `hx-target="body"` (`ressource_card.html` l. ~45-49) : ses scripts sont rejoués à chaque visite et `body` reste en place, donc des écouteurs sur `body` s'empileraient. Un `<script>` dans le partial s'exécuterait à chaque swap. |

---

## 5. Réponses du mainteneur (2026-10-18)

- **Q1 — Semaine par défaut :** **la semaine en cours**, même vide (D3).
- **Q2 — Réservation à cheval sur deux semaines :** **interdite**. `data-group-end` reste la fin du
  groupe dans la semaine (D8).
- **Q3 — Rafraîchir la semaine après « Ajouter au panier » :** **non**. Le seul gain serait visuel
  (le créneau passerait en couleur « Panier » sans recharger) ; le panier et la réservation
  revérifient tout. Hors périmètre.
- **Q4 — Templates orphelins (§2.6) :** **supprimés** dans ce chantier.
- **Q5 — Bug de minuit (§2.7) :** **corrigé** dans ce chantier (§6.5).

---

## 6. Conception détaillée

### 6.1 La vue `resource_page()`

Pseudo-code, à écrire en FALC dans la vue (méthodes privées du ViewSet, comme
`_build_calendar_weeks`) :

```
fuseau = timezone.get_current_timezone()            # fuseau du lieu (TimezoneMiddleware)
maintenant = timezone.localtime(timezone.now(), fuseau)   # JAMAIS timezone.now() brut (UTC)
aujourd_hui = maintenant.date()
lundi_de_cette_semaine = lundi_de_la_semaine(aujourd_hui)
dernier_jour_reservable = aujourd_hui + timedelta(days=resource.booking_horizon_days)
lundi_de_la_derniere_semaine = lundi_de_la_semaine(dernier_jour_reservable)

semaine_demandee = lire_la_semaine_demandee(request.GET.get("semaine"))
lundi = lundi_de_cette_semaine                                         # D3 : par défaut
si semaine_demandee et lundi_de_la_semaine(semaine_demandee) > lundi_de_cette_semaine :
    lundi = min(lundi_de_la_semaine(semaine_demandee), lundi_de_la_derniere_semaine)   # D4

creneaux_de_la_semaine = compute_slots(resource, fenetre_de_la_semaine(lundi))
groupes = annotate_slots_for_display(creneaux_de_la_semaine)
(marquage in_cart, inchangé)
calendar_weeks, min_hour, max_hour = self._build_calendar_weeks(groupes)
mobile_days, ... = self._build_mobile_days(groupes)
time_rows, mobile_day_bar : inchangés (calculés sur la semaine)

semaine = {"lundi", "titre",
           "precedente" (lundi ou None), "suivante" (lundi ou None)}     # D6

si HX-Target == "booking-calendrier-semaine" :
    render("booking/partials/resource_semaine.html", contexte minimal)   # ni get_context() ni
                                                                          # _get_resource_choices()
sinon :
    render("booking/views/resource.html")      # qui {% include %} le partial
```

`fenetre_de_la_semaine(lundi)` :

```
debut = timezone.make_aware(datetime.datetime.combine(lundi, datetime.time.min), fuseau)
fin   = timezone.make_aware(datetime.datetime.combine(lundi + timedelta(days=7), datetime.time.min), fuseau)
return Interval(start=max(debut, maintenant), end=fin)     # maintenant est déjà au fuseau du lieu
```

> `max(debut, maintenant)` : `compute_slots` ne borne pas le début de la fenêtre ; sans ce `max`,
> les créneaux déjà commencés de la semaine en cours seraient proposés. Les deux valeurs sont au
> fuseau du lieu : `max()` renvoie l'une ou l'autre, et le moteur lit le fuseau de `window.start`.

> **À vérifier pendant le chantier :** le contexte minimal du partial (le gabarit lit `resource`,
> `semaine`, `calendar_weeks`, `time_rows`, `mobile_days`, `mobile_time_rows`, `mobile_day_bar`…).
> Lister ce que le partial lit réellement avant d'alléger.

### 6.2 Le partial `booking/partials/resource_semaine.html`

```
<div id="booking-calendrier-semaine"
     data-semaine="{{ semaine.lundi|date:'Y-m-d' }}"
     hx-target="#booking-calendrier-semaine" hx-swap="outerHTML"
     data-testid="booking-calendrier-semaine">

  <nav aria-label="{% translate 'Changer de semaine' %}" data-testid="booking-calendar-nav">
    {% if semaine.precedente %}
      <a id="calendar-prev-week" href="…?semaine=…" hx-get="…?semaine=…" hx-push-url="true"
         aria-label="{% translate 'Semaine précédente' %}"
         data-testid="booking-calendar-prev-week">…</a>
    {% endif %}
    <h2 id="calendar-week-label" tabindex="-1" data-testid="booking-calendar-week-label">
      {{ semaine.titre }}
    </h2>
    {% if semaine.suivante %} … id="calendar-next-week" … data-testid="booking-calendar-next-week" {% endif %}
  </nav>

  {% if calendar_weeks %}
    bloc desktop (une seule semaine : plus de display:none)
    bloc mobile (barre des jours de la semaine, premier jour `active`, flèches `disabled` côté serveur)
    (créneaux recopiés de resource.html, data-group-end compris, inchangés : D8)
  {% else %}
    <p data-testid="booking-calendar-empty-week">{% translate "Aucun créneau cette semaine." %}</p>
  {% endif %}
</div>
```

- `href` et `hx-get` : `{% url 'booking-resource' pk=resource.pk %}?semaine=…` (route
  `url_name="resource"` du router `booking`, sans namespace).
- **Pas d'`aria-live`** sur la zone (remplacée en `outerHTML`, annonce peu fiable ; le focus sur le
  `h2` suffit, comme au bénévolat). **Garder** celui de `.mobile-days`, qui change sur place.
- **Garder les `data-testid` existants** des créneaux, des cellules, de la grille et de la barre
  mobile : `test_panier_flow.py` et `test_booking_formulaire_dynamique.py` doivent passer sans
  changement.
- `{% blocktrans %}` des `aria-label` de créneaux : recopiés tels quels (chaînes déjà traduites).
- L'overlay de chargement (`#tibillet-spinner`) s'allume tout seul après le délai : **ne rien
  ajouter** (`data-loading-*`) sur les liens de semaine.

### 6.3 `resource.html` (la page)

- Rendus **sans condition** (D11) : retour, en-tête de la ressource, `<style>`, offcanvas
  `#bookingPanel` / `#offcanvas-booking`, `#booking-calendar` (avec `data-book-url`), les deux
  sélecteurs de ressource sortis des cartes, la légende.
- Dans `#booking-calendar` : `{% include "booking/partials/resource_semaine.html" %}`. L'état vide
  global (`data-testid="booking-calendar-empty"`) est supprimé (D11).
- Script :
  - supprimer `showDesktopWeek()`, ses écouteurs et le calcul du libellé ;
  - flèches et barre de jours mobiles : écouteurs **délégués sur `#booking-calendar`** ;
    `showMobileDay()` ne sert plus qu'aux clics (l'état initial vient du serveur) ;
  - focus sur `#calendar-week-label` après chaque swap de `#booking-calendrier-semaine`
    (écouteur `htmx:afterSettle` posé sur `#booking-calendar`) ;
  - `openBookingPopup()` : inchangée.

### 6.5 Bug de minuit (Q5)

Dans `_build_calendar_weeks()` (l. ~117) et `_build_mobile_days()` (l. ~225), l'heure de fin d'un
créneau qui finit à minuit (lendemain 0 h) doit compter pour **24**, pas pour 0. Correction
minimale, la même dans les deux fonctions :

```python
end_hour = slot.end.hour
if slot.end.minute > 0:
    end_hour += 1
# Un créneau qui finit à minuit finit le lendemain à 0 h : il compte pour 24 h.
# / A slot ending at midnight ends at 0:00 the next day: it counts as 24.
if slot.end.date() > slot.start.date():
    end_hour = 24
```

(Possible parce que `OpeningEntry.clean()` interdit tout créneau qui finit **après** minuit,
§2.4 : « finit le lendemain » veut toujours dire « finit pile à minuit ».)

### 6.6 Templates orphelins (Q4)

Supprimer `booking/templates/booking/views/resource_day.html` et
`booking/templates/booking/partials/resource_day_calendar.html`. Avant : vérifier qu'aucun fichier
ne les cite (`rg -n "resource_day" --type py --type html`, hors `www/`).

### 6.4 Accessibilité

- Titre de semaine en `h2` focusable (`tabindex="-1"`), focus posé après chaque changement de semaine.
- Vérifier la hiérarchie des titres de la page (le `h1` est le nom de la ressource).
- Les liens absents (D6) ne laissent pas de bouton désactivé inutile au lecteur d'écran.

---

## 7. Ce qui ne change pas

- Le moteur (`compute_slots()`, `annotate_slots_for_display()`, `generate_theoretical_slots()`) :
  **aucune modification**.
- `_book_get()`, `_book_post()`, `openBookingPopup()`, le panier, l'offcanvas : inchangés.
- `_build_calendar_weeks()`, `_build_mobile_days()` : inchangées (D9), sauf le bug de minuit (§6.5).
- La liste des ressources (`list`) : hors sujet.

---

## 8. Fichiers touchés (prévision)

| Fichier | Changement |
|---|---|
| `booking/views.py` | `resource_page()` : lecture de `?semaine=`, choix de la semaine (D3), fenêtre au fuseau du lieu (D7), partial si `HX-Target` (D2) ; bug de minuit dans `_build_calendar_weeks` / `_build_mobile_days` (§6.5) |
| `booking/templates/booking/views/resource_day.html`, `booking/templates/booking/partials/resource_day_calendar.html` | Supprimés (§6.6) |
| `booking/templates/booking/partials/resource_semaine.html` | Nouveau : navigation de semaine + desktop + mobile d'une semaine |
| `booking/templates/booking/views/resource.html` | Structure sans condition (D11), sélecteurs sortis des cartes, inclusion du partial, JS délégué sur `#booking-calendar` |
| `tests/pytest/test_booking_calendrier_semaine.py` | Nouveau (voir §9) |
| `tests/e2e/test_booking_calendrier_semaine.py` | Nouveau (voir §9) |
| `CHANGELOG/AAAA-MM-JJ-booking-calendrier-une-semaine.md` | Fiche du chantier |

Pas de migration, pas de nouveau modèle, pas de nouvelle route.

---

## 9. Tests

**Avant d'écrire un test :** lire `tests/PIEGES.md`. `Event.save()` lit `connection.tenant` :
`tenant_context`, jamais `schema_context`.

**Figer le temps : ne pas patcher `timezone.now`.** `booking.views.timezone` est le module Django
lui-même : le patch toucherait les sessions, `last_login`, etc. Suivre le motif éprouvé de
`tests/pytest/test_benevolat_semaines.py` (l. ~70-72) : construire les données **à partir du vrai
aujourd'hui**, au fuseau du lieu `Configuration.get_solo().get_tzinfo()`. Hors requête,
`get_current_timezone()` vaut UTC (`TIME_ZONE=UTC` dans le conteneur) alors que la requête tourne
au fuseau du lieu (Europe/Paris sur `lespass`) : toujours passer par le fuseau du lieu.
Pour une « semaine en cours vide » : une `ClosedPeriod` d'aujourd'hui à dimanche.

Helpers utiles : `_make_resource`, `_make_calendar`, `_make_weekly_opening`, `_add_opening_entry`,
`_cleanup` (`booking/tests/test_booking_engine.py`). **Ne pas** utiliser `MONDAY_NEAR` /
`REFERENCE_NOW` : ces dates de juin 2026 sont passées, et la vue ne reçoit pas de `reference_now`.

### 9.1 pytest (`tests/pytest/test_booking_calendrier_semaine.py`)

1. Sans `?semaine=` : la page montre la semaine en cours (D3), même vide (`ClosedPeriod`
   d'aujourd'hui à dimanche → « Aucun créneau cette semaine. » et « Semaine suivante »).
2. `?semaine=` un mercredi → la semaine de son lundi ; le titre est celui de `titre_de_la_semaine`.
3. `?semaine=abc`, une date passée → semaine par défaut ; une date après l'horizon → dernière
   semaine (D4).
4. Avec `HX-Target: booking-calendrier-semaine` → le partial seul (pas de `<html>`) ; sans → la page.
5. La page ne contient **que** les créneaux de la semaine (compter les
   `data-testid="booking-calendar-slot-free"` et vérifier leurs dates).
6. **Fuseau (D7) :** dans la semaine en cours, une ouverture à 10 h donne des
   `data-start-datetime` en `…T10:00:00`. **Mutation :** `debut = timezone.now()` brut → échec.
7. **Bug de minuit (§6.5) :** un créneau 18 h – 24 h tient dans la grille : sa ligne de fin
   (`row_end`) ne dépasse pas la dernière ligne horaire (`time_rows`), et la grille va jusqu'à
   24:00. **Mutation :** retirer la correction → échec.
8. « Semaine précédente » absente sur la semaine en cours, « Semaine suivante » absente sur la
   dernière semaine (D6).
9. Une semaine vide demandée par `?semaine=` : la navigation, `#booking-calendar` et le message
   « Aucun créneau cette semaine. » sont présents ; pas l'état vide global (D5, D11).
10. Un créneau au panier est marqué `booking-calendar-slot-cart` dans le partial.
11. Un créneau bloqué par un événement (`Event.ressource_bloquee`) est `booking-calendar-slot-busy`.

### 9.2 E2E (`tests/e2e/test_booking_calendrier_semaine.py`)

1. Desktop : « Semaine suivante » → la zone change **sans rechargement**
   (`poser_un_temoin_de_rechargement` / `la_page_n_a_pas_ete_rechargee`,
   `tests/e2e/test_benevolat_flow.py` l. ~84-89), l'adresse porte `?semaine=`, le titre change.
   Retour arrière → la semaine d'avant revient (**ne pas** vérifier le témoin après `go_back` : les
   shells rechargent la page entière, §3).
2. Mobile (375 px) : flèches de jour dans la semaine, puis changement de semaine ; pas de
   défilement horizontal de la page.
3. Clic sur un créneau libre de la **deuxième** semaine → le formulaire s'ouvre (le clic délégué
   survit au swap).
4. Les E2E existants passent sans changement : `test_panier_flow.py`,
   `test_booking_formulaire_dynamique.py`.

Chaque test est vu **échouer** sur une mutation volontaire avant d'être livré (règle du projet).

---

## 10. Plan d'exécution

1. Vue : fenêtre au fuseau du lieu, choix de la semaine (D3, D4, D6, D7) + pytest 1 à 3, 5, 6, 8.
2. Bug de minuit (§6.5) + pytest 7.
3. Partial + page : structure sans condition (D11), navigation, `HX-Target` (D2)
   + pytest 4, 9, 10, 11.
4. JS : suppression de `showDesktopWeek`, délégation sur `#booking-calendar`, état mobile côté
   serveur, focus filtré.
5. Suppression des templates orphelins (§6.6).
6. E2E 1 à 4 ; vérification visuelle Chrome (desktop + 375 px) sur la « Salle de résidence et
   concert » (fixtures de démo, horizon 90 jours, soirées bloquées par les concerts, créneau
   18 h – 24 h dans la grille).
7. Mesure du poids avant / après (tableau du §1), notée dans le CHANGELOG.
8. Relecture `djc` (§12), CHANGELOG ; chaîne i18n nouvelle : « Aucun créneau cette semaine. »
   (« Changer de semaine », « Semaine précédente » et « Semaine suivante » existent déjà).

---

## 11. Pièges connus

- **Toutes les commandes dans le conteneur** (`docker exec lespass_django …`), rien sur l'hôte.
- **Docker ne voit pas les worktrees** : tester dans le dossier principal.
- **Fuseau :** une fenêtre passée à `compute_slots` doit être au fuseau du lieu (§2.4). Jamais
  `timezone.now()` brut comme début de fenêtre.
- **`compute_slots` borne la fin à l'horizon, pas le début** : d'où `max(lundi 0 h, maintenant)`.
- **`HX-Target`** : htmx envoie l'`id` de la cible **sans** `#`.
- **Écouteurs JS** : sur `#booking-calendar`, jamais sur `body` / `document` (page rejouée par
  `hx-target="body"`). Aucun `<script>` dans le partial.
- **`ruff format` / `ruff check --fix`** : jamais sur `booking/views.py` (fichier existant).

---

## 12. Garde-fous : pas de sur-ingénierie, conformité `djc`

Consigne du mainteneur. À relire **avant** d'écrire le code, puis **case par case** avant de
rendre le chantier (étape 8 du §10).

### 12.1 Pas de sur-ingénierie

- Pas de nouvelle route, pas de nouveau module, pas de classe : deux petites méthodes privées
  dans le ViewSet au plus (choix de la semaine, fenêtre de la semaine).
- On **importe** `lundi_de_la_semaine`, `lire_la_semaine_demandee`, `titre_de_la_semaine` depuis
  `booking/benevolat.py` : on ne les déplace pas, on ne les recopie pas.
- Le moteur (`booking_engine.py`) et `_book_get()` ne bougent pas.
- `_build_calendar_weeks()` / `_build_mobile_days()` : seule la correction de minuit (§6.5).
- Pas de cache, pas de préchargement des semaines voisines, pas de « première semaine avec
  créneaux », pas de rafraîchissement après le panier : tout cela a été écarté.
- Le JS **diminue** : on supprime `showDesktopWeek()` et le calcul du libellé ; on n'ajoute que la
  délégation et le focus.

### 12.2 Conformité `djc` (skill `djc`, `GUIDELINES.md`)

| Règle | Comment la tenir ici |
|---|---|
| FALC : noms verbeux, explicite, boucles simples | `lundi_de_la_derniere_semaine`, `creneaux_de_la_semaine`… ; pas de compréhension imbriquée |
| Commentaires bilingues FR (FALC) puis EN (une ligne) ; `LOCALISATION` dans les docstrings | Docstrings des méthodes ajoutées, en-tête du nouveau partial (bloc `<!-- -->` avec LOCALISATION, flux, contexte attendu) |
| Le commentaire décrit le code **tel qu'il est** (pas l'historique de la session) | Pas de « avant, la page rendait tout l'horizon » dans le code : ça va dans le CHANGELOG |
| `viewsets.ViewSet` explicite, pas de `get_queryset()` caché | `resource_page()` reste une `@action` explicite |
| Python serveur > JS client ; pas de `window.xxx = {{ … }}` | Titre de semaine, liens, état mobile initial calculés côté serveur ; le JS ne porte aucune logique métier |
| HTMX : partial HTML, `hx-get` + `href` (repli sans JS), `hx-push-url` | Liens de semaine (§6.2) |
| Overlay de chargement : ne rien ajouter | Pas de `data-loading-*` sur les liens de semaine |
| Pas de `hx-boost` | Liens explicites |
| `data-testid` sur tout élément interactif ou bloc de contenu | Zone, navigation, titre, liens, message de semaine vide ; testids existants conservés |
| Accessibilité : `aria-label`, `aria-hidden` sur les icônes décoratives, focus | `nav aria-label`, chevrons `aria-hidden="true"`, `h2 tabindex="-1"` |
| i18n : `{% translate %}` / `{% blocktrans %}`, **msgid en français** | « Aucun créneau cette semaine. » ; **ne pas** lancer `makemessages` / `compilemessages`, le signaler au mainteneur |
| Classes Bootstrap sémantiques (thème clair / sombre) | `text-muted`, etc. pour le message de semaine vide |
| Multi-tenant : fuseau du lieu | Fenêtre au fuseau du lieu (D7) ; tests en `tenant_context` |
| CHANGELOG : un fichier par chantier, créé avec le code | `CHANGELOG/AAAA-MM-JJ-booking-calendrier-une-semaine.md` (résumé bilingue, flag migration « Non », tests manuels) |
| Tests : pytest pour le Python, E2E pour le navigateur ; vus échouer sur mutation | §9 |
| Git : jamais de commit, push, ni commande destructive ; jamais de mention de Claude | Le mainteneur commit |
