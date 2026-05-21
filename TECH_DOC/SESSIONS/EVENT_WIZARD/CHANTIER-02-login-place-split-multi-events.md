# CHANTIER-02 — Login classique, choix de lieu en 2 pages, multi-événements

**Date :** 2026-05-21
**Statut :** Implémenté (vérifié sur Chrome, tests pytch différés)
**Dépend de :** [CHANTIER-01](SPEC.md) (MVP wizard + service OTP)

Évolution du wizard MVP (chantier 01) suite à des retours d'usage. Quatre axes :
connexion classique à la place de l'OTP, choix de lieu scindé en 2 pages comme
l'onboarding, ajout multi-événements, et un routage DRF propre. Plus deux
correctifs (badge sidebar, géocodage widget).

---

## 1. Connexion classique requise (OTP mis de côté)

**Avant :** le wizard public était anonyme (`authentication_classes = []`),
protégé par un OTP email (étapes `step0_email` / `step0_verify`).

**Problème constaté :** `authentication_classes = []` forçait `request.user` à
`AnonymousUser`, donc la navbar affichait « Connexion » même pour un visiteur
déjà connecté, et on lui redemandait une vérification OTP redondante.

**Décision :** s'appuyer sur la **connexion classique** (session) pour l'instant.
L'OTP sera réintégré plus tard **dans l'offcanvas de connexion** (cf. hub OTP).

- `EventWizardPublic.authentication_classes = [SessionAuthentication]` (au lieu de `[]`),
  `permission_classes = [AllowAny]` conservé (les anonymes atteignent la vue puis
  sont redirigés vers la connexion).
- Garde `_require_login_or_redirect(request)` : si non connecté →
  `messages.WARNING("Merci de vous connecter d'abord.")` + redirect
  `event-list?login=1`.
- **Ouverture auto de l'offcanvas de connexion** : `reunion/partials/navbar.html`
  contient un petit script qui ouvre `#loginPanel` via
  `bootstrap.Offcanvas.getOrCreateInstance(...).show()` quand l'URL porte
  `?login=1`, puis nettoie l'URL (`history.replaceState`).
- `step0_email` devient l'entrée intelligente : connecté → redirige vers le choix
  de lieu ; anonyme → garde (toast + offcanvas). **Le code OTP est conservé**
  (`otp_service.py`, `otp_session.py`, `step0_verify`, `step0_resend`,
  `_require_otp_confirmed`) — parqué, pas supprimé.
- Proposition créée avec `created_by=request.user` (avant `None`).

## 2. Choix de lieu en 2 pages (comme l'onboarding)

**Avant :** une seule page (toggle + nom + carte ensemble).

**Après :** deux pages, comme `onboard/steps/03_place.html`.

