# LaBoutik — Caisse enregistreuse tactile

Application de caisse enregistreuse (POS) pour terminaux tactiles, integree dans l'ecosysteme TiBillet/Lespass.

Interface full-screen pensee pour tablettes et ecrans tactiles, avec lecture NFC pour les cartes cashless.

## Statut actuel

**Backend ORM complet.** Les donnees (articles, points de vente, cartes, paiements) viennent de la base PostgreSQL via les modeles Django. Les fichiers mock dans `utils/` sont encore presents mais ne sont plus utilises par les vues principales.

**Phases terminees :** modeles POS, paiements especes/CB/NFC, recharges, commandes restaurant, cloture caisse, POS Adhesion multi-tarif.

## Architecture

### Stack technique

| Couche | Techno |
|--------|--------|
| Backend | Django 4.2 + DRF ViewSets (pattern FALC) |
| Frontend | HTMX 2.0.6 + django-cotton (composants `<c-xxx>`) |
| CSS | CSS custom properties (palette, sizes) — pas de framework CSS |
| JS | Vanilla JS, pas de bundler. Event bus custom (`tibilletUtils.js`) |
| Icones | FontAwesome 5 |
| NFC | Web NFC API + simulation en mode demo |

### Modeles

| Modele | App | Role |
|--------|-----|------|
| `PointDeVente` | laboutik | Point de vente physique ou virtuel |
| `CartePrimaire` | laboutik | Carte NFC du caissier (acces aux PV) |
| `Table` + `CategorieTable` | laboutik | Tables restaurant (mode commande) |
| `CommandeSauvegarde` + `ArticleCommandeSauvegarde` | laboutik | Commandes restaurant persistees |
| `ClotureCaisse` | laboutik | Rapport de cloture (totaux, JSON detail) |
| `Product` | BaseBillet | Catalogue produits (unifie POS + billetterie + adhesion) |
| `Price` | BaseBillet | Tarifs (EUR ou tokens, prix libre, abonnement) |
| `CategorieProduct` | BaseBillet | Categories produits (couleurs, icones POS) |
| `Membership` | BaseBillet | Fiches adherent (deadline, statut, contribution) |

### Types de points de vente

Le champ `PointDeVente.comportement` determine le mode d'interface (pas le contenu) :

| Type | Code | Comportement |
|------|------|-------------|
| **Direct** | `D` | Vente au comptoir classique (grille + panier + footer) |
| **Avance** | `V` | Mode commande restaurant (tables, preparations) — reserve, pas code |

Le **quoi** (ventes, adhesions, billets, recharges) est determine par les articles
dans le M2M `products` du PV. Un PV peut contenir tous les types d'articles.

> **Historique** : les anciens types ADHESION ('A'), CASHLESS ('C') et KIOSK ('K')
> ont ete supprimes. La logique est pilotee par l'article (`methode_caisse`), pas le PV.
> KIOSK sera une app Django separee dans le futur.

---

## Adhesions au POS — multi-tarif et prix libre

### Principe

Les produits adhesion existent deja dans `BaseBillet.Product` (avec `categorie_article=ADHESION`).
Ils ont des tarifs (`Price`) avec duree d'abonnement, prix libre, etc.

Le POS de type ADHESION les affiche tels quels. Pas de duplication de produits.
Pas de `methode_caisse` necessaire — c'est le type du PV qui determine le contenu.

### Donnees de test

La commande `create_test_pos_data` cree :

- **Adhesion annuelle** : 3 tarifs (Plein tarif 15 EUR, Tarif reduit 8 EUR, Prix libre min 5 EUR)
- **Adhesion mensuelle** : 1 tarif (Tarif unique 5 EUR)
- **PV "Adhesions"** : type `ADHESION`, accepte especes et CB

### Multi-tarif : overlay de selection

Quand un produit a **plusieurs tarifs** ou un **prix libre**, le clic sur l'article
ouvre un overlay plein ecran au lieu d'ajouter directement au panier.

