# Discovery — Appairage de terminaux par code PIN

App Django pour l'appairage de terminaux LaBoutik avec un tenant Lespass via un code PIN à 6 chiffres.

## Principe

```
┌──────────────────┐        ┌──────────────────────────────┐
│  Admin tenant    │        │  Terminal LaBoutik            │
│  (navigateur)    │        │  (application front)          │
└────────┬─────────┘        └──────────────┬───────────────┘
         │                                 │
    1. Crée un PairingDevice          3. Saisit le PIN
       dans l'admin Unfold               affiché par l'admin
         │                                 │
         ▼                                 ▼
┌──────────────────────────────────────────────────────────┐
│                     Lespass (Django)                      │
│                                                          │
│  2. Génère un PIN 6 chiffres (ex: 586 573)               │
│                                                          │
│  4. POST /api/discovery/claim/ { "pin_code": "586573" }  │
│     → Vérifie le PIN                                     │
│     → Crée une clé API LaBoutikAPIKey dans le tenant     │
│     → Vide le PIN (usage unique)                         │
│     → Retourne : server_url, api_key, device_name        │
└──────────────────────────────────────────────────────────┘
```

**Le PIN est à usage unique.** Une fois consommé, il est vidé de la base. Il ne sert qu'à établir le lien initial entre le terminal et son tenant.

## Architecture

| Fichier | Rôle |
|---------|------|
| `models.py` | `PairingDevice` — device en attente d'appairage, avec PIN unique |
| `serializers.py` | `PinClaimSerializer` — validation du PIN (6 chiffres, existant, non consommé) |
| `views.py` | `ClaimPinView` — route publique POST, crée la clé API, retourne les credentials |
| `urls.py` | Route unique : `claim/` |

**Schéma multi-tenant** : l'app `discovery` est dans `SHARED_APPS` (schéma public) parce que le terminal ne connaît pas encore son tenant au moment du claim. Le modèle `PairingDevice` a une FK vers `Customers.Client` (aussi public). La clé API `LaBoutikAPIKey` est créée dans le schéma du tenant via `tenant_context()`.

## Endpoint

### `POST /api/discovery/claim/`

Route publique (pas d'authentification requise). Domaine racine uniquement (pas le sous-domaine tenant).

**Throttling** : 10 requêtes/minute par IP (protection brute-force).

#### Requête

```json
{
  "pin_code": "586573"
}
```

Le `pin_code` est une string de 6 chiffres exactement.

#### Réponse succès — `200 OK`

```json
{
  "server_url": "https://lespass.tibillet.localhost",
  "api_key": "aBcDeFgH.xYzAbCdEfGhIjKlMnOpQrStUvWxYz1234",
  "device_name": "Caisse 1"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `server_url` | string | URL complète du tenant (avec `https://`). C'est la base pour tous les appels API suivants. |
| `api_key` | string | Clé API `LaBoutikAPIKey`. À envoyer dans le header `Authorization: Api-Key <api_key>` pour les appels authentifiés. |
| `device_name` | string | Nom du device tel que défini par l'admin. |

#### Réponses erreur — `400 Bad Request`

PIN invalide, déjà utilisé, ou mal formaté :

```json
{
  "pin_code": ["Invalid or already used PIN code."]
}
```

Format incorrect (pas 6 chiffres) :

```json
{
  "pin_code": ["PIN must contain only digits."]
}
```

#### Réponse erreur — `429 Too Many Requests`

Throttle dépassé (plus de 10 requêtes/minute depuis la même IP).

## Côté front : comment se brancher

### 1. Écran de saisie du PIN

L'application front affiche un écran avec un champ de saisie numérique à 6 chiffres. L'admin du lieu communique le PIN au terminal (affichage sur son écran, lecture orale, etc.).

### 2. Appel claim

```javascript
const response = await fetch('https://tibillet.localhost/api/discovery/claim/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ pin_code: '586573' }),
});

if (response.ok) {
  const { server_url, api_key, device_name } = await response.json();
  // Stocker server_url et api_key de façon persistante
  // (localStorage, fichier de config, etc.)
} else if (response.status === 400) {
  const errors = await response.json();
  // Afficher l'erreur à l'utilisateur
} else if (response.status === 429) {
  // Trop de tentatives, attendre avant de réessayer
}
```

### 3. Stocker les credentials

Après un claim réussi, le front doit persister :
- **`server_url`** — base URL pour tous les appels API du tenant
- **`api_key`** — clé d'authentification LaBoutik

Ces deux valeurs sont permanentes. Le PIN n'est plus nécessaire.

### 4. Appels API authentifiés

Pour tous les appels suivants vers le tenant, utiliser le header :

```
Authorization: Api-Key aBcDeFgH.xYzAbCdEfGhIjKlMnOpQrStUvWxYz1234
```

Exemple :

```javascript
const response = await fetch(`${server_url}/api/v2/some-endpoint/`, {
  headers: {
    'Authorization': `Api-Key ${api_key}`,
    'Content-Type': 'application/json',
  },
});
```

### 5. Gestion de la perte de credentials

Si le terminal perd sa clé API (reset, réinstallation), l'admin doit créer un nouveau `PairingDevice` depuis l'admin Unfold. L'ancien device reste en base (marqué "claimed") mais sa clé API reste valide dans le tenant.

## Type de clé API

La clé retournée est une `LaBoutikAPIKey` (pas une `ScannerAPIKey`). C'est un type distinct, prévu pour recevoir des permissions spécifiques aux terminaux de caisse dans le futur. La permission DRF correspondante est `HasLaBoutikApi` dans `BaseBillet/permissions.py`.

## Test Playwright

```bash
cd tests/playwright
yarn playwright test --project=chromium --workers=1 tests/30-discovery-pin-pairing.spec.ts
```

Ce test vérifie le flux complet : création admin → lecture PIN → claim API → re-claim rejeté → PIN invalide rejeté.
