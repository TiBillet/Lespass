# EVENT_WIZARD — Chantier 01 : wizards de création et proposition d'évènement

**Date :** 2026-05-19
**Statut :** Spec rédigée, en attente de revue (puis writing-plans)
**Auteur :** brainstorming session

## 1. Contexte

La page `event/list` de BaseBillet (skin `reunion`) propose aujourd'hui :
- un offcanvas admin "Ajouter un évènement" (`simple_add_event.html`) accessible uniquement aux admins du tenant via `CanCreateEventPermission` ;
- depuis cet offcanvas, un sous-formulaire texte pour créer une nouvelle adresse `PostalAddress` (sans carte) ;
- aucun moyen pour un visiteur anonyme de proposer un évènement.

Le wizard d'onboarding (`onboard/`, déployé 2026-05-14) a introduit :
- un **widget carte adresse réutilisable** (`templates/widgets/widget_carte_adresse.html`) avec Leaflet + leaflet-geosearch + marqueur draggable + géocodage inverse serveur ;
- un **mini-formulaire d'event** dans la step 5 (`event_row_form.html`) : nom, datetime, description, image.

Ce chantier vise à :
1. **Améliorer le formulaire admin** en remplaçant l'offcanvas par un wizard 2 étapes (Lieu → Event), en réutilisant le widget carte et le mini-form onboard.
2. **Créer un wizard public anonyme** sur `event/list` permettant à tout visiteur de proposer un évènement, protégé par OTP email. L'évènement est créé `published=False` et soumis à modération admin.
3. **Mettre en place un service OTP DRY** réutilisable pour le wizard public et pour un futur login OTP.

## 2. Décisions structurantes