```
┌──────────────────────────────────────────┐
│         Adhesion annuelle                │
│         Choisir un tarif                 │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Plein tarif                      │  │
│  │  15,00 EUR                        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Tarif reduit                     │  │
│  │  8,00 EUR                         │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Prix libre (min 5,00 EUR)        │  │
│  │  ┌──────────┐  EUR  [OK]          │  │
│  │  │  ______  │                     │  │
│  │  └──────────┘                     │  │
│  └────────────────────────────────────┘  │
│                                          │
│            [ <- RETOUR ]                 │
└──────────────────────────────────────────┘
```

**Comportement :**

- **Tarif fixe** : un clic ajoute l'article au panier avec ce prix et ferme l'overlay.
- **Prix libre** : un champ input apparait. Le caissier entre le montant. Le bouton OK valide que le montant est >= au minimum. Puis l'article est ajoute au panier avec le montant saisi.
- **Produit avec 1 seul tarif fixe** : pas d'overlay. Ajout direct au panier (meme comportement qu'un article de vente classique).

### Format du panier (formulaire HTML)

Le panier est un formulaire HTML cache (`#addition-form`). Chaque article ajoute des inputs :

**Articles classiques (mono-tarif) :**
```html
<input type="number" name="repid-<product_uuid>" value="2" />
```

**Articles multi-tarif (adhesion avec tarif choisi) :**
```html
<!-- Le separateur '--' distingue le product_uuid du price_uuid -->
<input type="number" name="repid-<product_uuid>--<price_uuid>" value="1" />
```

**Articles prix libre (montant custom) :**
```html
<input type="number" name="repid-<product_uuid>--<price_uuid>" value="1" />
<!-- Montant en centimes choisi par le caissier -->
<input type="hidden" name="custom-<product_uuid>--<price_uuid>" value="2500" />
```

Le backend (`PanierSerializer.extraire_articles_du_post()`) parse les deux formats :
- `repid-<uuid>` → ancien format, `price_uuid=None`, premier prix EUR
- `repid-<uuid>--<price_uuid>` → nouveau format, charge le `Price` specifique
- `custom-<uuid>--<price_uuid>` → montant libre en centimes

### Identification client pour les adhesions

Quand le panier contient des adhesions, l'ecran de paiement affiche deux options :

```
┌──────────────────────────────────────────┐
│     Adhesion — Identifier le client      │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  SCANNER CARTE NFC                │  │
│  └────────────────────────────────────┘  │
│                                          │
│  — ou —                                  │
│                                          │
│  Email :    [___________________]        │
│  Prenom :   [___________]                │
│  Nom :      [___________]                │
│                                          │
│  [ ESPECE ]  [ CB ]  [ CHEQUE ]          │
└──────────────────────────────────────────┘
```

**Option 1 — Scan NFC** : identifie le client via `CarteCashless.user`. Meme flux que les recharges.

**Option 2 — Formulaire email** : le caissier saisit l'email du client (obligatoire) et
son nom/prenom (optionnel). Le backend appelle `get_or_create_user(email)` pour creer
ou retrouver le `TibilletUser`. Puis `_creer_ou_renouveler_adhesion()` cree ou renouvelle
la `Membership` avec le `Price` choisi et le montant paye.

**Si aucune identification** : les `LigneArticle` sont creees (comptabilite), mais pas de `Membership`.
L'adhesion pourra etre rattachee plus tard.

### Flux technique complet (adhesion CB avec email)

