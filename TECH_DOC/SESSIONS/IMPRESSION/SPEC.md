# SPEC — Routage de l'impression par terminal

## 1. Le problème

`PointDeVente.printer` (`laboutik/models.py:469`) porte l'imprimante du ticket client.

**Un point de vente n'est pas un terminal.** En festival, une vingtaine de tablettes
encaissent sur le même point de vente « Bar ». Chacune a sa propre imprimante Sunmi Inner
intégrée. Le modèle actuel ne peut pas exprimer ça.

Deux conséquences, la seconde étant la plus grave :

1. Les 20 terminaux pointent la même imprimante — un seul ticket sort, au mauvais endroit.
2. La vue injecte `state["printer"] = pv.printer` (`laboutik/views.py:1765`), et chaque
   tablette s'abonne au WebSocket `ws/printer/{uuid}/`
   (`laboutik/static/js/manageSunmiPrint.js:135-136`). Les 20 tablettes rejoignent donc **le
   même groupe Redis** `printer-{uuid}` (`wsocket/consumers.py:209`). Chaque ticket envoyé
   est reçu par les 20 : **il s'imprime en 20 exemplaires.**

## 2. Archéologie — d'où vient cette décision

**LaBoutik V1 n'a jamais lié l'imprimante au point de vente.** Le modèle `PointDeVente`
legacy (`/home/jonas/TiBillet/dev/LaBoutik/APIcashless/models.py:315`) n'a aucun champ
imprimante. Le legacy répartit les imprimantes sur quatre porteurs :

| Ce qu'on imprime | Porteur legacy |
|---|---|
| Bon de préparation (cuisine, bar) | `GroupementCategorie.printer` — « Groupe d'impression » |
| **Reçu client** | `Printer.host` → **`Appareil`** (le terminal qui encaisse) |
| Billets (impression directe) | `Articles.direct_to_printer` |
| Ticket Z | `Configuration.ticketZ_printer` (global au lieu) |

Le reçu client sortait donc sur l'imprimante **du terminal** :
`request.user.appareil.printers.first()` (`htmxview/views.py:323`).

La réécriture V2 (documentée dans [`../LABOUTIK/PLAN_LABOUTIK.md`](../LABOUTIK/PLAN_LABOUTIK.md),
section « Phase Impression ») a **supprimé le modèle `Appareil`** avec un argument explicite
(« le Printer UUID suffit, pas de pairing complexe »). Elle a donc supprimé le **porteur du
reçu client** — et `PointDeVente` en a hérité le rôle, **en une ligne, sans arbitrage écrit** :

> « **Tickets de vente / billets (POS)** : après paiement, le récapitulatif s'imprime sur
> l'imprimante du point de vente. » — `PLAN_LABOUTIK.md:3160`

C'est le seul des trois axes d'impression dont la décision n'a jamais été argumentée. Les
deux autres l'ont été (abandon de `GroupementCategorie`, abandon d'`Appareil`).

**Ce chantier restaure le porteur « terminal » que la V2 avait perdu.**

## 3. La contrainte qui commande tout : le multi-tenant

| Modèle | App | Schéma |
|---|---|---|
| `discovery.PairingDevice` | SHARED_APPS | **public** |
| `AuthBillet.TermUser` (proxy de `TibilletUser`) | SHARED_APPS | **public** |
| `laboutik.Printer`, `laboutik.PointDeVente` | TENANT_APPS | **tenant** |
| `kiosk.Terminal` | TENANT_APPS | **tenant** |

`laboutik_printer` est **dupliquée dans N schémas tenant**. Une contrainte FK PostgreSQL
pointe une table physique unique. Depuis `public`, elle ne saurait pas laquelle viser — et
en pratique la migration plante avant : `migrate_schemas` exécute les migrations SHARED sur
le seul schéma `public`, où `laboutik_printer` **n'existe pas**.

