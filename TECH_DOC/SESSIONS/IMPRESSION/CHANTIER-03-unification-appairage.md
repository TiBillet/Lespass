# CHANTIER 03 — Un seul mécanisme d'appairage

> ⚠️ **RÉVISÉ par le [CHANTIER 05](./CHANTIER-05-le-terminal-preexiste.md).**
>
> Ce document décrit un `cible_uuid` qui pointe vers la **`TireuseBec`**, et un claim qui
> **crée** le `Terminal`. **Les deux ont changé** :
>
> - `cible_uuid` pointe désormais vers le **`Terminal`**, pour les trois rôles ;
> - le claim ne crée plus rien — il **remplit** un terminal qui existait déjà ;
> - `TireuseBec.terminal` est posé **à la création de la tireuse**, plus au claim.
>
> Ce qui tient : l'unification des trois rôles, la révocation à deux leviers, l'expiration du
> code PIN, et le fait que `PairingDevice` ne soit plus qu'un jeton d'appairage.

> **Statut : FAIT (2026-07-14).** 863 tests verts. Vérifié en réel : une tireuse créée dans
> l'admin naît avec son code PIN, le claim lui pose un compte + un `Terminal` + une clé liée,
> et le `PairingDevice` en ressort vidé. **Plus aucun objet ne pointe vers lui** — vérifié en
> le supprimant : la tireuse survit, terminal intact.
>
> **Les tireuses de dev sont à ré-appairer** (nouveau PIN + script d'installation du Pi).

Voir [SPEC.md](./SPEC.md) pour le contexte.

**Objectif** : les trois rôles matériels (LaBoutik, Kiosque, Tireuse) passent par le même
pipeline d'appairage. À l'arrivée, `PairingDevice` ne sert plus qu'à l'appairage — et rien
ne pointe plus vers lui.

## Ce qui a été implémenté

| Fichier | Changement |
|---|---|
| `discovery/models.py` | `cible_uuid` (UUID, **pas** une FK). `DUREE_DE_VIE_DU_PIN` = 1 h, `pin_est_expire()`, `regenerer_le_pin()`. `claim()` vide aussi la cible |
| `discovery/serializers.py` | Le claim refuse un PIN expiré |
| `discovery/views.py` | Helper commun `_creer_le_compte_et_le_terminal()` (les 3 rôles) + `_create_tireuse_terminal()` |
| `discovery/admin.py` | Action « Régénérer le code PIN » |
| `controlvanne/models.py` | `pairing_device` **supprimé** → `TireuseBec.terminal` (OneToOne). `TireuseAPIKey.user` ajouté |
| `controlvanne/signals.py` | Le signal écrit `cible_uuid` |
| `controlvanne/admin.py` | Le PIN se retrouve par `cible_uuid` |
| `Administration/admin/laboutik.py` | « Révoquer » coupe **les deux** classes de clé |
| `controlvanne/README.md` | Tuto d'appairage corrigé |

**Migrations** : `discovery/0004`, `controlvanne/0005`. Aucune data migration (rien en prod).

**Tests** : `tests/pytest/test_appairage_unifie.py` (7) + 3 dans `test_discovery_claim_creates_termuser.py`.

## La faille que la relecture a trouvée : le throttle était contournable

`TiBillet/settings.py` — ajout de **`'NUM_PROXIES': 1`** dans `REST_FRAMEWORK`.

Pour identifier qui appelle, DRF lit `X-Forwarded-For`. Sans `NUM_PROXIES`, il prend **cet
en-tête en entier** — fourni par le client, donc falsifiable. Et le nginx de prod *ajoute*
l'adresse réelle en fin d'en-tête (`$proxy_add_x_forwarded_for`) au lieu de l'écraser.

Il suffisait donc d'envoyer un `X-Forwarded-For` différent à chaque requête pour obtenir une
identité neuve : **la limite de 10 requêtes/minute du claim ne s'appliquait jamais.** Un code
PIN fait 6 chiffres, sur une route publique — 900 000 combinaisons, balayables en quelques
minutes.

Avec `NUM_PROXIES = 1`, DRF retient la **dernière** adresse de la liste : celle que nginx
vient d'ajouter, la seule que le client ne peut pas falsifier. Vérifié : quel que soit le
`X-Forwarded-For` forgé, l'identité de throttle reste l'IP réelle.

Le défaut **préexistait** au chantier, mais c'est lui qui le rendait exploitable, en exposant
un secret court sur une route publique. Le réglage protège maintenant **tous** les throttles
DRF du projet.

## État des lieux

Après le chantier 01, deux rôles sur trois sont unifiés :

| Rôle | Au claim | Identité durable |
|---|---|---|
| `LB` LaBoutik | `TermUser` + `LaBoutikAPIKey` + **`Terminal`** | `TermUser` / `Terminal` |
| `KI` Kiosque | idem (même helper) | idem |
| `TI` Tireuse | **`TireuseAPIKey` seule** — pas de `TermUser` | **`PairingDevice`** |

La tireuse est l'exception. Son `PairingDevice` n'est pas un jeton d'appairage éphémère :
c'est son **identité durable**.

## Pourquoi `TireuseBec.pairing_device` ne se retire pas d'une ligne

`controlvanne/models.py:223`. La FK sert à **deux** choses :

1. **Le signal** `controlvanne/signals.py:183-205` : à la création d'une `TireuseBec`, il
   crée automatiquement un `PairingDevice` (c'est ainsi que naît le PIN de la tireuse) et
   stocke la FK.
2. **Le claim** : `TireuseBec.objects.filter(pairing_device=pairing_device).first()`
   (`discovery/views.py:86`). **C'est par cette FK que le claim sait quelle tireuse il
   appaire.** Sans elle, il n'a aucun moyen de la retrouver.

Et on retombe sur la contrainte de la SPEC : `PairingDevice` est **public**, `TireuseBec`
est **tenant**. Le lien inverse (`PairingDevice.tireuse`) est **impossible**.

Il faut donc **substituer** un mécanisme, pas juste supprimer la FK.

## La solution retenue

L'appairage a besoin de transporter une **cible** du schéma tenant jusqu'à une route
publique. Deux mécanismes se composent :

**Un `UUIDField` « cible » sur `PairingDevice`, qui ne vit que le temps de l'appairage.**

1. Le signal (`controlvanne/signals.py:183-205`) crée le `PairingDevice` et y écrit
   `cible_uuid = tireuse.uuid`. Ce n'est **pas** une FK — juste un UUID. Pas de contrainte
   cross-schéma, donc légal.
2. Au claim, dans le `tenant_context`, on résout la `TireuseBec` par cet UUID, on crée le
   `Terminal` (comme pour LB et KI), et on pose **`TireuseBec.terminal`** — une vraie FK
   tenant → tenant, avec intégrité référentielle.
3. On **vide `cible_uuid`**, comme le `pin_code` l'est déjà.

L'objection « FK déguisée sans intégrité » tombe : le pointeur ne vit que quelques minutes,
et l'identité durable est portée par une vraie FK. C'est le miroir exact de ce que
`PairingDevice` fait déjà avec `tenant` et `terminal_role` : des métadonnées de routage du
claim, pas un lien durable.

## Les clés API : ajouter `user`, ne pas fusionner

`TireuseAPIKey` est créée **sans user** (`discovery/views.py:93`), là où `LaBoutikAPIKey.user`
est un OneToOne vers le `TermUser` (`BaseBillet/models.py:2855`).

**Décision : ajouter un champ `user` à `TireuseAPIKey`** (copier le pattern de
`LaBoutikAPIKey.user`). **Ne pas fusionner** les deux systèmes de clés.

Raison : c'est cohérent avec la doctrine du projet (« hybride additif, zéro fusion »), ça
laisse les classes de permission de `controlvanne` intactes, et fusionner sur
`LaBoutikAPIKey` avec un rôle élargirait la surface d'attaque pour un gain nul.

## Ce qu'on gagne à l'arrivée

- **Un seul pipeline** de claim, un seul type d'identité durable (`TermUser` + `Terminal`),
  une seule action « Révoquer le terminal » pour les trois rôles.
- **Plus aucune FK ne pointe vers `PairingDevice`.** Il redevient ce qu'il prétend être : un
  jeton d'appairage. On peut alors faire le ménage des PIN consommés sans rien casser.

  > Recommandation : **ne pas le supprimer automatiquement**. `created_at` / `claimed_at` sont
  > une trace d'audit qui ne coûte rien. Une fois qu'aucune FK ne pointe vers lui, le ménage
  > devient un choix d'exploitation, pas une contrainte de modèle.

- Une tireuse devient administrable comme les autres terminaux (nom lisible, révocation).

## À traiter dans la foulée

**TTL sur les PIN.** Le claim ne vérifie que `claimed_at__isnull=True`
(`discovery/serializers.py:36`) : un PIN oublié reste claimable indéfiniment, et le throttle
est par IP. Ce chantier touche déjà l'appairage — ajouter une expiration (~1 h sur
`created_at`) y a sa place.

**Le tuto d'appairage de `controlvanne/README.md` est à relire, corriger et retester.** Il
décrit la procédure d'appairage d'une tireuse telle qu'elle est aujourd'hui (PIN →
`TireuseAPIKey`, pas de `TermUser`). Ce chantier la change entièrement. Un tuto faux est
pire que pas de tuto : c'est la première chose que lit quelqu'un qui installe une tireuse.

## Périmètre — attention

Ce chantier touche `discovery`, `controlvanne`, `kiosk`, `laboutik`, **deux systèmes de clés
API** et le claim. La surface de test est large. Le découper à nouveau si besoin.