```
1. Caissier ouvre le PV "Adhesions"
   → _construire_donnees_articles() charge dynamiquement les Product(categorie_article=ADHESION)
   → Inclut tous les Price EUR dans les data-attributes de chaque tuile

2. Clic sur "Adhesion annuelle" (3 tarifs)
   → articles.js:manageKey() detecte data-multi-tarif="true"
   → Emet 'tarifSelection' au lieu d'appeler addArticle()

3. tibilletUtils.js route vers tarif.js:tarifSelection()
   → Genere l'overlay HTML dans #messages (cote client, pas d'aller-retour serveur)

4. Clic sur "Plein tarif — 15,00 EUR"
   → tarif.js:tarifSelectFixed() ferme l'overlay
   → Appelle addArticleWithPrice(productUuid, priceUuid, 1500, ...)
   → Emet 'articlesAdd' avec priceUuid et prixCentimes

5. addition.js:additionInsertArticle() recoit l'evenement
   → Cree input "repid-<product_uuid>--<price_uuid>" value="1"
   → Affiche la ligne dans le panier avec le nom "Adhesion annuelle (Plein tarif)"

6. Clic VALIDER
   → POST /paiement/moyens_paiement/
   → moyens_paiement() detecte panier_a_adhesions=True
   → Retourne hx_display_type_payment.html en mode adhesion (scan NFC + formulaire email)

7. Caissier saisit email + nom + prenom, clique CB
   → adhesionCopyFieldsToForm() copie les champs dans #addition-form (inputs caches)
   → hx-get /paiement/confirmer/?method=carte_bancaire

8. Clic VALIDER sur la confirmation
   → POST /paiement/payer/ avec les inputs repid-*, custom-*, email_adhesion, etc.
   → _payer_par_carte_ou_cheque() :
     a. _creer_lignes_articles() → ProductSold + PriceSold + LigneArticle
     b. _creer_adhesions_depuis_panier() :
        - Lit email_adhesion → get_or_create_user(email)
        - _creer_ou_renouveler_adhesion(user, product, price, contribution_value)
        - Membership creee avec status=LABOUTIK, deadline calculee

9. Ecran succes → RETOUR → interface POS
```

### Flux prix libre (variante de l'etape 4)

```
4b. Clic sur "Prix libre (min 5,00 EUR)"
    → L'overlay affiche un input numerique + bouton OK
    → Caissier saisit "25" (= 25 EUR)
    → tarif.js:tarifValidateFreePrix() verifie 25 >= 5
    → Appelle addArticleWithPrice(..., customAmount=2500)
    → addition.js cree DEUX inputs :
      - "repid-<product>--<price>" value="1"
      - "custom-<product>--<price>" value="2500"
    → Le total du panier utilise 2500 centimes (pas le prix de base)

Au paiement :
    → _extraire_articles_du_panier() lit custom-* → prix_centimes=2500
    → PriceSold cree avec prix=25.00 EUR
    → Membership.contribution_value = 25.00
```

---

## Flux HTMX — layers superposes

L'interface fonctionne en layers superposes :

```
Layer 0 : Interface principale (articles, categories, addition)
Layer 1 : #messages — types de paiement, verification carte, selection tarif
Layer 2 : #confirm  — confirmation paiement, lecture NFC
```

### Flux de paiement standard (especes)

```
[Articles] → clic VALIDER → trigger "validerPaiement"
    ↓
hx-post /paiement/moyens_paiement/ → swap #messages (layer 1)
    ↓
clic ESPECE → hx-get /paiement/confirmer/?method=espece → swap #confirm (layer 2)
    ↓
clic VALIDER → JS postUrl → hx-post /paiement/payer/ → swap #messages (layer 1)
    ↓
Paiement reussi → bouton RETOUR → manageReset() → retour layer 0
```

### Flux cashless (NFC)

```
clic CASHLESS → hx-get /paiement/lire_nfc/ → swap #confirm (layer 2)
    ↓
Composant <c-read-nfc> demarre NfcReader
    ↓
Lecture carte → JS injecte tag_id dans le formulaire addition
    ↓
Submit → hx-post /paiement/payer/ avec moyen_paiement=nfc + tag_id
    ↓
Si fonds insuffisants → partial hx_funds_insufficient (paiement fractionne)
```

---

## Communication JS — Event Bus

Les fichiers JS communiquent via un systeme d'evenements personnalises
route par `tibilletUtils.js`.

### Table de routage (`switches`)

```javascript
const switches = {
    articlesAdd:               → additionInsertArticle sur #addition
    additionTotalChange:       → updateBtValider sur #bt-valider
    additionRemoveArticle:     → articlesRemove sur #products
    resetArticles:             → additionReset + articlesReset
    articlesDisplayCategory:   → articlesDisplayCategory sur #products
    additionDisplayPaymentTypes: → additionDisplayPaymentTypes sur #addition
    additionManageForm:        → additionManageForm sur #addition
    tarifSelection:            → tarifSelection sur #messages
}
```