> **`PairingDevice.printer` est donc impossible.** Le sens est forcé : c'est une table
> **tenant** qui peut référencer `public`, jamais l'inverse.
>
> Le contournement `db_constraint=False` est à proscrire : il migre, mais déréférence
> contre le schéma courant à la lecture — aucune intégrité, `DoesNotExist` silencieux.

Précédents de FK tenant → public dans le projet : `BaseBillet.LaBoutikAPIKey.user`
(`BaseBillet/models.py:2855`), `kiosk.Terminal.term_user` (`kiosk/models.py:74`),
`controlvanne.TireuseBec.pairing_device` (`controlvanne/models.py:223`).

## 4. Le modèle cible — `Terminal` existe déjà

La relation métier est **N terminaux → 1 imprimante** (« le sunmi A peut imprimer sur
l'imprimante du sunmi B », « le Pi peut imprimer sur un sunmi »). Une FK exprime ça
naturellement — mais elle doit être portée par le terminal, qui vit dans `public`. Impasse.

La sortie est un objet « terminal » **côté tenant**. Et **il existe déjà** :
**`kiosk.Terminal`** (`kiosk/models.py:57`).

```python
class Terminal(models.Model):          # kiosk/models.py:57
    id           = UUIDField(primary_key=True)
    name         = CharField(...)
    term_user    = OneToOneField("AuthBillet.TibilletUser", related_name="terminal")  # l.74
    # --- TPE Stripe ---
    registration_code, stripe_id, type, archived
```

Il porte déjà exactement ce qu'il faut : l'identité (`name`), le lien vers le compte
d'authentification (`term_user`, OneToOne, tenant → public), et il vit dans le schéma tenant.
Sa docstring dit même qu'il « remplace le `Appareil.terminals` de LaBoutik ».

**Il n'y a donc pas de nouveau modèle à créer.** Il y a un modèle mal nommé et mal placé :
il s'appelle « Terminal » mais vit dans `kiosk`, alors qu'un TPE Stripe peut très bien être
branché sur une caisse LaBoutik sans borne kiosque.

### Décision : promouvoir `kiosk.Terminal` en `laboutik.Terminal`

**C'est l'objet pivot du matériel.** Tout s'y branche, et toutes ces capacités sont
optionnelles et indépendantes :

```python
# laboutik/models.py — TENANT_APPS
class Terminal(models.Model):
    id             # UUID
    name           # saisi par le gestionnaire à la création
    terminal_role  # LB caisse / KI kiosque / TI tireuse
    term_user      # OneToOne → TibilletUser (tenant → public). VIDE tant qu'il n'est pas appairé

    # Capacité « imprime »
    printer        # FK → Printer, SET_NULL, null, blank, related_name='terminaux'

    # Capacité « encaisse par carte » — venue de kiosk
    registration_code, stripe_id (unique), type, archived

    # Une tireuse le désigne : controlvanne.TireuseBec.terminal
```

**Le terminal existe AVANT l'appareil physique** (voir
[CHANTIER 05](./CHANTIER-05-le-terminal-preexiste.md)). Le gestionnaire le crée dans l'admin,
ce qui fabrique un code PIN ; l'appareil tape ce code, et le claim **remplit** le terminal en
lui posant son compte. `term_user` vide = en attente ; `term_user` posé = appairé.

- **Résolution de l'impression** : `request.user.terminal.printer` — une indirection, pas de
  `.filter()`, pas de `.first()`.
- **Inverse** : `printer.terminaux.all()` — qui imprime sur cette imprimante.
- **Isolation** : la table vit dans le schéma tenant. Le seul dropdown admin (`printer`)
  vise une table tenant → **isolation physique, aucun filtrage manuel à écrire.**
- **Le TPE se libère du kiosque** : une caisse LaBoutik peut avoir un TPE Stripe sans être une
  borne. Le `stripe_id` est **unique** — un lecteur physique n'appartient qu'à un terminal.

