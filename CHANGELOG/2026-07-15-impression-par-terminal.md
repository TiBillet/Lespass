# Impression par terminal (et non plus par point de vente)

**Date :** 2026-07-15
**Migration :** Oui

Spec : [`TECH_DOC/SESSIONS/IMPRESSION/`](../TECH_DOC/SESSIONS/IMPRESSION/INDEX.md)

## Ce qui a été fait

L'imprimante du ticket client était portée par `PointDeVente.printer`. En festival, vingt tablettes
encaissent sur le même point de vente : elles s'abonnaient toutes au **même** canal WebSocket, et
chaque ticket **sortait vingt fois**.

L'imprimante est maintenant portée par un objet **`Terminal`** — qui existait déjà sous le nom
`kiosk.Terminal` (le TPE Stripe), et qui a été promu en `laboutik.Terminal`.

### Modifications

| Fichier | Changement |
|---|---|
| `laboutik/models.py` | `Terminal` + `StripeLocation` (déplacés depuis `kiosk`), `PointDeVente.printer` supprimé |
| `laboutik/views.py` | `imprimante_du_terminal(user)` — la règle unique. 7 sites d'impression + `state["printer"]` |
| `Administration/admin/laboutik.py` | `TerminalAdmin` + action « Révoquer », colonne « Terminaux » sur les imprimantes |
| `discovery/views.py` | Le claim crée le `Terminal` |

**Migration :** `laboutik/0002` + `kiosk/0005`. Déjà appliquée en dev.

## Tests à réaliser

### Test 1 — Le bug d'origine : deux terminaux, un seul point de vente

C'est **le** scénario à valider.

1. Admin → **Terminaux matériels → Imprimantes** → créer deux imprimantes (type « Mock (console) »
   suffit) : « Imprimante A » et « Imprimante B ».
2. Admin → **Terminaux matériels → Terminaux** → créer deux terminaux, type « Caisse LaBoutik » :
   « Caisse A » et « Caisse B ». **Leur code PIN s'affiche aussitôt dans la colonne « État ».**
3. Appairer les deux appareils (ou simuler le claim) :
   ```bash
   curl -sk -X POST "https://tibillet.localhost/api/discovery/claim/" \
     -H "Content-Type: application/json" -d '{"pin_code": "<le PIN>"}'
   ```
   ⚠️ Le claim se fait sur le **domaine public** (`tibillet.localhost`), pas sur le tenant :
   l'appareil ne connaît pas encore son lieu.

   **Attendu** : la colonne « État » passe de `123 456` à « ✓ Appairé ».
4. Éditer « Caisse A », lui assigner « Imprimante A ». Idem B → B.
5. Sur les deux caisses, **choisir le même point de vente**, puis encaisser une vente sur chacune.

**Attendu :** le ticket de A sort sur l'Imprimante A, celui de B sur l'Imprimante B. **Un seul
exemplaire chacun.** Avant ce chantier, les deux tickets sortaient sur les deux imprimantes.

Avec l'imprimante « Mock », les tickets s'affichent en ASCII dans la console Celery :
```bash
docker logs -f lespass_celery
```

### Test 2 — Une imprimante partagée par plusieurs terminaux

Assigner **la même** imprimante à « Caisse A » et « Caisse B ».

**Attendu :** Admin → Imprimantes → la colonne « Terminaux » liste les deux. Les tickets des deux
caisses sortent sur cette imprimante unique. C'est le cas « un Pi imprime sur une imprimante cloud »,
ou « un Sunmi imprime sur l'imprimante d'un autre Sunmi ».

### Test 3 — Éditer un terminal sans TPE

C'était le piège : le formulaire appelait Stripe même sans lecteur de carte.

1. Admin → **Terminaux** → ouvrir un terminal dont le « Type de TPE » est « Pas de TPE ».
2. Lui choisir une imprimante, **Enregistrer**.

**Attendu :** l'enregistrement passe. **Aucune** erreur « The registration code is not set ».

### Test 4 — Révoquer un terminal