### Flux d'un evenement

```
1. articles.js:addArticle() envoie { msg: 'articlesAdd', data: { uuid, price... } }
2. eventsOrganizer() recoit et consulte switches['articlesAdd']
3. sendEvent('additionInsertArticle', '#addition', data)
4. addition.js:additionInsertArticle() est execute
```

### Fichiers JS

| Fichier | Role |
|---------|------|
| `tibilletUtils.js` | Event bus central (sendEvent, switches, eventsOrganizer) |
| `articles.js` | Grille d'articles (clic, quantite, groupes, categories) |
| `addition.js` | Panier (ajout, suppression, total, formulaire HTMX) |
| `tarif.js` | Overlay selection tarif + prix libre (multi-tarif adhesion) |
| `nfc.js` | Classe NfcReader (Web NFC + simulation demo) |

---

## Arborescence des fichiers

```
laboutik/
├── models.py                        # 6 modeles POS (PointDeVente, CartePrimaire, Table, etc.)
├── views.py                         # 3 ViewSets DRF (Caisse, Paiement, Commande)
├── serializers.py                   # 7 serializers DRF (validation POST, extraction panier)
├── urls.py                          # DRF router
├── tasks.py                         # Tache Celery (envoi rapport cloture par email)
├── pdf.py                           # Generation PDF cloture (WeasyPrint)
├── csv_export.py                    # Generation CSV cloture
├── management/commands/
│   └── create_test_pos_data.py      # Donnees de test (categories, produits, PV, cartes)
├── templates/
│   ├── cotton/                      # Composants django-cotton (reutilisables)
│   │   ├── articles.html            # Grille d'articles + styles + chargement JS
│   │   ├── addition.html            # Panier + formulaire HTMX cache
│   │   ├── categories.html          # Barre laterale categories
│   │   ├── header.html              # Header avec menu burger
│   │   └── bt/paiement.html         # Bouton moyen de paiement
│   └── laboutik/
│       ├── base.html                # Layout HTML (HTMX, FontAwesome, NFC, state JSON)
│       ├── views/
│       │   ├── common_user_interface.html  # Interface POS principale
│       │   └── tables.html                # Selection de table
│       └── partial/                 # Fragments HTMX
│           ├── hx_display_type_payment.html  # Choix paiement (normal/recharge/adhesion)
│           ├── hx_confirm_payment.html       # Confirmation paiement
│           └── hx_return_payment_success.html # Succes
├── static/js/
│   ├── tibilletUtils.js             # Event bus central
│   ├── articles.js                  # Grille articles (clic, groupes)
│   ├── addition.js                  # Panier (ajout, suppression, total)
│   ├── tarif.js                     # Overlay selection tarif + prix libre
│   └── nfc.js                       # Lecture NFC
└── doc/
    ├── PLAN_INTEGRATION.md          # Plan de fusion mono-repo (toutes les phases)
    └── UX/PLAN_UX_LABOUTIK.md       # Plan UX (5 sessions, toutes terminees)
```

---

## Authentification des terminaux (hardware auth)

LaBoutik tourne sur du hardware (PC de caisse, tablette Android, Raspberry Pi kiosque). Chaque terminal doit prouver son identite au serveur Lespass pour acceder a l'API de caisse.

L'authentification se fait en **deux etapes** :

1. **Appairage initial** (une seule fois par appareil) : un code PIN a 6 chiffres echange contre une cle API permanente.
2. **Login runtime** (a chaque lancement) : la cle API est echangee contre un cookie de session Django valable 12h.

Les requetes metier suivantes (POS, paiement, commandes) passent uniquement par le cookie de session. La cle API ne circule qu'au moment du login, jamais sur les appels courants.

### Modele conceptuel

