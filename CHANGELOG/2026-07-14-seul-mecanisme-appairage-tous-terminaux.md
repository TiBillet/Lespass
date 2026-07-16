# Un seul mécanisme d'appairage pour tous les terminaux / One pairing mechanism for all terminals

**Date :** 2026-07-14
**Migration :** **Oui** — `discovery/0004` et `controlvanne/0005`.
`migrate_schemas --executor=multiprocessing`
**Spec :** [`TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-03`](TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-03-unification-appairage.md)

### 1. La tireuse était le vilain petit canard

**Quoi / What :** les caisses et les bornes recevaient, à l'appairage, un compte (`TermUser`),
un `Terminal` et une clé d'API. La tireuse, elle, ne recevait qu'une `TireuseAPIKey` — **sans
compte, sans terminal**. Son `PairingDevice` lui tenait lieu d'identité durable.

**Pourquoi / Why :** conséquence directe — **une tireuse ne pouvait pas être révoquée.** Rien
ne reliait sa clé à un appareil. Et le `PairingDevice`, censé n'être qu'un jeton d'appairage,
ne pouvait jamais être supprimé.

Les trois rôles suivent désormais le **même pipeline** : compte + `Terminal` + clé. Seule la
**classe** de la clé diffère (`TireuseAPIKey` pour une tireuse, `LaBoutikAPIKey` sinon), parce
que les permissions de controlvanne s'appuient dessus. Les deux systèmes de clés restent
**séparés** — les fusionner élargirait la surface d'attaque sans rien apporter.

Une tireuse se révoque maintenant comme une caisse : Admin → Terminaux → « Révoquer ».

### 2. `PairingDevice` ne fait plus que l'appairage

**Quoi / What :** `TireuseBec.pairing_device` (la dernière clé étrangère vers `PairingDevice`)
est **supprimée**, remplacée par `TireuseBec.terminal` — une vraie clé étrangère tenant→tenant,
avec intégrité référentielle.

**Pourquoi / Why :** cette clé étrangère servait au claim à savoir *quelle* tireuse il
appairait. Le lien inverse était impossible : `PairingDevice` vit dans le schéma `public`,
`TireuseBec` dans celui du lieu.

Il est remplacé par **`PairingDevice.cible_uuid`** — un simple UUID, sans contrainte, qui ne
vit **que le temps de l'appairage**. Le claim s'en sert pour retrouver la tireuse, pose la
vraie clé étrangère, puis le vide (comme il vide déjà le code PIN).

Résultat : **plus aucun objet ne pointe vers `PairingDevice`.** Il redevient ce qu'il prétend
être — un jeton d'appairage — et devient supprimable sans rien casser.

### 3. Un code PIN n'expire plus jamais… si, maintenant il expire

**Quoi / What :** un code PIN vit **une heure** (`PairingDevice.DUREE_DE_VIE_DU_PIN`).
Passé ce délai, le claim le refuse. Une action d'admin « Régénérer le code PIN » en redonne un
(elle refuse un appairage déjà consommé — un appareil à ré-appairer se recrée, il ne se
ressuscite pas).

**Pourquoi / Why :** un code créé puis oublié dans l'admin restait réclamable **indéfiniment**.

### 4. La limitation de débit était contournable — SÉCURITÉ

**Quoi / What :** ajout de `'NUM_PROXIES': 1` dans `REST_FRAMEWORK` (`TiBillet/settings.py`).

**Pourquoi / Why :** pour identifier qui appelle, DRF lit l'en-tête `X-Forwarded-For`. Sans
`NUM_PROXIES`, il prend **cet en-tête en entier** — or il est fourni par le client, donc
falsifiable. Notre nginx *ajoute* l'adresse réelle en fin d'en-tête
(`$proxy_add_x_forwarded_for`) au lieu de l'écraser : il suffisait donc d'envoyer un
`X-Forwarded-For` différent à chaque requête pour obtenir une **identité neuve à chaque fois**,
et la limite de 10 requêtes/minute ne s'appliquait plus jamais.

Concrètement : l'appairage se réclame avec un code à **6 chiffres**, sur une route **publique**.
Sans limite de débit réelle, les 900 000 codes possibles se balaient en quelques minutes.

Avec `NUM_PROXIES = 1`, DRF retient la **dernière** adresse de la liste : celle que nginx vient
d'ajouter, la seule que le client ne peut pas falsifier.

> Le défaut **préexistait** à ce chantier, mais c'est lui qui le rendait exploitable, en
> exposant un secret court sur une route publique. Le réglage protège désormais **tous** les
> throttles DRF du projet.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `discovery/models.py` | **Nouveau** `cible_uuid`. Durée de vie du PIN, `pin_est_expire()`, `regenerer_le_pin()`. `claim()` vide aussi la cible |
| `discovery/serializers.py` | Le claim refuse un code PIN expiré |
| `discovery/views.py` | **Nouveau** helper commun `_creer_le_compte_et_le_terminal()`, partagé par les trois rôles. **Nouveau** `_create_tireuse_terminal()` |
| `discovery/admin.py` | **Nouvelle** action « Régénérer le code PIN » |
| `controlvanne/models.py` | `TireuseBec.pairing_device` **supprimé** → `TireuseBec.terminal`. **Nouveau** `TireuseAPIKey.user` |
| `controlvanne/signals.py` | Le signal écrit `cible_uuid` au lieu de la clé étrangère |
| `controlvanne/admin.py` | Le code PIN se retrouve par `cible_uuid`. Affiche « Appairée », « Code PIN expiré », ou le code |
| `controlvanne/README.md` | **Le tuto d'appairage est corrigé** |
| `Administration/admin/laboutik.py` | « Révoquer le terminal » coupe **les deux** classes de clé |
| `tests/pytest/test_appairage_unifie.py` | **Nouveau** — 6 tests |

### Attention / Heads-up

**Les tireuses de dev doivent être ré-appairées** (nouveau code PIN dans l'admin, script
d'installation relancé sur le Pi). Rien n'est en production, donc aucune data migration.