> ⚠️ **Sans cette promotion, le chantier ne compile pas.** Déclarer un second modèle
> `Terminal` avec `related_name='terminal'` sur `TibilletUser` provoque un `fields.E304`
> (clash d'accesseur inverse) : **Django refuse de démarrer**. Et `user.terminal` est déjà
> utilisé pour le TPE (`kiosk/views.py:11`, `kiosk/views.py:106`,
> `wsocket/consumers.py:395`) — une fonction de résolution d'imprimante y trouverait un TPE.

### Une seule règle de résolution

Tout ce qu'un terminal imprime sort sur **son** imprimante : ticket de vente, billet, reçu
de rechargement, **ticket X et ticket Z**.

Le ticket Z est un document **global au tenant** (`ClotureCaisse` est documenté « GLOBAL au
tenant (couvre tous les PV) », `laboutik/models.py:832` ; `point_de_vente` nullable, l.853).
Il s'imprime néanmoins sur le terminal **qui en fait la demande** — c'est l'opérateur qui est
devant. Décision actée : **pas d'imprimante de gestion globale.**

## 5. Décisions actées

| Décision | Raison |
|---|---|
| **`kiosk.Terminal` → `laboutik.Terminal`** | Le modèle existe déjà et porte le bon lien. Un TPE Stripe n'est pas propre au kiosque. `controlvanne` importe déjà `laboutik` ; le claim Kiosque passe déjà par `_create_laboutik_terminal()`. |
| **`PointDeVente.printer` supprimé** | Structurellement faux. LaBoutik V2 n'est pas en production : **aucune data migration**. |
| **Pas de FK `Terminal.pairing_device`** | Aucun usage à l'exécution. Une FK `CASCADE` ferait qu'un ménage des PIN consommés dans l'admin **détruirait silencieusement la config d'un terminal en service**. On copie le `name`, les deux objets restent indépendants. |
| **Pas de FK `PairingDevice.term_user`** | `Terminal.term_user` porte déjà le lien. Deux FK diraient la même chose deux fois. |
| **La clé API reste sur le `TermUser`** | `LaBoutikAPIKey.user` est déjà un OneToOne (`BaseBillet/models.py:2855`). `terminal.term_user.laboutik_api_key` y accède. Ne pas dupliquer. |
| **Une session humaine n'imprime plus le ticket client** | Voir ci-dessous — **conséquence assumée**, à ne pas découvrir en test. |
| **`CategorieProduct.printer` inchangé** | Axe distinct (bons de préparation). Il fonctionne. |
| **`ImpressionLog` inchangé** | Vérifié : il trace déjà `operateur` (le TermUser, `laboutik/models.py:1069`) et `printer` (l.1083). Une fois le routage par terminal en place, `operateur` **identifie déjà le terminal**. Rien à ajouter pour la conformité LNE. |

### La conséquence assumée : plus d'impression en session humaine

Aujourd'hui, un **humain en session admin** qui tient la caisse dans un navigateur (cas dev,
et petits lieux via le fallback V1 de `HasLaBoutikTerminalAccess`) imprime via `pv.printer`.

Après ce chantier, il n'a **pas** de `Terminal` → pas d'imprimante → **plus d'impression du
ticket client en session humaine**, et aucun moyen de la configurer.

C'est cohérent (une imprimante appartient à un appareil, pas à un navigateur), mais **c'est
un changement de comportement visible**. Si un lieu en dépend, il faudra lui créer un
`Terminal` — ce qui est le geste correct.

## 6. Options écartées

| Option | Pourquoi non |
|---|---|
| **`PairingDevice.printer`** (FK côté terminal) | Impossible : FK public → tenant. Voir §3. |
| **Créer un `laboutik.Terminal` à côté de `kiosk.Terminal`** | `fields.E304` : Django ne démarre pas. Et une borne kiosque aurait **deux** objets « Terminal ». |
| **`Printer.terminal`** (FK simple côté imprimante) | Cardinalité inversée : une imprimante n'appartiendrait qu'à **un** terminal. Interdit le partage (sunmi A → imprimante de sunmi B). |
| **`Printer.terminaux`** (M2M vers `PairingDevice`) | Perd l'invariant « un terminal = une imprimante » (retour du `.first()`). Et le dropdown viserait une table **publique** → risque cross-tenant à filtrer à la main. |
| **Imprimante de gestion globale** (`LaboutikConfiguration.printer_gestion`) pour Z/X | Écartée : le Z sort sur le terminal qui le demande. |