```
┌──────────────────┐                              ┌────────────────────────┐
│  Admin Lespass   │  1. Cree PairingDevice       │   Base PostgreSQL      │
│  (navigateur)    ├─────────────────────────────▶│                        │
│                  │     (role=LB, PIN=586573)    │   PairingDevice        │
└──────────────────┘                              │                        │
                                                  └────────────────────────┘
                                                          ▲
┌──────────────────┐                                      │
│  Terminal        │  2. POST /api/discovery/claim/       │
│  (Pi, Android,   ├──────────────────────────────────────┤
│   PC, etc.)      │     {"pin_code": 586573}             │
│                  │                                       │
│                  │  3. Reponse :                         │
│                  │◀──────────────────────────────────────┤
│                  │     {server_url, api_key, ...}        │
│                  │                                       │
│                  │  4. Stocke api_key localement         │
│                  │     (.env / localStorage / fichier)   │
│                  │                                       │
│                  │  5. POST /laboutik/auth/bridge/       │
│                  │     Header: Authorization: Api-Key x  │
│                  ├──────────────────────────────────────▶│
│                  │                                       │
│                  │  6. Reponse 204 + Set-Cookie sessionid│
│                  │◀──────────────────────────────────────┤
│                  │                                       │
│                  │  7. Toutes les requetes suivantes     │
│                  │     via cookie (pas de header)        │
│                  ├──────────────────────────────────────▶│
└──────────────────┘                              ┌────────────────────────┐
                                                  │  /laboutik/caisse/     │
                                                  │  /laboutik/paiement/   │
                                                  │  /laboutik/commande/   │
                                                  └────────────────────────┘
```

### Flow complet cote serveur

| Etape | Endpoint | Entree | Sortie |
|-------|----------|--------|--------|
| 1. Appairage | `POST /api/discovery/claim/` | `{"pin_code": 586573}` (body JSON) | `{server_url, api_key, device_name}` |
| 2. Login | `POST /laboutik/auth/bridge/` | `Authorization: Api-Key <key>` (header) | `204 No Content` + `Set-Cookie: sessionid=...` |
| 3. API metier | `GET /laboutik/caisse/` etc. | `Cookie: sessionid=...` (auto) | HTML/JSON de la caisse |

Cote base de donnees, l'appairage cree automatiquement :

- Un **`TermUser`** (`TibilletUser` proxy, `espece=TE`, `terminal_role=LB/TI/KI`) avec un email synthetique `<pairing_uuid>@terminals.local`
- Une **`LaBoutikAPIKey`** liee au TermUser via `OneToOneField`

La cle API est hashee en base (SHA256). Seule la version non-hashee retournee au moment du claim peut etre utilisee — impossible de la recuperer plus tard.

### Codes de reponse du bridge

| Code | Condition |
|------|-----------|
| `204 No Content` | Cle valide, user actif, cookie pose. Succes. |
| `400 Bad Request` | Cle API V1 legacy (sans `user` lie) — re-pairing necessaire |
| `401 Unauthorized` | Header absent, cle invalide, ou `user.is_active=False` (revoque) |
| `429 Too Many Requests` | Throttle 10/min par IP depasse |

Les 401 ont un body vide (pas de fuite d'info pour un attaquant qui tenterait de distinguer cle inconnue / cle revoquee). Seul le 400 a un message explicite (la cle legacy n'est pas une donnee sensible).

### Revocation

Revoquer un terminal se fait via l'admin Unfold (`Terminals > bulk action "Revoke selected terminals"`), ce qui passe `is_active=False` sur le `TermUser`. A la prochaine requete, le middleware d'auth Django voit le flag et anonymise la session — acces refuse instantanement, aucune gymnastique de cache ou d'index inversé.

Pour re-autoriser le terminal, il faut generer un **nouveau** `PairingDevice` cote admin et re-faire l'appairage (`/api/discovery/claim/`). Il n'y a pas de mecanisme de "re-activation" de l'ancien user — c'est volontaire : on garde une trace dans la base du terminal revoque.

### Coexistence V1 / V2

| Version | Permission | Utilise |
|---------|------------|---------|
| V1 | `HasLaBoutikAccess` | Header `Authorization: Api-Key` OU session admin tenant |
| V2 | `HasLaBoutikTerminalAccess` | Session TermUser (bridge) + fallback V1 |

