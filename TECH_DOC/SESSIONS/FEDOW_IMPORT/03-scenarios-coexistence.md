# Recherche 03 — Comparaison des scénarios de coexistence V1/V2

Date : 2026-06-10
Contexte : suite à l'audit profond (doc 02), trois scénarios de transition sont
sur la table. La correction du drift (`reconcile_tokens`) passe en prod dans la
nuit du 10 au 11 juin → les soldes legacy redeviennent fiables pour tous les
scénarios.

---

## Les trois scénarios

### S1 — Migration par population (plan initial, audité)
Anciens tenants V1, nouveaux tenants V2, et chaque tenant V1 migre
individuellement (toutes ses données, FED compris) quand il bascule.

### S2 — Zéro migration
Anciens tenants V1 pour toujours (ou très longtemps), nouveaux tenants V2
complets, y compris un FED V2 **neuf et étanche** au FED legacy.
Aucun import de données.

### S3 — Split par catégorie d'asset (proposition mainteneur 2026-06-10)
Le FED reste sur Fedow legacy **pour tous les tenants, y compris les nouveaux**.
Les assets locaux / cadeau / temps (TLF, TNF, TIM, FID) basculent en V2,
tenant par tenant. Fedow legacy ne sert plus que le FED, jusqu'à une bascule
FED finale en bloc.

---

## Tableau comparatif

| Critère | S1 population | S2 zéro migration | S3 split par asset |
|---|---|---|---|
| Réseau FED | Scindé pendant la transition, double registre risqué (B3) | Scindé définitivement (2 réseaux étanches) | **Unique en permanence** |
| Import de données | Massif, tous les bloquants B3/B4/B5/B7 actifs | **Aucun** | Réduit : assets locaux d'un tenant volontaire ; FED en bloc à la fin |
| Risque corruption soldes (500 lieux) | Élevé | **Nul** | Faible (périmètres petits, validés un par un) |
| Dispatch runtime | Par tenant (déjà codé en V2) | Par tenant (déjà codé) | **Par asset** — nouveau, flux hybrides |
| Atomicité paiement | Interne au moteur | Interne au moteur | Cascade cross-moteur → à neutraliser par le pattern « FED = moyen de paiement externe » |
| Cycle de vie carte | Un seul moteur par tenant | Un seul moteur par tenant | **Double écriture** (liaison, perte, vidage) dans les 2 moteurs |
| B6 (autonomie wallet sans Fedow) | Requis | Requis | Non requis pendant la transition (legacy vivant pour tous) |
| Extinction de Fedow legacy | Progressive | Jamais (ou projet futur séparé) | À la fin (bascule FED en bloc, post-drift-fix) |
| Dépendance au laboutik intégré | Pour les nouveaux tenants cashless | Pour les nouveaux tenants cashless | **Gate des migrations** : migrer les locaux d'un tenant = migrer sa caisse |
| Convergence vers la fusion complète | Oui | Non (fork permanent) | **Oui** |

## Analyse S3 — points clés

**Forces**
- Conforme à la recommandation de l'audit sur B3 : les locaux migrent tenant
  par tenant, le FED migre en bloc, jamais de double registre FED.
- Un nouveau lieu rejoint le réseau de cartes existant dès le premier jour
  (cas d'usage Montpellier : 4 festivals, une carte).
- B6 neutralisé pendant la transition : la création de wallet user peut rester
  sur le chemin HTTP legacy (chaque user garde un wallet legacy pour le FED).
- Trajectoire incrémentale naturelle (voir découpage ci-dessous).

**Coûts / risques**
1. **Dispatch par asset, plus par tenant.** Le pattern `server_cashless` de
   lespass-main ne suffit plus. La plupart des flux restent purs (FED → 100 %
   legacy pour tous sans dispatch ; cadeau/temps/adhésion → 100 % V2), mais
   deux zones deviennent hybrides :
   - **Cascade de paiement POS** (cadeau V2 + FED legacy dans un même paiement) :
     pas d'atomicité cross-moteur possible. Mitigation actée : modéliser le
     FED legacy comme un **moyen de paiement externe** (même statut qu'un TPE
     carte bancaire) — en cas d'échec du débit FED, la vente reste ouverte avec
     un reste à payer. Pas de compensation distribuée.
   - **Cycle de vie carte** : liaison user, perte, vidage fin de festival =
     double écriture V2 + legacy. Modes de panne à spécifier explicitement.
2. **La caisse est le gate des migrations.** LaBoutik V1 ne parle que HTTP
   legacy : un tenant dont les tokens locaux passent en V2 doit basculer sa
   caisse vers le laboutik intégré le même jour. Le portage laboutik (10 700+
   lignes, cf. audit B9) devient prérequis du *flux de migration des tenants
   existants* (pas du socle pour les nouveaux).
3. **Assets locaux fédérés** (SSA, monnaies multi-lieux) : l'unité de migration
   est la fédération entière, pas le tenant (finding majeur de l'audit).

**Découpage incrémental possible de S3**
1. Socle fedow_core V2 durci + porté (bloquants B1/B2/B8/B9 + majeurs M1-M9) —
   nouveaux tenants : assets locaux V2 uniquement.
2. Acceptation du FED legacy chez les tenants V2 via « moyen de paiement
   externe » + cycle de vie carte double-écriture.
3. Migrations volontaires des tenants existants (assets locaux), au rythme du
   POS intégré ; fédérations locales par bloc.
4. Bascule FED finale en bloc (gel + import + extinction de Fedow legacy).

## Question décisive entre S2 et S3

**Les nouveaux lieux doivent-ils rejoindre le réseau FED existant dès
maintenant ?**
- Oui → S3, malgré le surcoût hybride (localisé et mitigeable).
- Non → S2 reste le plus simple et le moins risqué.

S1 (plan initial) est écarté : c'est le scénario qui cumule le plus gros
import de données et le double registre FED.

## Impact du scénario S3 sur les findings de l'audit

| Finding | Devenir en S3 |
|---|---|
| B3 FED indécoupable | Résolu par design (bascule en bloc à la fin) |
| B4 sémantique import | Réduit aux assets locaux + bascule FED finale (table DRIFT §8.1 toujours nécessaire) |
| B5 reconcile_tokens | Réglé (passage en prod nuit du 10-11/06) — vérifier drift=0 après |
| B6 autonomie wallet | Reporté à l'extinction finale |
| B7 instance .re | Repoussé à la bascule FED finale (les places .re gardent le FED legacy) |
| B1, B2, B8, B9, M1-M9 | Inchangés — à corriger avant/pendant le portage |
| Gap fonctionnel (badge, QR pay, refund, rewards) | Inchangé pour les flux V2 ; refund/recharge FED restent legacy pour tous (plus simple qu'en S1/S2) |