1. Admin → **Terminaux** → cocher un terminal → action « **Révoquer le terminal (coupe son accès)** » → Run.
2. Vérifier en base :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django_tenants.utils import tenant_context
   from Customers.models import Client
   from laboutik.models import Terminal
   with tenant_context(Client.objects.get(schema_name='lespass')):
       t = Terminal.objects.get(name='<le nom>')
       print('Compte actif :', t.term_user.is_active)
       print('Cle revoquee :', t.term_user.laboutik_api_key.revoked)
   "
   ```

**Attendu :** `Compte actif : False` **et** `Cle revoquee : True`. Les **deux** — révoquer la clé
seule ou désactiver le compte seul ne suffit pas (la clé est stockée sur l'appareil).

**Attendu aussi :** l'appareil révoqué ne peut plus se reconnecter à la caisse.

### Test 5 — Non-régression TPE kiosque

Le modèle `Terminal` a changé d'app : vérifier que le TPE Stripe fonctionne toujours (appairage du
reader, envoi d'un `PaymentsIntent`, affichage du montant sur le TPE).

### Test 6 — Le ticket Z et le ticket X

Clôturer une caisse depuis un terminal équipé d'une imprimante.

**Attendu :** le ticket Z sort sur l'imprimante **de ce terminal**. La clôture reste globale au lieu
(elle couvre tous les points de vente) — c'est seulement son **ticket** qui sort là où se trouve
l'opérateur.

## Changement de comportement à connaître

**Un gestionnaire connecté dans un navigateur n'imprime plus le ticket client.** Il n'a pas de
`Terminal`, donc pas d'imprimante — et il n'y a aucun moyen de lui en configurer une.

C'est cohérent (une imprimante appartient à un appareil, pas à un onglet), mais si un lieu comptait
là-dessus, il faut lui appairer un vrai terminal.

Côté dev, `create_test_pos_data` rattache l'imprimante mock aux terminaux **déjà appairés**. S'il
n'y en a aucun, la commande le dit et **rien n'imprimera** tant qu'un appareil n'aura pas été
appairé.

## Test 7 — Sécurité du canal d'impression (chantier 02)

Le canal `ws/printer/<uuid>/` transporte le **contenu des tickets clients**. Avant, tout
compte authentifié pouvait s'y abonner. Maintenant, **seul le terminal propriétaire** de
l'imprimante le peut.

**Non-régression (le plus important) :** une tablette Sunmi Inner reçoit toujours ses tickets.
Encaisser une vente sur un terminal dont l'imprimante est de type « Sunmi Inner » → le ticket
sort. Si **rien ne sort**, c'est que l'émetteur et le récepteur ne nomment plus le canal
pareil — et ce genre de panne est **silencieuse**, aucune erreur n'est levée.

**Le verrou :** connecté en admin dans un navigateur, ouvrir la console et tenter :
```js
new WebSocket(`wss://${location.host}/ws/printer/<uuid-d-une-imprimante>/`)
```
**Attendu :** la connexion est **fermée** par le serveur. Avant, elle était acceptée et on
recevait les tickets en clair.

Vérifier aussi dans les logs du serveur :
```
[WS] Printer connexion refusee : l'imprimante <uuid> n'est pas celle de cet utilisateur
```

## Test 8 — Appairage : un seul écran pour tout le matériel

### 8a. Créer un terminal fabrique son code PIN

1. Admin → **Terminaux matériels → Terminaux** → « Créer ». Nom : « Caisse Test ».
   Type d'appareil : « Caisse LaBoutik ».
2. **Attendu** : la colonne « État » affiche aussitôt un code à 6 chiffres — `123 456`.
3. Vérifier que le type « **Tireuse** » n'est **pas** proposé dans le menu : une tireuse se crée
   depuis son propre écran (elle porte du métier : fût, débitmètre, prix).

### 8b. L'appairage remplit le terminal

```bash
curl -sk -X POST "https://tibillet.localhost/api/discovery/claim/" \
  -H "Content-Type: application/json" -d '{"pin_code": "<le code>"}'
