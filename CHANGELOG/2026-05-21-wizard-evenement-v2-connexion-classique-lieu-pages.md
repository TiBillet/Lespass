# Wizard évènement V2 : connexion classique, lieu en 2 pages, multi-évènements / Event wizard V2: classic login, 2-page place, multi-events

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Évolution du wizard évènement (cf. entrée du 2026-05-19). Le
wizard public n'utilise plus l'OTP mais la **connexion classique** (l'OTP est
conservé en code, parqué pour un futur offcanvas de connexion). Le choix de lieu
passe en **2 pages** comme l'onboarding (page 1 : adresse existante filtrable OU
nom d'un nouveau lieu ; page 2 : carte pré-remplie avec recherche auto). On peut
désormais **proposer / créer plusieurs évènements** d'un coup (liste HTMX
add/remove, lieu partagé). Le routage des 2 wizards passe sur un **router DRF**
(plus de `path()` manuels). La liste d'adresses **plafonne l'affichage à 50** (la
recherche couvre la totalité) pour rester navigable avec 300+ adresses, et le
toggle de mode passe en **vertical sur mobile**.

**Pourquoi / Why :** `authentication_classes = []` faisait afficher « Connexion »
à un visiteur déjà connecté et imposait un OTP redondant. Le multi-évènements
reproduit le formulaire onboarding (annoncer plusieurs dates d'un lieu). Le
plafond d'adresses et le toggle mobile préparent les tenants « agenda régional ».

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Auth session + garde `_require_login_or_redirect`, split lieu (2 helpers), multi-events (3 helpers + 2 fabriques `_creer_event_*`), `@action` + `url_name` |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` + `WizardPlaceMapSerializer` (remplacent `WizardPlaceSerializer`) |
| `BaseBillet/urls.py` | `SimpleRouter` `wizard_router` (avant le routeur principal), suppression des `as_view`/`path` manuels du wizard |
| `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html` | Toggle full-width + liste filtrable + plafond 50 + media query mobile |
| `BaseBillet/templates/reunion/views/event/wizard/_form_carte.html` + `{admin,public}_step_map.html` | NOUVEAU — page carte (étape 2 du lieu) |
| `BaseBillet/templates/reunion/views/event/wizard/_events_inner.html` | NOUVEAU — liste brouillons + sous-form HTMX add |
| `BaseBillet/templates/reunion/views/event/wizard/{admin,public}_step2_event.html` | Réécrits en étape multi-évènements |
| `Administration/admin/dashboard.py` | Fix badge sidebar « None » (`event_proposals_badge_callback(request) or ""`) |
| `BaseBillet/templates/reunion/partials/navbar.html` | Ouverture auto de l'offcanvas connexion via `?login=1` |
| `static/widgets/widget_carte_adresse.js` | Repli reverse-geocode quand la recherche par nom renvoie une adresse incomplète |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/CHANTIER-02-*.md` | NOUVEAU — recap du chantier |
| `TECH_DOC/SESSIONS/WIDGET_GEO/03-fix-reverse-geocode-fallback.md` | NOUVEAU — note de correctif |
| `A TESTER et DOCUMENTER/event-wizards.md` | Mis à jour (nouveau flux login + multi-events) |

### Décisions clés / Key decisions

- **OTP parqué** (code conservé) → réintégration future dans l'offcanvas de connexion.
- **Lieu partagé** : tous les évènements d'une proposition au même lieu choisi à l'étape 1.
- **Image de brouillon** : `event.img.name = chemin` au finalize (une seule sauvegarde → signaux 1×).
- **HTMX add** : renvoi **200** sur erreur de validation (pas de config swap-on-422 dans le skin reunion).
- **Routage** : `SimpleRouter` inclus avant `EventMVT` pour que `event/propose/...` résolve avant `event/{pk}/`.

### Migration

- **Migration nécessaire / Migration required:** Non (aucun changement de modèle ; `Event.is_proposal` existe déjà depuis la migration 0209).

### À surveiller / Watch out

- Tests `tests/pytest/test_event_wizard_public.py` à adapter (testaient le flow OTP/anonyme) — différé.
- i18n : `makemessages` / `compilemessages` à lancer (nouvelles chaînes).
- Images de brouillons abandonnés (wizard quitté sans finaliser) : restent dans `event_wizard_drafts/` (pas de purge auto).
