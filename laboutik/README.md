# LaBoutik — Caisse enregistreuse tactile

Application de caisse enregistreuse (POS) pour terminaux tactiles, integrée dans l'ecosystème TiBillet/Lespass.

Interface full-screen pensée pour tablettes et écrans tactiles, avec lecture NFC pour les cartes cashless.

## Statut actuel

**Données 100% mockées.** L'interface est fonctionnelle mais toutes les données (articles, points de vente, cartes, paiements) viennent de fichiers JSON statiques dans `utils/`. Les vrais modèles Django seront construits dans une étape ultérieure.

## Architecture

### Stack technique

| Couche | Techno |
|--------|--------|
| Backend | Django 4.2 + DRF ViewSets (pattern FALC) |
| Frontend | HTMX 2.0.6 + django-cotton (composants `<c-xxx>`) |
| CSS | CSS custom properties (palette, sizes) — pas de framework CSS |
| Icônes | FontAwesome 5 (migration Bootstrap Icons prévue) |
| NFC | Web NFC API + simulation en mode démo |

### Authentification — deux modes d'accès

**1. Terminal / appareil (API Key)**

Le flux d'appairage passe par l'app Discovery :

```
Admin crée un PairingDevice (PIN 6 chiffres) dans l'admin Unfold
     ↓
Terminal POST /api/discovery/claim/ avec le PIN
     ↓
Lespass valide le PIN, crée une LaBoutikAPIKey dans le schema tenant
     ↓
Terminal reçoit { api_key, server_url, device_name }
     ↓
Toutes les requêtes suivantes : Authorization: Api-Key <key>
```

Le PIN est à usage unique — détruit après claim.

**2. Navigateur admin (session Django)**

Un admin connecté au tenant peut accéder directement à `/laboutik/caisse/` via son navigateur. La permission `HasLaBoutikAccess` (`BaseBillet/permissions.py`) vérifie :
- Soit une clé API valide (header `Authorization`)
- Soit un user authentifié + admin du tenant courant (`is_tenant_admin`)

### Multi-tenancy

LaBoutik est une **tenant app** (dans `TENANT_APPS`). Les URLs sont routées via `urls_tenants.py`, donc accessibles uniquement sur les sous-domaines tenant (ex: `lespass.tibillet.localhost/laboutik/`), pas sur le domaine racine.

### ViewSets DRF

Deux ViewSets, tous avec `permission_classes = [HasLaBoutikAccess]` :

**`CaisseViewSet`** (prefix: `/laboutik/caisse/`)

| URL | Méthode | Action | Description |
|-----|---------|--------|-------------|
| `/caisse/` | GET | `list` | Page d'attente carte primaire |
| `/caisse/carte_primaire/` | POST | `carte_primaire` | Valide la carte NFC, redirige vers le PV |
| `/caisse/point_de_vente/` | GET | `point_de_vente` | Interface POS (service direct / tables / kiosk) |

**`PaiementViewSet`** (prefix: `/laboutik/paiement/`)

| URL | Méthode | Action | Description |
|-----|---------|--------|-------------|
| `/paiement/moyens_paiement/` | POST | `moyens_paiement` | Affiche les types de paiement disponibles |
| `/paiement/confirmer/` | GET | `confirmer` | Ecran de confirmation avant paiement |
| `/paiement/payer/` | POST | `payer` | Exécute le paiement (mock) |
| `/paiement/lire_nfc/` | GET | `lire_nfc` | Partial attente lecture NFC |
| `/paiement/verifier_carte/` | GET | `verifier_carte` | Partial vérification carte |
| `/paiement/retour_carte/` | POST | `retour_carte` | Feedback après lecture carte NFC |

### Arborescence des fichiers

