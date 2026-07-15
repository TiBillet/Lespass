# CHANTIER 04 — La tireuse rejoint le pipeline d'appairage commun

> **Statut : FAIT (2026-07-14).** 864 tests verts. Appairage vérifié de bout en bout, y
> compris le script du Raspberry Pi : `.env` généré, clé valide, `ping` → `pong`.
>
> Ce chantier vient du chantier [IMPRESSION](../IMPRESSION/INDEX.md) (chantier 03) — il touche
> `controlvanne` de plein fouet, d'où cette fiche.
>
> ⚠️ **Les tireuses existantes doivent être ré-appairées** (nouveau code PIN + `make claim`).

## Le problème

La tireuse était le **vilain petit canard** de l'appairage.

| | Caisse / Borne | **Tireuse (avant)** |
|---|---|---|
| Compte (`TermUser`) | ✅ | ❌ |
| `Terminal` | ✅ | ❌ |
| Clé d'API | ✅ liée au compte | ✅ **sans compte** |
| Identité durable | `TermUser` / `Terminal` | **le `PairingDevice` lui-même** |
| **Révocable ?** | ✅ | ❌ **non** |

Deux conséquences :

1. **Une tireuse ne pouvait pas être révoquée.** Rien ne reliait sa clé d'API à un appareil.
   Un Raspberry Pi volé ou déclassé gardait un accès valide, indéfiniment.
2. **`PairingDevice` ne pouvait jamais être supprimé.** `TireuseBec.pairing_device` était la
   dernière clé étrangère qui pointait vers lui. Il prétendait n'être qu'un jeton d'appairage,
   mais il était en réalité l'identité durable de la tireuse.

## Pourquoi la clé étrangère ne pouvait pas simplement disparaître

`TireuseBec.pairing_device` servait au **claim** : c'est par elle qu'il savait *quelle* tireuse
il était en train d'appairer (`TireuseBec.objects.filter(pairing_device=...)`).

Et le lien inverse était **impossible** : `PairingDevice` vit dans le schéma `public`,
`TireuseBec` dans celui du lieu. Une clé étrangère PostgreSQL vise une table physique unique —
depuis `public`, elle ne saurait pas *laquelle* des N tables `controlvanne_tireusebec` viser.

