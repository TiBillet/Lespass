# CHANTIER 04 — Flasher le QR code d'une carte dans « Ajouter une adhésion »

**Date :** 2026-11-27
**Statut :** spec relue par Fable (2026-11-27), corrections intégrées ; codé le 2026-11-27, non commité
**Migration :** non

## 1. Besoin

Page `/admin/BaseBillet/membership/add/` : le champ « Numéro de carte »
(`MembershipAddForm.card_number`) se saisit à la main. Le gestionnaire recopie
les 8 caractères imprimés sur la carte.

On ajoute un bouton **« Flasher le QR code de la carte »**. Il ouvre la caméra,
lit le QR code imprimé sur la carte et remplit le champ.

**Aucune requête serveur au moment du scan.** La vérification de la carte reste
celle d'aujourd'hui, à l'enregistrement du formulaire
(`MembershipAddForm.clean_card_number()`, appel Fedow).

## 2. Faits établis (code réel)

- **Unfold n'a pas de scanner caméra** (ni widget, ni composant).
- **Le projet a déjà une lib de lecture de QR code** : `qr-scanner` (nimiq),
  `BaseBillet/static/commun/js/qr-scanner.min.js` + `qr-scanner-worker.min.js`
  dans le même dossier. La lib charge son worker par un `import()` relatif à son
  propre fichier : il suffit que les deux fichiers soient côte à côte.
  Elle est déjà utilisée par `BaseBillet/templates/fonctionnel/qrcode_scan_pay/scanner.html`
  (`<script type="module">`, `new QrScanner(video, onDecode, {returnDetailedScanResult: true, ...})`).
- **Contenu du QR code d'une carte :** une adresse web contenant l'UUID de la carte :
  - `https://lieu.tld/qr/<uuid>/` (format courant) ;
  - `https://lieu.tld/<uuid>` (cartes imprimées sans le préfixe `/qr/`, cf.
    `BaseBillet/urls.py:101-105`, redirigé vers `/qr/<uuid>/`).
- **Numéro imprimé = 8 premiers caractères de l'UUID, en majuscules.** C'est
  l'invariante `number == uuid.hex[:8].upper()` de la SPEC du hub (§ 4.2).
  - **C'est une convention, pas une contrainte.** Fedow ne la vérifie pas
    (`../Fedow/fedow_core/management/commands/import_cards.py:55-72`,
    `../Fedow/fedow_core/serializers.py:300-310`). Seul le formulaire admin
    d'ajout de carte de Lespass l'impose. Les cartes de production n'ont pas été
    vérifiées.
  - **Attention en dev :** la plupart des cartes de la base de dev (fixtures
    anciennes) ne respectent pas cette invariante (`number == tag_id`, UUID
    aléatoire). Seules 7 cartes sur 49 la respectent (UUID du type
    `a49e8e2a-0000-4000-8000-000000000000`). Les tests manuels utilisent l'une
    d'elles.
- **Le champ :** `card_number = forms.CharField(required=False, min_length=8,
  max_length=8, widget=UnfoldAdminTextInputWidget())`
  (`Administration/admin_tenant.py`, classe `MembershipAddForm`).
  `clean_card_number()` fait déjà `strip().upper()` et vérifie le format hexa.
- **Le widget Unfold :** `UnfoldAdminTextInputWidget.template_name =
  "unfold/widgets/text.html"`. Ce gabarit rend le `<input>` via
  `django/forms/widgets/input.html`, dans une `div.max-w-2xl`.

## 3. Design

### 3.1 Un widget dédié

Dans `Administration/admin_tenant.py`, juste avant `MembershipAddForm` :

```python
class CardNumberQrScanWidget(UnfoldAdminTextInputWidget):
    # Même champ texte Unfold, avec en plus un bouton qui lit le QR code
    # de la carte à la caméra. Tout se passe dans le navigateur.
    # / Same Unfold text input, plus a button that reads the card QR code.
    template_name = "admin/widgets/card_number_qr_scan.html"
```

`MembershipAddForm.card_number` utilise `CardNumberQrScanWidget()` à la place
de `UnfoldAdminTextInputWidget()`. Rien d'autre ne change dans le formulaire.

**Choix écarté :** un script dans `admin/membership/custom_form.html`
(`change_form_after_template`) qui irait chercher `#id_card_number` pour y
glisser un bouton. Le widget rend le bouton avec le champ : pas d'injection DOM,
et le bouton suit le champ partout où il est utilisé.

### 3.2 Le gabarit du widget

`Administration/templates/admin/widgets/card_number_qr_scan.html` :

1. `{% include "unfold/widgets/text.html" %}` : le champ d'origine, inchangé.
2. Un bouton `type="button"` « Flasher le QR code de la carte »
   (`data-testid="membership-card-qr-start"`).
3. Un bouton `type="button"` « Arrêter la caméra », caché par défaut
   (`data-testid="membership-card-qr-stop"`).