```
laboutik/
├── __init__.py
├── apps.py                          # AppConfig (verbose_name: "LaBoutik (Caisse)")
├── models.py                        # Vide (modèles à créer)
├── views.py                         # 2 ViewSets DRF
├── urls.py                          # DRF router
├── migrations/
│   └── __init__.py
├── utils/
│   ├── __init__.py
│   ├── mockData.py                  # Données mock : PVs, articles, cartes, tables + classe mockDb
│   ├── method.py                    # Fonctions utilitaires paiement
│   ├── dbJson.py                    # Version standalone du mock (non utilisée)
│   └── mockDb.json                  # Base de données JSON fichier (transactions runtime)
├── templatetags/
│   ├── __init__.py
│   └── laboutik_process.py          # Filtres : sel, divide_by, mul, force_dot
├── templates/
│   ├── cotton/                      # Composants django-cotton (réutilisables)
│   │   ├── addition.html            # Panneau addition (formulaire HTMX caché)
│   │   ├── articles.html            # Grille d'articles cliquables
│   │   ├── categories.html          # Barre latérale catégories
│   │   ├── header.html              # Header avec menu burger + navigation PV
│   │   ├── read_nfc.html            # Composant lecture NFC (spinner + simulation démo)
│   │   ├── spinner.html             # Animation spinner SVG
│   │   ├── status_wallets.html      # Affichage solde portefeuille
│   │   └── bt/
│   │       ├── paiement.html        # Bouton moyen de paiement
│   │       └── return.html          # Bouton retour (ferme un layer)
│   └── laboutik/                    # Templates namespacés
│       ├── base.html                # Layout HTML (HTMX, FontAwesome, NFC, state JSON)
│       ├── views/
│       │   ├── ask_primary_card.html    # Attente carte primaire (entrée de l'app)
│       │   ├── common_user_interface.html  # Interface POS principale
│       │   ├── tables.html              # Sélection de table (mode restaurant)
│       │   ├── kiosk.html               # Mode kiosque (placeholder)
│       │   ├── login_hardware.html      # Login hardware (legacy, non utilisé)
│       │   └── test.html
│       └── partial/                 # Fragments HTMX (swaps)
│           ├── hx_display_type_payment.html  # Choix moyen de paiement
│           ├── hx_confirm_payment.html       # Confirmation paiement
│           ├── hx_return_payment_success.html # Paiement réussi
│           ├── hx_funds_insufficient.html    # Fonds insuffisants (paiement fractionné)
│           ├── hx_read_nfc.html              # Attente NFC pour paiement
│           ├── hx_check_card.html            # Vérification carte (check solde)
│           ├── hx_card_feedback.html         # Résultat vérification carte
│           ├── hx_primary_card_message.html  # Messages carte primaire
│           ├── hx_messages.html              # Messages génériques
│           └── no_articles.html              # Aucun article
├── static/
│   ├── css/
│   │   ├── modele00.css             # Styles principaux + layout flex
│   │   ├── palette.css              # Variables CSS couleurs
│   │   ├── sizes.css                # Variables CSS dimensions
│   │   ├── vk.css                   # Styles clavier virtuel
│   │   └── all_fontawesome-free-5-11-2.css  # FontAwesome 5
│   ├── js/
│   │   ├── addition.js              # Logique addition (ajout/suppression articles)
│   │   ├── articles.js              # Gestion grille articles
│   │   ├── nfc.js                   # Classe NfcReader (Web NFC API + simulation)
│   │   ├── tibilletUtils.js         # Utilitaires (sendEvent, hideElement, etc.)
│   │   ├── big.js                   # Bibliothèque calcul décimal
│   │   ├── htmx@2.0.6.min.js       # HTMX
│   │   ├── socket.io.3.0.4.js       # Socket.IO (préparation comm temps réel)
│   │   ├── login_hardware.js        # Login hardware (legacy)
│   │   └── modules/                 # Modules JS supplémentaires
│   └── images/                      # Logos, icônes, images de fond
└── doc/                             # Documentation design (excalidraw)
```

### Flux HTMX

L'interface fonctionne en layers superposés :

```
Layer 0 : Interface principale (articles, catégories, addition)
Layer 1 : #messages — types de paiement, vérification carte, fonds insuffisants
Layer 2 : #confirm  — confirmation paiement, lecture NFC
```

Flux de paiement typique :

```
[Articles] → clic VALIDER → trigger "validerPaiement"
    ↓
hx-post /paiement/moyens_paiement/ → swap #messages (layer 1)
    ↓
clic ESPECE → hx-get /paiement/confirmer/?method=espece → swap #confirm (layer 2)
    ↓
clic VALIDER → JS postUrl → hx-post /paiement/payer/ → swap #messages (layer 1)
    ↓
Paiement réussi → bouton RETOUR → manageReset() → retour layer 0
```