## 7. Combien d'objets pour un appareil ?

**Trois**, et c'est le minimum imposé par les schémas. Chacun a une responsabilité unique.

| Objet | Schéma | Responsabilité | Pourquoi il ne peut pas fusionner |
|---|---|---|---|
| `PairingDevice` | public | Cycle de vie du PIN | Le claim arrive sur une route **publique**, avant toute résolution de tenant |
| `TermUser` | public | Principal d'authentification | `AUTH_USER_MODEL` est nécessairement SHARED |
| **`Terminal`** | **tenant** | Capacités matérielles : **imprimante**, TPE Stripe | Doit porter une FK vers `Printer` (tenant) |

La promotion de `kiosk.Terminal` **évite** d'en ajouter un quatrième.

## 8. Sécurité — une faille à refermer

`PrinterConsumer.connect()` (`wsocket/consumers.py:176`) vérifie que le tenant est résolu et
que l'utilisateur est authentifié — **et rien d'autre**. Il ne vérifie ni que l'imprimante
existe, ni qu'elle appartient au tenant courant, ni que l'utilisateur est un terminal. Et le
groupe Redis est `printer-{uuid}` (`wsocket/consumers.py:209`,
`laboutik/printing/sunmi_inner.py:194`) — **sans préfixe de tenant**.

Conséquence : tout compte authentifié qui connaît un UUID d'imprimante peut rejoindre son
groupe et **lire le contenu des tickets clients** — y compris ceux d'un autre lieu. Les
UUID sont en v4 (non devinables), donc ce n'est pas exploitable en aveugle, mais le
contrôle d'accès est vide.

Traité en [CHANTIER-02](./CHANTIER-02-securite-websocket.md).

## 9. Ce que l'isolation multi-tenant garantit déjà

Audit fait, ces barrières tiennent :

- `PairingDeviceAdmin` filtre par `tenant=connection.tenant` et force le tenant à la
  création (`discovery/admin.py:90-102`) — pas de fuite par URL forgée.
- Le **claim** cherche le PIN globalement (l'appareil ne connaît pas son tenant), mais les
  credentials sortent du tenant **du PairingDevice**. Un PIN du lieu A n'ouvre pas le lieu B.
- Le **bridge** : `LaBoutikAPIKey` est en TENANT_APPS → la clé est cherchée dans le schéma
  courant. Une clé du lieu A postée sur le bridge du lieu B est introuvable → 401.
  **Isolation physique.**
- `HasLaBoutikTerminalAccess` vérifie `client_source_id == connection.tenant.pk`
  (`BaseBillet/permissions.py:122`), et `TermUser.save()` force `client_source` à la
  création (`AuthBillet/models.py:405`).

**Point ouvert** : un PIN n'expire jamais — le claim ne vérifie que `claimed_at__isnull=True`
(`discovery/serializers.py:36`). Un PIN oublié reste claimable indéfiniment, et le throttle
est **par IP**. Un TTL sur `created_at` serait sain. Traité en
[CHANTIER-03](./CHANTIER-03-unification-appairage.md).

## 10. Hypothèse à confirmer avant le CHANTIER-01

**Le module `kiosk` est-il déployé en production quelque part ?**

- **Non** → on déplace `Terminal` (et la FK `PaymentsIntent.terminal`, `kiosk/models.py:150`)
  sans data migration.
- **Oui** → il faut un `SeparateDatabaseAndState` pour déplacer la table entre apps sans
  perdre les TPE appairés et leurs `PaymentsIntent`.
