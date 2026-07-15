# IMPRESSION — Hub du chantier

Le module d'impression de `laboutik` route aujourd'hui le **ticket client** par le
**point de vente** (`PointDeVente.printer`). C'est faux : en festival, **20 terminaux
partagent le même point de vente**. Les 20 tablettes se retrouvent donc à partager une
seule imprimante — et, pire, à s'abonner toutes au **même groupe WebSocket**, ce qui fait
sortir chaque ticket en autant d'exemplaires qu'il y a de tablettes connectées.

Ce chantier remplace ce routage par un **objet `Terminal`**, et en profite pour refermer
une faille d'écoute WebSocket et pour préparer l'unification de l'appairage des trois
rôles matériels (LaBoutik, Kiosque, Tireuse).

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [SPEC.md](./SPEC.md) | **La spec** : archéologie de la décision, contraintes multi-tenant, modèle de données cible, décisions actées et écartées | — |
| [CHANTIER-01-terminal-et-routage.md](./CHANTIER-01-terminal-et-routage.md) | Modèle `Terminal`, suppression de `PointDeVente.printer`, résolution de l'imprimante, abonnement WebSocket, admin | ✅ **FAIT 2026-07-14** — 846 tests verts, vérifié dans Chrome |
| [CHANTIER-02-securite-websocket.md](./CHANTIER-02-securite-websocket.md) | Durcissement du `PrinterConsumer` : contrôle d'accès et cloisonnement du groupe Redis par tenant | ✅ **FAIT 2026-07-14** — 854 tests verts |
| [CHANTIER-03-unification-appairage.md](./CHANTIER-03-unification-appairage.md) | Un seul mécanisme d'appairage pour les trois rôles. Retrait de `TireuseBec.pairing_device`, convergence des clés API, `PairingDevice` réduit à l'appairage | ✅ **FAIT** — ⚠️ **révisé par le 05** |
| [CHANTIER-05-le-terminal-preexiste.md](./CHANTIER-05-le-terminal-preexiste.md) | **Le terminal existe AVANT l'appareil.** On le crée dans l'admin (ce qui fabrique son code PIN), le claim le **remplit**. `PairingDevice` sort de l'admin. Un seul écran pour tout le matériel | ✅ **FAIT** — ⚠️ « pas de TPE objet » révisé par le 06 |
| [CHANTIER-06-extraction-tpe.md](./CHANTIER-06-extraction-tpe.md) | **Le lecteur de carte devient un objet** (`TPEBancaire`), typable (Stripe, demain SumUp) et **déplaçable** d'un appareil à l'autre. Sidebar : Terminaux + Imprimantes + TPE bancaires | ✅ **FAIT 2026-07-15** — vérifié dans Chrome |

> ⚠️ **Le CHANTIER 05 révise les chantiers 01 et 03** : ils décrivent un claim qui *crée* le
> terminal. Ce n'est plus le cas. Les bandeaux en tête de ces documents le disent.

**Écarts entre la spec et l'implémentation :**

- `StripeLocation` a dû suivre `Terminal` dans `laboutik`. Elle n'est utilisée que par le
  TPE ; la laisser dans `kiosk` aurait créé un couplage circulaire.
- Le TPE a finalement été **extrait en modèle** (`TPEBancaire`) au chantier 06 — la décision
  « pas d'objet TPE » posée ici est révisée.

## Le pivot : `Terminal` existe déjà

Le chantier a besoin d'un objet « appareil appairé » côté tenant, capable de porter une FK
vers `Printer`. **Il existe : `kiosk.Terminal`** (`kiosk/models.py:57`). Il est simplement
mal placé — un TPE Stripe n'est pas propre au kiosque.

On le **promeut en `laboutik.Terminal`** et on lui ajoute une capacité « imprime ». En créer
un second était de toute façon impossible : deux `related_name="terminal"` sur `TibilletUser`
→ `fields.E304`, Django refuse de démarrer.

## Ce qui ne bouge pas

**`CategorieProduct.printer`** (`BaseBillet/models.py:1022`) route les **bons de
préparation** (cuisine, bar) par catégorie de produit. C'est un axe distinct du ticket
client, il fonctionne, et ce chantier n'y touche pas.

## Impact sur les autres apps

| App | Document |
|---|---|
| `kiosk` | [`../KIOSK/IMPACT-CHANTIER-IMPRESSION.md`](../KIOSK/IMPACT-CHANTIER-IMPRESSION.md) — `Terminal` déménage, le TPE se libère du kiosque |
| `controlvanne` | [`../CONTROLVANNE/CHANTIER-04-appairage-unifie.md`](../CONTROLVANNE/CHANTIER-04-appairage-unifie.md) — appairage unifié, la tireuse devient révocable. Tutos et script du Pi corrigés |

## Repères

- Archive de la conception d'origine : [`../LABOUTIK/PLAN_LABOUTIK.md`](../LABOUTIK/PLAN_LABOUTIK.md), section « Phase Impression »
- Doc constructeur : [`../../SUNMI/`](../../SUNMI/)
- LaBoutik V1 legacy : `/home/jonas/TiBillet/dev/LaBoutik`