Pour le cashless (NFC) :

```
clic CASHLESS → hx-get /paiement/lire_nfc/ → swap #confirm (layer 2)
    ↓
Composant <c-read-nfc> démarre NfcReader
    ↓
Lecture carte → JS injecte tag_id dans le formulaire addition
    ↓
Submit → hx-post /paiement/payer/ avec moyen_paiement=nfc + tag_id
    ↓
Si fonds insuffisants → partial hx_funds_insufficient (paiement fractionné)
```

### Communication JS ↔ HTMX

Les templates utilisent un pattern "event organizer" pour piloter les formulaires HTMX depuis le JS :

```javascript
// Envoyer une commande au formulaire addition
sendEvent('organizerMsg', '#event-organizer', {
    msg: 'additionManageForm',
    data: { actionType: 'updateInput', selector: '#addition-moyen-paiement', value: 'espece' }
})

// actionType peut être :
// - 'updateInput' : met à jour un champ caché du formulaire
// - 'postUrl'     : change l'URL hx-post du formulaire
// - 'submit'      : soumet le formulaire
```

### Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DEMO` | `0` | Active le mode démo (simulation NFC) |
| `DEMO_TAGID_CM` | `A49E8E2A` | Tag ID carte primaire mock |
| `DEMO_TAGID_CLIENT1` | `B52F9F3B` | Tag ID client 1 mock |
| `DEMO_TAGID_CLIENT2` | `C63A0A4C` | Tag ID client 2 mock |
| `DEMO_TAGID_CLIENT3` | `D74B1B5D` | Tag ID client 3 mock |

### django-cotton

Les composants réutilisables sont dans `templates/cotton/`. Syntaxe :

```html
<!-- Utilisation -->
<c-header :title="title" />
<c-bt.paiement name="ESPECE" icon="fa-coins" hx-get="/paiement/confirmer/" />
<c-read-nfc id="confirm" event-manage-form="additionManageForm" submit-url="/paiement/payer/" />

<!-- Le composant reçoit les attributs via {{ attrs }} et le contenu via {{ slot }} -->
```

Configuration requise dans `settings.py` :
- `APP_DIRS: False` + loaders explicites (`cotton_loader`, `filesystem`, `app_directories`)
- `builtins: ['django_cotton.templatetags.cotton']`
- `django_cotton` dans `SHARED_APPS`

---

## Fichiers modifiés hors de laboutik/

| Fichier | Modification |
|---------|-------------|
| `pyproject.toml` | Ajout `django-cotton = "^2.6.1"` |
| `TiBillet/settings.py` | `django_cotton` SHARED_APPS, `laboutik` TENANT_APPS, TEMPLATES loaders, variables DEMO_* |
| `TiBillet/urls_tenants.py` | `path('laboutik/', include('laboutik.urls'))` |
| `BaseBillet/permissions.py` | Fix `HasLaBoutikApi` (key=None), ajout `HasLaBoutikAccess` (API key OU admin tenant) |

---

## Ce qui reste à faire

### Priorité haute — Modèles Django

Remplacer les données mock par de vrais modèles. Tout est dans `utils/mockData.py`.

**Modèles à créer dans `laboutik/models.py` :**

| Modèle | Remplace | Champs principaux |
|--------|----------|-------------------|
| `PointDeVente` | `mockData.pvs` | uuid, name, icon, comportement (A/K/C), service_direct, accepte_especes, accepte_carte_bancaire, accepte_cheque, afficher_les_prix, accepte_commandes, poid_liste |
| `CategorieArticle` | categories dans pvs | uuid, name, icon, couleur_texte, couleur_fond, poid_liste, FK → PointDeVente |
| `Article` | articles dans pvs | uuid, name, prix (centimes), methode_name, couleur_texte, couleur_fond, icon, poid_liste, FK → CategorieArticle, FK → PointDeVente, bt_groupement (JSONField ou FK) |
| `Table` | `mockData.tables` | id, name, statut (L/S/O), FK → PointDeVente |
| `CarteCashless` | `mockData.cards` | tag_id, type_card (primary/client), name, email, wallets (Decimal), wallets_gift (Decimal), mode_gerant, memberships (JSONField), ManyToMany → PointDeVente (pvs_list) |
| `Transaction` | table "transactions" dans mockDb | uuid, payment data (JSONField), total, missing, moyen_paiement, timestamps |
| `GroupementBouton` | `mockData.bt_groupement` | methode_name, moyens_paiement, besoin_tag_id, groupe, nb_commande_max |