```

**Attendu** : la colonne « État » passe à « **✓ Appairé** ». Le terminal n'a pas été créé par le
claim — il **existait déjà**, le claim lui a posé son compte.

### 8c. Une tireuse s'appaire comme une caisse

1. Admin → **Tireuses** → créer une tireuse.
2. **Ouvrir** la tireuse : son code PIN s'affiche dans la fiche (pas dans la liste — il ne sert
   qu'au moment où l'on installe le Pi).
3. Appairer avec ce code.

**Attendu** : la réponse contient `api_key` **et** `tireuse_uuid`. La tireuse apparaît aussi dans
**Terminaux**, avec le type « Tireuse ».

### 8d. Le Raspberry Pi crame — le terminal survit

C'est **le** scénario à valider.

1. Admin → **Terminaux** → cocher un terminal **appairé** (avec une imprimante assignée).
2. Action « **Générer un nouveau code PIN** ».

**Attendu** :
- l'ancien compte est **désactivé** et son ancienne clé **révoquée** — l'appareil perdu ne peut
  plus rien faire, même s'il a encore sa clé en mémoire ;
- le terminal repasse « en attente », avec un **nouveau code PIN** ;
- **il garde son imprimante**. Pour une tireuse, elle garde toute sa configuration et son
  historique de services.

**Le matériel est jetable, le métier persiste.**

### 8e. Une tireuse se révoque (c'était impossible avant)

Admin → **Terminaux** → cocher la tireuse → action « **Révoquer le terminal** ».

**Attendu** : le compte est désactivé **et** la `TireuseAPIKey` est révoquée. Le Pi ne peut plus
servir de bière.

### 8f. Le code PIN expire

Créer un terminal, attendre **plus d'une heure**, puis tenter le claim.

**Attendu** : refusé (400). La colonne « État » affiche « Code PIN expiré — à régénérer ».
L'action « Générer un nouveau code PIN » en redonne un valide.

### 8g. Un lecteur de carte n'appartient qu'à un seul terminal

1. Créer un terminal avec un TPE (type « bbpos_wisepos_e » + code d'enregistrement).
2. Créer un **second** terminal avec **le même** code d'enregistrement.

**Attendu** : le formulaire refuse, avec « Ce lecteur est déjà rattaché à un autre terminal ».
Sans ce garde-fou, deux caisses croiraient piloter le même TPE — et un client verrait s'afficher,
sur le lecteur devant lui, le montant de la vente d'à côté.

### 8h. ⚠️ Les tireuses de dev doivent être ré-appairées

Celles qui existaient avant le chantier ont `terminal = NULL`. Il faut les recréer, ou leur
générer un terminal, puis relancer le script d'installation sur le Pi.

## Test 9 — La limitation de débit du claim (sécurité)

Le claim est limité à **10 requêtes/minute**. Ce garde-fou était **contournable** : DRF faisait
confiance à l'en-tête `X-Forwarded-For` fourni par le client.

**Vérifier que le contournement est bien fermé** :
```bash
# Onze requêtes avec un X-Forwarded-For différent à chaque fois.
for i in $(seq 1 11); do
  curl -sk -o /dev/null -w "%{http_code} " -X POST \
    "https://tibillet.localhost/api/discovery/claim/" \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 1.2.3.$i" \
    -d '{"pin_code": "000000"}'
done; echo
```
**Attendu** : les premières renvoient 400 (PIN invalide), puis **429 (Too Many Requests)**.
Avant le correctif, elles auraient **toutes** renvoyé 400 — la limite ne s'appliquait jamais.

## Reste à faire

- **`LaboutikConsumer`** (`ws/laboutik/{pv_uuid}/`) porte le même anti-pattern que celui corrigé
  au chantier 02 : aucun contrôle d'accès, et un groupe Redis sans préfixe de tenant. Gravité
  faible aujourd'hui (jauges, badges de stock — pas de données nominatives), mais à traiter si
  ce canal porte un jour de la donnée sensible.
- **Front (Filaos)** : voir la liste des points à vérifier dans le rapport de session
  (abonnement WebSocket sur la page « carte primaire », absence de reconnexion après coupure,
  flag `sunmiInnerPrinterOK` figé au démarrage).
