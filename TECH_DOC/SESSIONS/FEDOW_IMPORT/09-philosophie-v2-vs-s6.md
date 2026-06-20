# Recherche 09 — La philosophie choisie par la V2, comparée à S6

Date : 2026-06-10
Source : `lespass-main/TECH DOC/SESSIONS/LABOUTIK/PLAN_LABOUTIK.md` (4 717 l.),
sections « Vision », « Coexistence V1/V2 », « Statut par phase ».

> **DÉCISION ACTÉE 2026-06-20 (point 4).** L'embranchement est tranché : **voie S6 —
> réseau unique** (interop legacy). La voie **V2-pure (FED local) est écartée** : pas de
> `bootstrap_fed_asset`, pas de tenant `federation_fed`, **jamais de FED en local**. Les
> nouveaux lieux rejoignent le réseau des 500 dès le départ. Ce document garde le
> raisonnement qui a mené là ; le « décider au 1er tenant réel » plus bas est donc **résolu**.

## Le scénario implicite de la V2

| Axe | Choix V2 (PLAN_LABOUTIK) |
|---|---|
| Vision | Fusion mono-repo totale : « 1 seul Django, accès DB direct, transaction.atomic() couvre tout » |
| Coexistence | Par population stricte : anciens tenants = V1 intact (carte Caisse V2 grisée) ; nouveaux = « V2 directe, tout en DB direct » |
| Pureté runtime | « Les vues laboutik utilisent TOUJOURS fedow_core — pas de double-chemin if use_fedow_core » |
| Monnaie fédérée | **FED local neuf** (tenant `federation_fed`, recharge Stripe session 31) → 2e réseau, étanche au réseau des 500 lieux |
| Migration des anciens | **Différée** : phases ⑩ (import données Fedow + LaBoutik) et ⑪ (consolidation, suppression fedow_connect) À FAIRE |
| Incohérence résiduelle | La création des wallets users passe ENCORE par le legacy HTTP (audit B6) : identité legacy, valeur locale |

En termes de nos scénarios : **S2 comme présent (réseau scindé, zéro pont),
S1 comme dette future (la grosse migration, repoussée)**.

## Comparaison avec S6

| | V2 pure (plan actuel lespass-main) | S6 (hybride additif) |
|---|---|---|
| Runtime | Le plus simple (aucun pont) | Pont cartes + segment legacy dans la cascade |
| Réseau de cartes | **Scindé** : nouveaux lieux hors réseau existant | **Unique** : cartes des 500 lieux acceptées |
| Migration de données | Dette différée (phases ⑩⑪ = la partie la plus risquée selon l'audit : B3, B4, .re) | **Dissoute** : le legacy n'est jamais importé |
| Coût C-C | Bootstrap FED local + recharge V2 (déjà codés) | Interop legacy : 3-4 sessions + 4 parades |
| Validé par | L'avocat du diable (recommandation « séparation nette ») | Le creusage doc 08 (viable sous conditions) |

**Constat clé : S6 = V2 moins UNE décision.** Le socle est identique
(copier-coller, population split, identité wallet via legacy). L'unique
embranchement : où vit la monnaie fédérée des nouveaux tenants —
FED local neuf (V2) ou FED legacy via API (S6).

## Conséquence pratique : le tronc commun

Les lots **C-A (copier-coller du socle)** et **C-B (durcissement audit +
parades)** sont rigoureusement identiques dans les deux voies. Seul le C-C
diverge :

- Voie V2 pure : bootstrapper `federation_fed` + porter la recharge
  CASHLESS_REFILL (code existant) — ~2 sessions de moins.
- Voie S6 : interop legacy (doc 08) — réseau unique.

**Recommandation** : démarrer C-A + C-B sans trancher. Décider l'embranchement
au premier tenant réel :
- lieu autonome (sa monnaie propre, pas besoin du réseau) → voie V2 pure ;
- lieu rejoignant le réseau de cartes existant → interop S6 (additive,
  activable après coup).

Ne PAS activer les deux (FED local + acceptation legacy) sans nécessité :
deux pots fédérés = confusion comptable et UX.

## Garde-fou de décision

Si la voie V2 pure est choisie, acter explicitement que les phases ⑩⑪ du
PLAN_LABOUTIK (import des anciens tenants) héritent des bloquants B3/B4/B7 de
l'audit (doc 02) — ce n'est pas un détail d'implémentation, c'est le morceau
le plus risqué du programme, et il reste dû dans cette voie.
