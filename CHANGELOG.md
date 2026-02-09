# Changelog / Journal des modifications

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*