Toutes les routes de l'app `laboutik` utilisent desormais `HasLaBoutikTerminalAccess` (V2) :

- `CaisseViewSet`, `PaiementViewSet`, `CommandeViewSet`, `ArticlePanelViewSet` — session TermUser acceptee directement (chemin V2) ou fallback V1 (header Api-Key ou admin session humain).

Les routes V1 d'autres apps (ex: `ApiBillet`) qui utilisent encore `HasLaBoutikAccess` directement continuent d'accepter le header `Authorization: Api-Key` et la session admin humain, mais PAS les sessions TermUser (c'est voulu : `HasLaBoutikAccess` ne passe pas `is_tenant_admin()` pour un TermUser).

---

## Tuto 1 — Client Python / Raspberry Pi

Script minimal pour un terminal Python (Pi, serveur de caisse legacy, bot de test).

### Pre-requis

```bash
pip install requests
```

### Etape 1 — Appairage (une seule fois par machine)

```python
# pair_device.py
# Execute une seule fois pour appairer le terminal au serveur Lespass
# Stocke la cle API dans un fichier .env local

import json
import os
import sys
from pathlib import Path

import requests

SERVER_URL = "https://lespass.tibillet.localhost"
ENV_FILE = Path(__file__).parent / ".env.json"


def claim_pin(pin_code: str) -> dict:
    """Echange un PIN contre une cle API permanente."""
    response = requests.post(
        f"{SERVER_URL}/api/discovery/claim/",
        json={"pin_code": int(pin_code)},
        timeout=10,
        verify=True,  # HTTPS obligatoire en prod
    )
    response.raise_for_status()
    return response.json()


def main():
    if ENV_FILE.exists():
        print(f"[!] {ENV_FILE} existe deja. Supprimez-le pour re-appairer.")
        sys.exit(1)

    pin = input("PIN (6 chiffres, genere par l'admin) : ").strip()
    if not pin.isdigit() or len(pin) != 6:
        print("[!] PIN invalide (attendu : 6 chiffres)")
        sys.exit(1)

    try:
        data = claim_pin(pin)
    except requests.HTTPError as err:
        print(f"[!] Claim refuse : {err.response.status_code} {err.response.text}")
        sys.exit(1)

    # Sauvegarde locale. Attention : la cle API donne acces au tenant,
    # proteger le fichier (mode 600) ou le stocker dans un keyring.
    ENV_FILE.write_text(json.dumps(data, indent=2))
    ENV_FILE.chmod(0o600)

    print(f"[OK] Appairage reussi. Infos sauvees dans {ENV_FILE}")
    print(f"     device_name: {data['device_name']}")
    print(f"     server_url:  {data['server_url']}")


if __name__ == "__main__":
    main()
```

Usage :
```bash
$ python pair_device.py
PIN (6 chiffres, genere par l'admin) : 586573
[OK] Appairage reussi. Infos sauvees dans .env.json
     device_name: Caisse de test
     server_url:  https://lespass.tibillet.localhost
```

### Etape 2 — Client runtime (a chaque demarrage)

```python
# pos_client.py
# Client HTTP qui :
# 1. Lit la cle API depuis le fichier d'appairage
# 2. Echange la cle contre un cookie de session via le bridge
# 3. Utilise ensuite une session requests pour tous les appels metier

import json
from pathlib import Path

import requests

ENV_FILE = Path(__file__).parent / ".env.json"


class PosClient:
    def __init__(self):
        if not ENV_FILE.exists():
            raise RuntimeError(f"Pas d'appairage. Lancer pair_device.py d'abord.")
        data = json.loads(ENV_FILE.read_text())
        self.server_url = data["server_url"]
        self.api_key = data["api_key"]
        # Session requests : conserve automatiquement le cookie sessionid
        self.session = requests.Session()
        self.session.verify = True

    def login(self) -> None:
        """Echange la cle API contre un cookie de session (bridge)."""
        response = self.session.post(
            f"{self.server_url}/laboutik/auth/bridge/",
            headers={"Authorization": f"Api-Key {self.api_key}"},
            timeout=10,
        )
        if response.status_code == 204:
            print("[OK] Session ouverte (12h).")
            return
        if response.status_code == 401:
            raise RuntimeError("Cle API invalide ou terminal revoque. Re-appairer.")
        if response.status_code == 400:
            raise RuntimeError("Cle API legacy V1. Re-appairer via PIN.")
        response.raise_for_status()

    def caisse_home(self) -> str:
        """Recupere la page d'accueil de la caisse (retourne du HTML)."""
        response = self.session.get(
            f"{self.server_url}/laboutik/caisse/",
            timeout=10,
        )
        response.raise_for_status()
        return response.text

    # Ajouter ici d'autres methodes metier selon les besoins :
    # - valider un panier   → self.session.post("/laboutik/paiement/payer/", data=...)
    # - ouvrir une commande → self.session.post("/laboutik/commande/...", data=...)


def main():
    client = PosClient()
    client.login()
    html = client.caisse_home()
    print(f"[OK] Caisse chargee ({len(html)} octets de HTML)")


if __name__ == "__main__":
    main()
```

Usage :
```bash
$ python pos_client.py
[OK] Session ouverte (12h).
[OK] Caisse chargee (34521 octets de HTML)
```

### Gestion de l'expiration de session

La session dure 12h, refresh automatique a chaque requete (`SESSION_SAVE_EVERY_REQUEST=True`). Une caisse active ne se deconnecte jamais en cours de service. Si la session expire quand meme (caisse inactive 12h+), le serveur retourne un `401` ou un `403`. Le client doit :

1. Detecter le code d'erreur sur une requete metier
2. Re-appeler `self.login()` (le bridge) pour obtenir un nouveau cookie
3. Ré-essayer la requete metier

Wrapper suggere :

```python
def request_with_auto_relogin(self, method: str, url: str, **kwargs):
    """Wrapper qui re-auth automatiquement sur 401/403."""
    response = self.session.request(method, url, **kwargs)
    if response.status_code in (401, 403):
        self.login()
        response = self.session.request(method, url, **kwargs)
    return response
```

---

## Tuto 2 — Cordova / Android WebView

Pour une app Cordova qui encapsule l'interface POS dans une WebView native, le flow est legerement different : pas de `requests.Session()`, c'est le cookie jar du WebView qui gere la persistance. Le JavaScript initie le bridge puis la navigation classique prend le relais.

### Configuration

Dans `config.xml`, autoriser les cookies cross-origin et le domaine Lespass :

```xml
<allow-navigation href="https://lespass.tibillet.localhost/*" />
<access origin="https://lespass.tibillet.localhost" />
```

### Stockage de la configuration

Au premier lancement, l'app doit demander le PIN, appeler `/api/discovery/claim/`, puis stocker le resultat dans le systeme de fichiers natif (pas dans `localStorage` — un `localStorage` est partage avec tout code charge dans la WebView, y compris les pages distantes).

Exemple avec `cordova-plugin-file` :

```javascript
// pair.js — premier lancement uniquement
async function pairDevice(serverUrl, pinCode) {
  const response = await fetch(`${serverUrl}/api/discovery/claim/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin_code: parseInt(pinCode, 10) }),
  })

  if (!response.ok) {
    throw new Error(`Claim refuse : ${response.status}`)
  }

  const data = await response.json()
  // data = { server_url, api_key, device_name }

  // Ecriture dans le repertoire prive de l'app (cordova-plugin-file)
  await writeFile('config.json', JSON.stringify(data))
  return data
}
```

### Login au demarrage de l'app

```javascript
// app.js — execute a chaque deviceready ET a chaque resume
async function authenticate() {
  const config = JSON.parse(await readFile('config.json'))

  const response = await fetch(`${config.server_url}/laboutik/auth/bridge/`, {
    method: 'POST',
    headers: { 'Authorization': `Api-Key ${config.api_key}` },
    credentials: 'include',  // IMPORTANT : laisse le WebView poser Set-Cookie
  })

  if (response.status === 204) {
    // Le cookie sessionid est maintenant pose sur le WebView.
    // Toute navigation suivante vers lespass.tibillet.localhost l'enverra.
    return { ok: true }
  }
  if (response.status === 401) {
    // Cle invalide ou terminal revoque → afficher ecran de re-pairing
    return { ok: false, reason: 'revoked_or_invalid' }
  }
  if (response.status === 400) {
    // Cle V1 legacy → re-pairing necessaire
    return { ok: false, reason: 'legacy_key' }
  }
  throw new Error(`Auth bridge : ${response.status}`)
}