- **Page 1 — choix** (`_form_lieu.html`) : toggle **pleine largeur**
  (`btn-group w-100`) entre « adresse existante » (liste **filtrable en JS**,
  pas d'HTMX) et « nouveau lieu » (**nom seul**). « Continuer » route vers
  l'étape event (existante) ou la page carte (nouveau).
- **Page 2 — carte** (`_form_carte.html`, wrappers `*_step_map.html`) : widget
  carte avec `adresse_initiale = <nom saisi>` → le widget **pré-remplit et lance
  la recherche automatiquement** (code déjà présent dans `widget_carte_adresse.js`).
- Serializers : `WizardPlaceSelectSerializer` (mode existant/nouveau) +
  `WizardPlaceMapSerializer` (lat/lng + adresse) **remplacent** `WizardPlaceSerializer`.
- Helpers module partagés admin/public : `_wizard_etape_choix_lieu`,
  `_wizard_etape_carte_lieu`. Nom du nouveau lieu stocké en session entre les 2 pages.

## 3. Multi-événements (admin + public)

**Avant :** un seul événement par passage.

**Après :** étape « événements » = liste HTMX add/remove + bouton finaliser, repris
du formulaire multi-events de l'onboarding (`onboard/partials/event_row_form.html`).

- Brouillons stockés en **session HTTP** (liste de dicts) ; images uploadées →
  `default_storage` (chemin relatif en session, dossier `event_wizard_drafts/`).
- Actions `@action` : `events_add` (`events/add`), `events_remove`
  (`events/remove/<idx>`). GET de `step2_event` = liste+form, POST = **finalize**.
- **Lieu partagé** : tous les événements d'une proposition partagent le lieu choisi
  à l'étape 1 (décision validée avec le mainteneur).
- Finalize : **admin** → N events `published=True` (jauge/show_gauge, tags, FREERES) →
  redirect fiche (1 event) ou agenda (N) ; **public** → N propositions
  `published=False, is_proposal=True` → page Done.
- Helpers : `_wizard_events_add_generic`, `_wizard_events_remove_generic`,
  `_wizard_render_events_inner`, `_creer_event_{admin,public}_depuis_brouillon`.
- Image au finalize : `event.img.name = chemin` (pas de recopie → **une seule
  sauvegarde**, les signaux ne se déclenchent qu'une fois).

## 4. Routage via router DRF (plus de `path()` manuels)

**Avant :** `as_view({...})` + un `path()` par étape (les `@action` étaient décoratifs).

**Après :** `SimpleRouter` dédié (`wizard_router` dans `urls.py`) qui route les 2
ViewSets via leurs `@action(url_path=..., url_name=...)`. Ajouter une action =
ajouter une URL automatiquement (bénéfice constaté pour `events_add`/`events_remove`).

- `SimpleRouter` (pas `DefaultRouter`) → pas de vue api-root, donc pas de souci
  avec des ViewSets sans méthode `list`.
- Inclus **avant** le routeur principal (`urlpatterns += wizard_router.urls`
  avant `+= router.urls`) pour que `event/propose/...` et `event/admin/wizard/...`
  soient résolus avant le pattern `event/{pk}/` d'`EventMVT`.
- Noms d'URL **préservés** via `url_name` (`event-propose-email`, etc.) → templates
  inchangés. Le redirect d'entrée `event/propose/` reste un `path()` (lambda).

## 5. Plafond d'affichage des adresses (tenants 300+)

Pour un tenant avec beaucoup de `PostalAddress` (agenda régional) : **toutes** les
adresses restent dans le DOM (la recherche JS fonctionne sur la totalité), mais on
n'en **affiche que 50 à la fois** (`LIMITE_VISIBLE`). Message « Toutes les adresses
ne sont pas affichées. Tapez pour filtrer. ». L'item sélectionné reste toujours
visible. (Pour des milliers d'adresses : recherche serveur HTMX = étape future.)

## 6. Toggle vertical sur mobile

`@media (max-width: 575.98px)` dans `_form_lieu.html` : le toggle passe en
`flex-direction: column`, chaque bouton pleine largeur avec coins arrondis
individuels (annulation des marges/rayons horizontaux de Bootstrap).

## 7. Correctifs

- **Badge sidebar « None »** (`Administration/admin/dashboard.py`) : l'item Events
  utilisait `"badge": "<chemin callback>"`. Le template Unfold teste
  `{% if item.badge %}` sur ce chemin (toujours vrai) → le badge s'affichait
  toujours, rendant `None` quand le callback renvoyait `None`. Fix : appeler le
  callback dans `get_sidebar_navigation` et passer `… or ""` (chaîne vide → pas de badge).
- **Widget géocodage** (cf. [WIDGET_GEO/03](../WIDGET_GEO/03-fix-reverse-geocode-fallback.md)) :
  une recherche par **nom** renvoie souvent un centroïde sans rue/CP. Repli :
  reverse-geocode sur les coordonnées trouvées si l'adresse forward est incomplète.

---

## Fichiers principaux touchés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | auth session + garde login, split lieu (2 helpers), multi-events (3 helpers + 2 fabriques), `@action` + `url_name` |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` + `WizardPlaceMapSerializer` (remplacent `WizardPlaceSerializer`) |
| `BaseBillet/urls.py` | `SimpleRouter` wizard, suppression des `as_view`/`path` manuels |
| `BaseBillet/templates/.../wizard/_form_lieu.html` | toggle full-width + liste filtrable + plafond 50 + media query mobile |
| `BaseBillet/templates/.../wizard/_form_carte.html` + `*_step_map.html` | NOUVEAU — page carte |
| `BaseBillet/templates/.../wizard/_events_inner.html` | NOUVEAU — liste + sous-form HTMX add |
| `BaseBillet/templates/.../wizard/{admin,public}_step2_event.html` | réécrits en étape multi-events |
| `Administration/admin/dashboard.py` | fix badge `… or ""` |
| `reunion/partials/navbar.html` | ouverture auto offcanvas connexion (`?login=1`) |
| `static/widgets/widget_carte_adresse.js` | repli reverse-geocode |

## Décisions

| Sujet | Décision |
|---|---|
| OTP | **Parqué** (code conservé), réintégration future dans l'offcanvas de connexion |
| Auth public | Connexion classique (session) requise pour l'instant |
| Lieu / events | **Partagé** : tous les events d'une proposition au même lieu |
| Image brouillon | `event.img.name = chemin` au finalize (1 save, signaux 1×) |
| HTMX erreurs add | Renvoi **200** (pas de config swap-on-422 dans le skin reunion) |
| Routage | `SimpleRouter` avant le routeur principal, `url_name` pour garder les noms |

## Reste à faire / différé

- Tests pytch à adapter (`test_event_wizard_public.py` testait le flow OTP/anonyme).
- i18n : `makemessages` / `compilemessages` (nouvelles chaînes).
- Réintégration OTP dans l'offcanvas de connexion (chantier futur, cf. hub OTP).