4. Un `<video>` caché par défaut **par `style="display:none"`, jamais par
   l'attribut `hidden`** (`playsinline`, `muted`,
   `data-testid="membership-card-qr-video"`). Si la vidéo porte `hidden` au
   moment du `new QrScanner(...)`, la lib retire `hidden` et force en style
   inline opacité 0, largeur 0, hauteur 0 : la vidéo resterait invisible.
5. Un message `aria-live="polite"` (`data-testid="membership-card-qr-message"`).
6. Un `<script type="module">` qui importe `QrScanner` depuis
   `{% static 'commun/js/qr-scanner.min.js' %}`.

Les ids des éléments dérivent de `widget.attrs.id` (`id_card_number`).
Le gabarit commence par `{% load i18n static %}` (le moteur des formulaires n'a
pas de `builtins`).
Les textes du JS passent en `data-*` sur le conteneur, traduits par
`{% translate %}` (pas de chaînes en dur dans le JS).
Styles **inline** (règle Unfold), couleurs via `var(--color-primary-600)`.

### 3.3 Le comportement (JS, dans le navigateur)

1. **Clic sur « Flasher »** : le scanner est créé au premier clic (pas avant :
   aucune demande d'accès caméra au chargement de la page).
   Ordre imposé : **afficher la vidéo, PUIS `new QrScanner(video, onDecode,
   {returnDetailedScanResult: true, highlightScanRegion: true})`, PUIS
   `start()`**. Le 3ᵉ argument doit être un objet : sinon la lib passe en
   ancienne API (résultat = chaîne). La caméra arrière est le défaut de la lib.
   La vidéo et le bouton « Arrêter » s'affichent.
2. **QR code lu** (`result.data`) : le texte doit être une adresse web dont le
   **chemin** est `/qr/<uuid>/` ou `/<uuid>/` (barre finale facultative).
   Regex sur `new URL(texte).pathname` :
   `^\/(?:qr\/)?([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/?$` (insensible à la casse).
   - **Trouvé** → `numéro = groupe1.toUpperCase()`. On remplit le
     champ, on émet `input` (`dispatchEvent(new Event("input", {bubbles: true}))`,
     sinon `warn_unsaved_form` d'Unfold ne voit pas le changement), on arrête la
     caméra, on cache la vidéo, on annonce « Numéro de carte rempli : XXXXXXXX ».
   - **Pas trouvé** → message « Ce QR code n'est pas celui d'une carte. ».
     La caméra continue de lire (le gestionnaire présente la bonne carte).
     Le message n'est pas répété en boucle pour le même texte lu.
3. **Clic sur « Arrêter »** : `qrScanner.stop()`, vidéo et bouton cachés.
4. **Caméra impossible** (`start()` rejeté : permission refusée, pas de caméra,
   page hors HTTPS) → message « Caméra indisponible ou accès refusé. ».
   Pas de plantage : la saisie à la main reste possible. La lib rejette avec
   une chaîne (`"Camera not found."`), pas un `Error`.
5. **Limite assumée** : une carte hors convention (numéro imprimé ≠ 8 premiers
   caractères de l'UUID) donne 8 caractères faux. Le serveur répond « Unknown
   card number » à l'enregistrement. Le gestionnaire saisit alors à la main le
   numéro imprimé.

Le JS ne valide rien d'autre. La vérification (format hexa, carte connue de
Fedow, carte libre) reste côté serveur dans `clean_card_number()`.

## 4. Fichiers

| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | Classe `CardNumberQrScanWidget` ; widget de `MembershipAddForm.card_number` |
| `Administration/templates/admin/widgets/card_number_qr_scan.html` | Nouveau : champ + boutons + vidéo + script |
| `tests/pytest/test_admin_membership_scan_qr_carte.py` | Nouveau : la page d'ajout affiche le bouton et charge le script |
| `CHANGELOG/2026-11-27-adhesion-scan-qr-carte.md` | Nouveau |

## 5. Tests

- **pytest** : un admin ouvre `GET /admin/BaseBillet/membership/add/` →
  code 200, le HTML contient `data-testid="membership-card-qr-start"`,
  le `<input name="card_number">` et le chemin `commun/js/qr-scanner.min.js`.
  Vérifié par mutation (retirer le widget → le test échoue).
  **Limite assumée :** ce test ne prouve ni l'extraction de l'UUID ni la mise
  en majuscules (pas de JS en pytest). Cette logique est vérifiée à la main.
- **À la main (Chrome)** : afficher sur un téléphone le QR code
  `https://lespass.tibillet.localhost/qr/a49e8e2a-0000-4000-8000-000000000000/`
  → le champ reçoit `A49E8E2A`. Un QR code quelconque → message
  « pas une carte ». Refus de la caméra → message « caméra indisponible ».
- **Pas d'E2E caméra** : une fausse caméra Chromium
  (`--use-file-for-fake-video-capture`) demande une vidéo `.y4m` du QR code.
  Trop lourd pour ce besoin.

## 6. i18n

5 chaînes nouvelles, source en français : « Flasher le QR code de la carte »,
« Arrêter la caméra », « Numéro de carte rempli : », « Ce QR code n'est pas
celui d'une carte. », « Caméra indisponible ou accès refusé. ».
Workflow i18n à lancer par le mainteneur.