document.addEventListener('deviceready', async () => {
  const result = await authenticate()
  if (result.ok) {
    // Rediriger vers l'interface POS principale
    const config = JSON.parse(await readFile('config.json'))
    window.location.href = `${config.server_url}/laboutik/caisse/`
  } else {
    // Afficher ecran de re-pairing
    showPairingScreen(result.reason)
  }
})

// Cordova declenche 'resume' quand l'app revient au premier plan.
// On re-auth pour verifier que la session n'a pas expire pendant l'inactivite.
document.addEventListener('resume', async () => {
  const result = await authenticate()
  if (!result.ok) {
    showPairingScreen(result.reason)
  }
})
```

### Pourquoi `credentials: 'include'` est critique

Par defaut, `fetch()` en CORS ne pose PAS les cookies meme si le serveur envoie `Set-Cookie`. Sans cette option, le bridge retourne bien 204, mais le cookie est ignore et la navigation suivante vers `/laboutik/caisse/` echouera en 401. Bien verifier aussi que `withCredentials`/`credentials` soit actif sur les autres appels qui peuvent suivre.

### Wrapper fetch avec re-auth automatique

Pour les requetes AJAX internes a la page POS (si elle utilise HTMX ou des appels manuels), on peut wrapper `fetch` pour declencher automatiquement le re-bridge si la session expire :

```javascript
// fetch-wrapper.js
async function fetchWithAuth(url, options = {}) {
  const merged = { credentials: 'include', ...options }
  let response = await fetch(url, merged)

  if (response.status === 401 || response.status === 403) {
    // Tentative de re-auth
    const authResult = await authenticate()
    if (!authResult.ok) {
      showPairingScreen(authResult.reason)
      throw new Error('Auth expired, re-pairing required')
    }
    // Retry une seule fois
    response = await fetch(url, merged)
  }

  return response
}
```

### Bonnes pratiques mobile

- **HTTPS obligatoire** : Cordova ignore `Set-Cookie` sur HTTP en clair dans la plupart des WebViews recentes.
- **Pas d'`api_key` dans l'URL** : utiliser uniquement le header `Authorization`. L'URL apparait dans les logs nginx, l'historique WebView, et les tracebacks.
- **Nettoyer le DOM apres soumission** : si pour une raison quelconque un form HTML sert au bridge, faire `form.remove()` apres submit pour eviter un retour arriere qui exposerait la cle.
- **Conteneur natif** : preferer `cordova-plugin-file` au `localStorage` pour stocker l'`api_key`, et le repertoire prive de l'app (`cordova.file.dataDirectory`), pas le stockage partage.
- **Gerer offline** : si `authenticate()` echoue sur une `TypeError` reseau, afficher un ecran "Hors ligne" distinct du refus d'auth.

### Revoquer un terminal perdu ou vole

Cote admin, passer le `TermUser` correspondant en `is_active=False` depuis l'admin Unfold. Au prochain `deviceready` ou `resume`, l'app recevra un 401 et basculera sur l'ecran de re-pairing. Pour re-habiliter l'appareil (s'il est retrouve), il faut generer un nouveau PIN cote admin et re-faire l'appairage depuis l'app.

---

## Commandes utiles

```bash
# Acceder a la caisse (navigateur, admin connecte)
https://lespass.tibillet.localhost/laboutik/caisse/

# Creer les donnees de test POS
docker exec lespass_django poetry run python manage.py create_test_pos_data

# Lancer les tests POS
docker exec lespass_django poetry run pytest tests/pytest/test_pos_models.py -v

# Lancer tous les tests
docker exec lespass_django poetry run pytest tests/pytest/ -x --tb=short
```