**Points d'attention :**
- Les prix sont stockés en **centimes** dans le mock (int). Utiliser `DecimalField` ou garder en centimes.
- `CarteCashless` pourrait être un proxy vers le modèle Fedow existant (wallets fédérés).
- `PointDeVente` et `Article` pourraient être liés aux `Product` de BaseBillet.
- Penser à la relation avec le modèle `Configuration` de BaseBillet (monnaie_name, lieu, etc.).

### Priorité haute — Supprimer le state mutable

La fonction `_construire_state()` dans views.py construit le state à chaque requête (corrigé par rapport au global mutable original). Mais les données dedans sont en dur ("lieu de test", "lémien"). A remplacer par :

```python
# Exemple futur
def _construire_state(request):
    config = Configuration.get_solo()
    return {
        "version": config.version,
        "place": {"name": config.organisation, "monnaie_name": config.monnaie_name},
        # ...
    }
```

### Priorité moyenne — Kiosque

Le template `kiosk.html` est un placeholder (`<h1>Kiosk</h1>`). A implémenter pour le mode libre-service.

### Priorité moyenne — Mode restaurant (tables + commandes)

Le mode tables fonctionne visuellement mais :
- Les statuts de table (L/S/O) ne sont pas mis à jour.
- Pas de persistence des commandes par table.
- Pas de vue "préparations" (cuisine).

### Priorité basse — Migration FontAwesome → Bootstrap Icons

L'interface utilise FontAwesome 5 (`all_fontawesome-free-5-11-2.css`). Le reste de Lespass utilise Bootstrap Icons. Migration à planifier (chercher `fa-` dans les templates et le JS).

### Priorité basse — HTMX embarqué

L'app embarque sa propre copie de HTMX (`static/js/htmx@2.0.6.min.js`). Le reste de Lespass utilise aussi HTMX via `django-htmx`. A terme, utiliser une seule version partagée.

### Priorité basse — Cordova

Le `base.html` charge `<script src="http://localhost/cordova.js"></script>` pour la compatibilité avec les apps mobiles Cordova. A conditionner ou supprimer si non utilisé.

### Priorité basse — Socket.IO

`socket.io.3.0.4.js` est chargé mais pas utilisé activement. Prévu pour la communication temps réel (préparations cuisine, synchronisation caisses).

### Priorité basse — Tests

Le plan prévoyait un test Playwright `31-laboutik-basic-flow.spec.ts` :
1. Créer un PairingDevice via l'admin
2. Claim le PIN → récupérer l'API key
3. GET `/laboutik/caisse/` avec API key → vérifier 200
4. GET sans auth → vérifier 403
5. Naviguer vers le PV mock → vérifier que l'interface se charge

### Nettoyage

- `laboutik/utils/dbJson.py` : version standalone du mock, quasi-identique à `mockData.py`. A supprimer quand les vrais modèles seront en place.
- `laboutik/views/login_hardware.html` : template de l'ancien login hardware (remplacé par Discovery). A supprimer.
- `laboutik/static/js/login_hardware.js` : idem.

---

## Commandes utiles

```bash
# Accéder à la caisse (navigateur, admin connecté)
https://lespass.tibillet.localhost/laboutik/caisse/

# Accéder via API key
curl -H "Authorization: Api-Key <key>" https://lespass.tibillet.localhost/laboutik/caisse/

# Créer une clé API manuellement (shell Django)
from django.db import connection
connection.set_schema('lespass')
from BaseBillet.models import LaBoutikAPIKey
api_key, key = LaBoutikAPIKey.objects.create_key(name='test')
print(key)

# Ou via Discovery (flux normal)
# 1. Admin crée PairingDevice dans l'admin Unfold → obtient un PIN
# 2. POST /api/discovery/claim/ {"pin_code": "123456"}
# 3. Réponse : {"api_key": "xxx", "server_url": "https://...", "device_name": "..."}
```