| Sujet | Décision |
|---|---|
| Architecture | Tout dans BaseBillet, pas de modèle draft (session HTTP) |
| Wizard admin | 2 étapes (Lieu → Event) |
| Wizard public | OTP email + 2 étapes (Lieu → Event) |
| Modération | Badge Unfold sur le menu "Events" (count `is_proposal=True & published=False`) |
| Stockage propositions | Nouveau champ `Event.is_proposal` (BooleanField) |
| UI event/list | Deux boutons distincts : admin voit les deux, anonyme voit "Proposer" |
| Champs admin | mini-form (name, datetime, long_description, image) + `jauge_max` + `tags` |
| Champs public | strict mini-form (name, datetime, long_description, image) |
| Service OTP | Module `AuthBillet/otp_service.py` stateless + helper `OtpSession` pour session HTTP |
| Onboard | Inchangé (continue d'utiliser `WaitingConfiguration` pour son OTP) |

## 3. Architecture

```
AuthBillet/
├── otp_service.py                              # NOUVEAU — service stateless (4 fonctions pures)
├── otp_session.py                              # NOUVEAU — helper session HTTP préfixé
└── templates/auth/emails/
    ├── otp_code.html                           # NOUVEAU — template OTP générique
    └── otp_code.txt                            # NOUVEAU

BaseBillet/
├── views.py                                    # +EventWizardAdmin, EventWizardPublic ViewSets
├── validators.py                               # +WizardPlaceSerializer, +WizardEventAdminSerializer,
│                                               #  +WizardEventPublicSerializer, +EventProposalEmailSerializer
├── models.py                                   # +Event.is_proposal (BooleanField, default=False)
├── urls.py                                     # +9 routes (4 admin, 5 public)
├── migrations/0XXX_event_is_proposal.py        # nouvelle migration
└── templates/reunion/views/event/
    ├── list.html                               # MODIF : 2 boutons (admin + public anonyme)
    └── wizard/                                 # NOUVEAU
        ├── _base.html                          # layout wizard centré
        ├── _form_lieu.html                     # partial toggle existante/nouvelle adresse
        ├── admin_step1_place.html
        ├── admin_step2_event.html
        ├── public_step0_email.html
        ├── public_step0_verify.html
        ├── public_step1_place.html
        ├── public_step2_event.html
        └── public_done.html

Administration/
├── admin/dashboard.py                          # +event_proposals_badge_callback
└── admin_tenant.py                             # +badge sur item Events + filtre is_proposal + action bulk
```

### URLs nommées Django (référence)

| Nom URL | Path | Méthodes | Vue |
|---|---|---|---|
| `event-admin-wizard-place` | `/event/admin/wizard/place/` | GET, POST | `EventWizardAdmin.step1_place` |
| `event-admin-wizard-event` | `/event/admin/wizard/event/` | GET, POST | `EventWizardAdmin.step2_event` |
| `event-propose-email` | `/event/propose/email/` | GET, POST | `EventWizardPublic.step0_email` |
| `event-propose-verify` | `/event/propose/verify/` | GET, POST | `EventWizardPublic.step0_verify` |
| `event-propose-resend` | `/event/propose/resend/` | POST | `EventWizardPublic.step0_resend` |
| `event-propose-place` | `/event/propose/place/` | GET, POST | `EventWizardPublic.step1_place` |
| `event-propose-event` | `/event/propose/event/` | GET, POST | `EventWizardPublic.step2_event` |
| `event-propose-done` | `/event/propose/done/` | GET | `EventWizardPublic.done` |

Note : la route `/event/propose/` racine fait un `redirect` vers `event-propose-email`.

### Code supprimé (cleanup)

| Élément | Action |
|---|---|
| Offcanvas `#adminAddEventPanel` dans `list.html` | supprimé |
| `simple_add_event.html` | supprimé |
| `address_simple_add.html` | supprimé |
| `EventMVT.simple_add_event` (vue) | supprimée |
| `EventMVT.simple_create_event` | supprimée |
| `EventMVT.address_add_form` | supprimée |
| `EventMVT.address_create` | supprimée |
| `EventMVT.get_permissions` (branches simple_*) | nettoyée |
| `EventQuickCreateSerializer` | conservé si utilisé ailleurs, sinon supprimé (vérification à faire au début de l'implémentation) |

## 4. Service OTP DRY

**Spec complète dans le hub dédié : [TECH_DOC/SESSIONS/OTP/SPEC.md](../OTP/SPEC.md).**

Résumé pour ce chantier :
- Le service vit dans `AuthBillet/otp_service.py` (4 fonctions pures stateless) + `AuthBillet/otp_session.py` (helper classe `OtpSession` pour stockage en session HTTP).
- Templates email partagés : `AuthBillet/templates/auth/emails/otp_code.{html,txt}`.
- Le wizard public event est le **premier consommateur** du service. Onboard reste inchangé (continue d'utiliser sa logique custom basée sur `WaitingConfiguration`).
- Le chantier 01 d'EVENT_WIZARD inclut la création du service OTP. Le chantier 01 d'OTP **est** ce travail-là, documenté séparément pour faciliter les futurs branchements (login OTP, SSO, migration onboard).

Usage côté wizard event public :

```python
from AuthBillet.otp_session import OtpSession

# Step 0a : envoi du code
otp = OtpSession(request, prefix="event_proposal")
otp.start(
    email=validated_data["email"],
    libelle_action=str(_("Proposer un evenement")),
    nom_organisation=Configuration.get_solo().organisation,
)

# Step 0b : verification
if otp.verify(request.POST.get("otp", "")):
    return redirect("event-propose-place")

# Garde au debut des steps 1 et 2
if not otp.is_confirmed():
    return redirect("event-propose-email")

# Apres soumission finale du wizard
otp.reset()
```

## 5. Wizard admin (2 étapes)

### 5.1 Step 1 — Lieu (`/event/admin/wizard/place/`)

- Permission : `CanCreateEventPermission`.
- GET : formulaire avec deux modes mutuellement exclusifs via radio + CSS sibling selector (pas de JS).
  - Mode "Utiliser une adresse existante" : `<select>` peuplé de `PostalAddress.objects.all()`, adresse par défaut config pré-sélectionnée.
  - Mode "Créer un nouveau lieu" : champ `<input name="new_address_name">` au-dessus du widget carte `{% include "widgets/widget_carte_adresse.html" with identifiant_widget="place" ... %}`.
- POST :
  1. Validation `WizardPlaceSerializer`.
  2. Si nouvelle adresse : `PostalAddress` créée immédiatement via `PostalAddressCreateSerializer` (api_v2) en ajoutant `name`, `latitude`, `longitude`. Pk stocké en session `event_wizard_admin_postal_address_pk`.
  3. Si existante : pk stocké en session.
  4. Redirect `step2_event`.
- Erreur 422 : re-rend la page avec `errors` + `initial` (valeurs pré-remplies dans le widget via `latitude_initiale`, `longitude_initiale`, `adresse_initiale`).

### 5.2 Step 2 — Event (`/event/admin/wizard/event/`)

- Garde : si pas de `postal_address_pk` en session → redirect step 1.
- GET : mini-form `name`, `datetime`, `long_description`, `image` + `jauge_max` + `tags` (datalist depuis `Tag.objects.all()`). Affiche en haut un rappel "Lieu choisi : ..." avec lien "← Modifier le lieu".
- POST :
  1. Validation `WizardEventAdminSerializer`.
  2. `Event.objects.create(..., published=True, is_proposal=False, postal_address_id=..., created_by=request.user)`.
  3. Tags : split comma/semicolon, `Tag.objects.get_or_create` pour chaque (variable `_tag_obj, _created` — jamais `_` qui écraserait `gettext`).
  4. Si `jauge_max` renseigné : `event.show_gauge=True`, attache le produit FREERES (reprendre la logique existante de `EventQuickCreateSerializer.create`).
  5. Nettoie clés session `event_wizard_admin_*`.
  6. `messages.SUCCESS(...)` + redirect vers la page detail de l'event créé.
- Erreur 422 : re-rend la page avec erreurs + initial. L'adresse choisie reste en session.

## 6. Wizard public anonyme (OTP + 2 étapes)

### 6.1 Step 0a — Email (`/event/propose/email/`)

- Permission : `AllowAny`. Throttle : `AnonRateThrottle` (3 demandes / heure / IP) sur le POST.
- GET : page expliquant le flow + champs `email` + `email_confirm` + honeypot caché `<input name="website" tabindex="-1" autocomplete="off" style="display:none">`.
- POST :
  1. Si honeypot rempli → 422 silencieuse (anti-bot).
  2. Validation `EventProposalEmailSerializer` (email + email_confirm match, case-insensitive).
  3. `OtpSession(request, "event_proposal").start(email, libelle_action=_("Proposer un évènement"), nom_organisation=Configuration.get_solo().organisation)`.
  4. Redirect `step0_verify`.

### 6.2 Step 0b — Verify (`/event/propose/verify/`)

- Garde : si pas d'email en session → redirect step 0a.
- GET : champ OTP 6 chiffres + email cible affiché + lien "Renvoyer le code" (POST step0_resend).
- POST :
  1. `OtpSession.verify(code)`.
  2. OK → redirect step 1.
  3. KO → 422 + message "Code incorrect ou expiré".
  4. Si attempts ≥ MAX → `reset()` + redirect step 0a avec message d'erreur.

### 6.3 Step 0c — Resend (`/event/propose/resend/`, POST only)

- Garde : `can_resend()` ? Sinon 429 + message "Patientez X secondes."
- Sinon : `start(email_existant, libelle_action)` à nouveau.
- Redirect step 0b + toast "Nouveau code envoyé".

### 6.4 Step 1 — Lieu (`/event/propose/place/`)

- Garde : `OtpSession.is_confirmed()` ? Sinon redirect step 0a.
- GET/POST : même logique que step 1 admin. Stocke `event_wizard_public_postal_address_pk` en session.

### 6.5 Step 2 — Event (`/event/propose/event/`)

- Gardes : `is_confirmed()` + `postal_address_pk` en session.
- GET : mini-form strict `name`, `datetime`, `long_description`, `image`. Pas de jauge, pas de tags. Rappel "Lieu : ...".
- POST :
  1. Validation `WizardEventPublicSerializer`.
  2. `Event.objects.create(..., published=False, is_proposal=True, postal_address_id=..., created_by=None)`.
  3. Nettoie toutes les clés session `event_wizard_public_*` ET les clés OTP (une proposition = une session terminée, pas de spam multi-soumission).
  4. Redirect `done`.

### 6.6 Step done (`/event/propose/done/`)

- Page idempotente, pas de garde session.
- Message "Merci, votre proposition est en attente de validation par un administrateur."
- Lien retour `/event/`.

## 7. Modèle : `Event.is_proposal`

```python
# BaseBillet/models.py
class Event(models.Model):
    ...
    is_proposal = models.BooleanField(
        default=False,
        verbose_name=_("Public proposal"),
        help_text=_("Event submitted via the public proposal wizard, awaiting admin validation."),
    )
```

Migration `BaseBillet/migrations/0XXX_event_is_proposal.py` : additive, default `False`. Aucune data migration nécessaire (les events existants restent `is_proposal=False`).

## 8. Modération admin

### 8.1 Badge sidebar Unfold

```python
# Administration/admin/dashboard.py
def event_proposals_badge_callback(request):
    """Compte des propositions d'event en attente.
    / Count of pending event proposals."""
    from BaseBillet.models import Event
    count = Event.objects.filter(is_proposal=True, published=False).count()
    return f"+ {count}" if count else None
```

Branchement dans `get_sidebar_navigation` : item Events sous le module `module_billetterie`, ajouter `"badge": "Administration.admin.dashboard.event_proposals_badge_callback"`.

### 8.2 Filtre changelist EventAdmin

Nouveau `SimpleListFilter` `IsProposalFilter` avec 3 choix :
- "Proposals pending" → `is_proposal=True, published=False`
- "Regular events" → `is_proposal=False`
- "Approved proposals" → `is_proposal=True, published=True`

### 8.3 Action bulk `approuver_propositions`

```python
@admin.action(description=_("Approve and publish selected proposals"))
def approuver_propositions(self, request, queryset):
    nb_approuvees = queryset.filter(is_proposal=True, published=False).update(
        is_proposal=False,
        published=True,
    )
    self.message_user(request, _("%(n)s proposal(s) approved.") % {"n": nb_approuvees})
```

## 9. Sécurité

| Risque | Mitigation |
|---|---|
| Spam soumissions publiques | OTP email + honeypot + `AnonRateThrottle` (3/h sur step0_email + step0_resend) |
| Bypass OTP | Garde `is_confirmed()` au début de chaque vue post-OTP |
| OTP brute-force | Max 5 tentatives, hash SHA-256, `hmac.compare_digest` |
| Upload abusif | Validation image : 5 Mo max + content_type whitelist (jpeg/png/webp) |
| XSS `long_description` | `admin_clean_html` (déjà utilisé par `EventQuickCreateSerializer`) |
| Admin permissions | `CanCreateEventPermission` sur EventWizardAdmin |
| CSRF | Token sur tous les forms POST |

## 10. Templates

### 10.1 `_base.html` (layout wizard)

Extends `base_template` (récupéré via `get_context` selon `request.htmx`). Container Bootstrap centré max-width 720px. Header avec titre wizard + indicateur "Étape X / Y". Bouton "← Précédent" si applicable. `{% block step_content %}` pour le corps.

### 10.2 `_form_lieu.html` (partial)

Variables attendues : `form_action_url`, `addresses`, `default_address_pk`, `initial`, `errors`. Toggle radio CSS-only entre "Adresse existante" et "Nouveau lieu". Le widget carte n'apparaît que dans le mode "Nouveau lieu" (visibilité contrôlée par CSS `:checked ~ *`).

Inclus tel quel par `admin_step1_place.html` et `public_step1_place.html` (action URL et bouton "Continuer" diffèrent uniquement).

### 10.3 Pages event/list

```html
<!-- list.html — bloc filtres / actions -->
<div class="ms-auto d-flex align-items-center gap-2">
    <!-- ... toggle filtres mobile ... -->
    {% if user|can_create_event_tag %}
        <a class="btn btn-sm btn-success" href="{% url 'event-admin-wizard-place' %}"
           data-testid="btn-event-admin-add">
            <i class="bi bi-plus-circle" aria-hidden="true"></i>
            {% translate "Ajouter un évènement" %}
        </a>
    {% endif %}
    <a class="btn btn-sm btn-outline-secondary" href="{% url 'event-propose-email' %}"
       data-testid="btn-event-public-propose">
        <i class="bi bi-megaphone" aria-hidden="true"></i>
        {% translate "Proposer un évènement" %}
    </a>
</div>
```

## 11. Tests pytest (DB-only, ~57 tests, ~10s)

Fichiers :
- `tests/pytest/test_otp_service.py` — service stateless (~10 tests)
- `tests/pytest/test_otp_session.py` — helper session (~12 tests)
- `tests/pytest/test_event_wizard_admin.py` — wizard admin 2 steps (~14 tests)
- `tests/pytest/test_event_wizard_public.py` — wizard public OTP + 2 steps (~16 tests)
- `tests/pytest/test_event_proposal_admin_badge.py` — badge + filtre + action bulk (~5 tests)

Couverture cible :
- `AuthBillet/otp_service.py` : 100%
- `AuthBillet/otp_session.py` : 100%
- Wizards (vues + serializers) : ≥ 90%

Pièges connus (cf. `tests/PIEGES.md`) à éviter :
- `tenant_context` plutôt que `schema_context` quand le code accède à `connection.tenant.uuid`.
- Variables `_created` (jamais `_`) pour ne pas masquer `gettext._`.
- Mock `AuthBillet.otp_service.envoyer_email_otp` directement (pas `django.core.mail`).
- Pour tester l'expiration OTP : `freezegun` ou `monkeypatch` sur `django.utils.timezone.now`.

Tests E2E Playwright (validation HTML5, widget carte interactif, transitions wizard) : reportés à un chantier futur.

## 12. CHANGELOG

Entrée à ajouter dans `CHANGELOG.md` du repo après implémentation :

```
## N. Wizards de création et proposition d'évènement / Event wizards

**Quoi / What:** Refonte de la création d'évènement en wizard 2 étapes (admin) et ajout d'un wizard public anonyme protégé par OTP email pour proposer des évènements soumis à modération.
**Pourquoi / Why:** Améliorer l'UX admin (carte interactive pour les nouvelles adresses) et ouvrir la plateforme aux contributions publiques avec modération.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service OTP stateless DRY |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `AuthBillet/templates/auth/emails/otp_code.{html,txt}` | NOUVEAU — templates email génériques |
| `BaseBillet/models.py` | +`Event.is_proposal` (BooleanField) |
| `BaseBillet/views.py` | +EventWizardAdmin, +EventWizardPublic. -EventMVT.simple_* |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/urls.py` | +9 routes wizard |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `BaseBillet/templates/reunion/views/event/list.html` | -offcanvas, +2 boutons |
| `BaseBillet/templates/reunion/views/event/partial/simple_add_event.html` | supprimé |
| `BaseBillet/templates/reunion/views/event/partial/address_simple_add.html` | supprimé |
| `Administration/admin/dashboard.py` | +event_proposals_badge_callback |
| `Administration/admin_tenant.py` | +badge Events + filtre IsProposalFilter + action approuver_propositions |

### Migration
- **Migration nécessaire / Migration required:** Oui
- `BaseBillet/migrations/0XXX_event_is_proposal.py` (additive, default=False, aucune data migration)
```

## 13. Documentation `A TESTER et DOCUMENTER/`

Créer `A TESTER et DOCUMENTER/event-wizards.md` avec scénarios manuels :
1. Wizard admin : créer un event avec adresse existante.
2. Wizard admin : créer un event avec nouvelle adresse (carte).
3. Wizard public : flow OTP complet jusqu'à la page "Merci".
4. Modération : badge sidebar + filtre admin + action bulk "Approuver".
5. Anti-spam : honeypot + throttle DRF (3 emails consécutifs en < 1h → 429).
6. Sécurité : tentative de bypass (POST direct step 2 sans OTP) → redirect step 0.

## 14. Hors scope

- Migration onboard vers le service OTP DRY (chantier futur, optionnel).
- Notification email à l'admin lors d'une nouvelle proposition (le mainteneur préfère le badge Unfold seul).
- Stockage de l'email du proposant dans Event (pas de traçabilité demandée).
- Page admin dédiée aux propositions (le filtre + l'action bulk dans `EventAdmin` suffisent).
- Tests E2E Playwright (chantier futur).
