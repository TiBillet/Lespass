# Review de la branche `template-faire-festival`

Branche basee sur `PreProd`. ~64 fichiers modifies, ~2274 lignes ajoutees, ~727 supprimees.

## Contenu de la branche — par theme

### 1. Template Faire Festival (theme brutaliste)

Nouveau theme CSS pur pour le Faire Festival (polices custom Faire-Regular/Stencil, palette jaune/bleu/blanc).

**Fichiers :**
- `BaseBillet/static/faire_festival/` — CSS, fonts, images, video
- `BaseBillet/templates/faire_festival/` — base, navbar, home, event/list, event/retrieve, membership/list
- `BaseBillet/templates/faire_festival/maquette/` — maquette HTML statique de reference

**Points de review :**
- [x] Accueil avec video (`motion-table.mp4`)
- [x] Navbar avec boutons contact/login/mes billets
- [x] Page programmation (liste events) avec filtres par tags
- [x] Page detail event avec offcanvas reservation (reutilise `reunion/views/event/partial/booking_form.html`)
- [ ] Bouton "Je m'inscris" sur la page liste — **COMMENTE, a reprendre avec une vue back dediee pour la resa gratuite**
- [ ] Offcanvas reservation sur la page liste — **COMMENTE, idem**

### 2. Bugfixes back-end

**a) Montants FREERES (reservation gratuite)**
- `BaseBillet/migrations/0198_fix_free_lignearticle_amount.py` — data migration pour corriger les montants existants
- `BaseBillet/models.py` — `paid()` retourne 0 pour les paiements gratuits
- `BaseBillet/views.py` — count free tickets as 0 EUR dans les aggregats (price_min/price_max)

**b) Meta URL crash**
- `BaseBillet/views.py` (get_context) — `Client.objects.filter(...).first()` + guard `if meta:` au lieu de `[0]` qui crashait si pas de Client META

**c) Lost my card — try/except**
- `BaseBillet/views.py` — `lost_my_card` et `admin_lost_my_card` : wrappent l'appel FedowAPI dans un try/except pour eviter les 500

**d) Event date grouping**
- `BaseBillet/views.py` — `event.datetime.date()` au lieu de `event.datetime` pour le groupement par date

**e) Tri des prix publies**
- `BaseBillet/views.py` — `.order_by('product__poids', 'order', 'prix')` au lieu de `('order', 'prix')`

**f) WaitingConfiguration tenant linkage**
- `BaseBillet/views.py` (Tenant) — `wc.tenant = existing_client` si manquant, evite les duplicatas

**g) Contribution value nullable**
- `BaseBillet/migrations/0197_alter_membership_contribution_value.py`

**h) Validation montant custom**
- `BaseBillet/validators.py` — max 999999.99 sur les montants custom
- `BaseBillet/templates/reunion/views/event/partial/booking_form.html` — `max="999999.99"` sur l'input
- `BaseBillet/templates/reunion/views/membership/form.html` — idem pour adhesions

### 3. Nouvelles fonctionnalites

**a) Discovery (pairing PIN)**
- Nouvelle app `discovery/` — modeles, admin, API, serializers, permissions
- Pairing de devices par code PIN (6 chiffres)

**b) Reset cashless handshake**
- `Administration/management/commands/reset_cashless_handshake.py`

**c) Custom form fields pour adhesions**
- `Administration/templates/admin/membership/partials/custom_form_add_field.html`

### 4. Infra / Config

- `docker-compose.yml` — restructure, stack Fedow commentee
- `env_example` — enrichi (email, Stripe, Formbricks)
- `.gitignore` — ajout
- `VERSION` — 1.7.1
- `CHANGELOG.md` — notes de version
- `TiBillet/settings.py` — ajouts config
- `TiBillet/urls_public.py` — route discovery
- Suppression : `dockerfile_nightly`, `license_audit.py`, `import_membership_csv_exemple.csv`

### 5. Tests

- `tests/playwright/tests/26-admin-membership-custom-form-edit.spec.ts` — refactored
- `tests/playwright/tests/28-numeric-overflow-validation.spec.ts` — nouveau

---

## Plan de review — par parties

### Partie 1 : Bugfixes back-end (2a-2h) — FAIT
- Verifier chaque fix isolement
- S'assurer que les migrations sont coherentes

### Partie 2 : Template Faire Festival (1)
- Review CSS/HTML
- Tester navigation, responsive, offcanvas
- Verifier accessibilite (contrastes, labels)
- **Le bouton "Je m'inscris" et l'offcanvas de resa sur la page liste sont COMMENTES** — a reprendre plus tard avec une vue back dediee pour la resa gratuite uniquement

### Partie 3 : Discovery app (3a)
- Review modeles, permissions, securite du PIN
- Tester le flow de pairing

### Partie 4 : Infra / Config (4)
- Review docker-compose, env_example
- Verifier que rien de sensible n'est committe

### Partie 5 : Tests (5)
- Lancer les tests PW 26 et 28
- Verifier couverture