Voir [SPEC.md §3](../IMPRESSION/SPEC.md#3-la-contrainte-qui-commande-tout--le-multi-tenant).

## La solution

**Un pointeur qui ne vit que le temps de l'appairage.**

```
1. L'admin crée une tireuse.
   → le signal post_save fabrique un PairingDevice avec :
        pin_code   = 6 chiffres
        cible_uuid = l'identifiant de CETTE tireuse   ← un simple UUID, PAS une FK

2. Le Pi envoie le PIN sur la route publique /api/discovery/claim/.

3. Le claim, dans le tenant_context du lieu :
        retrouve la tireuse par cible_uuid
        crée un TermUser        ← le compte de l'appareil
        crée un Terminal        ← l'appareil lui-même
        crée une TireuseAPIKey(user=term_user)
        pose TireuseBec.terminal   ← LA VRAIE CLÉ ÉTRANGÈRE, tenant → tenant

4. PairingDevice.claim() vide le pin_code ET le cible_uuid.
   → il est consommé. Plus rien ne pointe vers lui. Il est supprimable.
```

L'objection « c'est une clé étrangère déguisée, sans intégrité » tombe : le pointeur ne vit que
quelques minutes. L'identité durable, elle, est portée par une **vraie** clé étrangère.

## Ce qui a changé, fichier par fichier

| Fichier | Changement |
|---|---|
| `controlvanne/models.py` | `TireuseBec.pairing_device` **supprimé** → **`TireuseBec.terminal`** (OneToOne vers `laboutik.Terminal`). **`TireuseAPIKey.user`** ajouté (OneToOne, nullable) |
| `controlvanne/signals.py` | Le signal écrit `cible_uuid` au lieu de la clé étrangère |
| `controlvanne/admin.py` | Le code PIN se retrouve par `cible_uuid`. La colonne affiche le code, « Expiré », ou « Appairée : \<nom\> » |
| `controlvanne/Pi/config/claim.sh` | **Messages d'erreur** : le script disait juste « échec ». Il affiche maintenant le code HTTP et la cause (PIN expiré, déjà utilisé, throttle…) |
| `controlvanne/Pi/README.md` | Durée de vie du PIN, régénération, révocation |
| `controlvanne/README.md` | Tuto d'appairage corrigé |
| `discovery/*` | `cible_uuid`, expiration du PIN, `_create_tireuse_terminal()` |
| `Administration/admin/laboutik.py` | « Révoquer le terminal » coupe **les deux** classes de clé |

**Migrations** : `controlvanne/0005`, `discovery/0004`. Aucune data migration (rien en prod).

## Les deux systèmes de clés ne fusionnent pas

`TireuseAPIKey` gagne un champ `user`, mais **reste une classe distincte** de `LaBoutikAPIKey`.

Raison : les permissions de `controlvanne` (`HasTireuseAccess`) s'appuient sur cette classe.
Fusionner sur `LaBoutikAPIKey` avec un rôle élargirait la surface d'attaque — une clé de caisse
pourrait alors piloter une vanne — pour un gain nul. C'est cohérent avec la doctrine du projet
(« hybride additif, zéro fusion »).

## Ce que ça débloque

- **Une tireuse se révoque** : Admin → **Terminaux** → cocher → « Révoquer le terminal ».
  L'action coupe les **deux** accès : le compte (`is_active`) **et** la clé (`revoked`).
  Le second est indispensable — la clé est stockée sur le Pi ; sans le révoquer, il suffirait
  de réactiver le compte pour qu'il se reconnecte tout seul.
- **Le code PIN expire** (une heure). Avant, un code oublié dans l'admin restait réclamable
  pour toujours. Une action « Régénérer le code PIN » en redonne un.
- **`PairingDevice` est devenu jetable.** Vérifié : après appairage, on le supprime — la tireuse
  et son terminal survivent intacts.

## Une faille trouvée à la relecture

**La limitation de débit du claim était contournable.** Corrigé par `'NUM_PROXIES': 1` dans
`REST_FRAMEWORK` (`TiBillet/settings.py`).

DRF identifie l'appelant via `X-Forwarded-For`. Sans ce réglage, il faisait confiance à
**l'en-tête entier fourni par le client** — falsifiable. Et notre nginx *ajoute* l'adresse réelle
en fin d'en-tête au lieu de l'écraser. Il suffisait donc d'envoyer un `X-Forwarded-For` différent
à chaque requête pour obtenir une identité neuve : **la limite de 10 requêtes/minute ne
s'appliquait jamais**, et les 900 000 codes PIN possibles devenaient balayables en quelques
minutes sur une route publique.

Le défaut **préexistait**, mais c'est ce chantier qui le rendait exploitable, en exposant un
secret court sur une route publique.

## Installer un Pi après ce chantier

**Le contrat de la réponse du claim est INCHANGÉ** (`server_url`, `api_key`, `tireuse_uuid`,
`device_name`). Le script `claim.sh` fonctionne donc **sans modification de fond** — seuls ses
messages d'erreur ont été améliorés.

```bash
# 1. Admin → Tireuses → créer la tireuse. Lire le code PIN (colonne « Code PIN »).
#    ⏱️ Il expire en une heure : créez-la au moment d'installer le Pi.

# 2. Sur le Pi, en SSH :
wget https://raw.githubusercontent.com/TiBillet/Lespass/main-fedow-import/controlvanne/Pi/install_pi.sh \
  && chmod +x install_pi.sh && ./install_pi.sh

# SERVER = l'adresse RACINE de TiBillet (https://tibillet.org),
#          PAS le sous-domaine du lieu. Le Pi ne connaît pas encore son lieu :
#          c'est le serveur qui le lui apprend, dans sa réponse.

# 3. Vérifier : Admin → Tireuses → la colonne affiche « Appairée : <nom> ».
#    La tireuse apparaît aussi dans Admin → Terminaux.
```

**Vérifié en réel** : `.env` généré (`SERVER_URL`, `API_KEY`, `TIREUSE_UUID`), puis
`POST /controlvanne/api/tireuse/ping/` avec la clé → **`pong`**.

## Point ouvert (hors périmètre)

Une `TireuseAPIKey` valide peut piloter **n'importe quelle** tireuse du lieu : `authorize` prend
le `tireuse_uuid` du payload sans vérifier qu'il correspond bien à la clé
(`controlvanne/viewsets.py:229-235`). C'est **préexistant**.

Mais ce chantier rend le durcissement possible : la chaîne `clé → user → terminal → tireuse`
existe désormais. Il suffirait de vérifier que le `tireuse_uuid` demandé est bien celui de la
tireuse du terminal qui présente la clé.
