# Chantier 05 — Suivi (la mémoire du chantier)

> **Ce fichier est la mémoire durable du chantier.** Les sessions sont jetables : une
> session d'orchestration qui s'arrête repart d'ici, pas de son contexte.
> Il est tenu **uniquement par l'orchestrateur**, mis à jour **à chaque étape** (pas en
> fin de journée). Un message est une impulsion, un fichier est un contrat.
>
> Spec : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) (tronc) +
> fiches `CHANTIER-05-0` à `H`. Briefs : [`CHANTIER-05-briefs/`](CHANTIER-05-briefs/).

## 1. Rôles

| Rôle | Modèle | Fait | Ne fait jamais |
|---|---|---|---|
| **Orchestrateur** | Opus (session principale) | écrit les briefs, prouve le rouge, délègue, relance tests et mutations lui-même, lit `git diff`, tient ce fichier, prépare le commit | écrire du code de production ou de test |
| **Ouvrier** | Opus (sous-agent), Sonnet pour le mécanique | exécute **un** brief, s'arrête à la fin du brief, rapporte | git (sauf lecture), toucher hors du périmètre du brief, décider un écart à la spec |
| **Relecteur** | Fable (sous-agent) | relit le diff d'une fiche entière + CHANGELOG + sorties de tests ; aussi à la fin de la fiche A | corriger |
| **Mainteneur** | humain | tranche les écarts, valide, **commite** (jamais de Co-Authored-By) | — |

Git : lecture seule autorisée (`status`, `diff`, `log`, `show`). Interdit sans accord
explicite : `commit`, `add`, et toute commande destructive (`checkout --`, `restore`,
`stash`, `reset`, `clean`).

## 2. La boucle, pour chaque session de fiche

```
1. LIRE      la fiche (sections du brief) + ce fichier (§4 écarts, §5 en attente)
2. BRIEF     écrire CHANTIER-05-briefs/<session>.md (modèle : MODELE.md)
3. ROUGE     l'ouvrier écrit les tests ; l'orchestrateur les LANCE LUI-MÊME et colle
             la sortie d'échec ici (§3). Déjà vert = le test ne prouve rien → on
             revoit le test avant tout code.
4. DÉLÉGUER  l'ouvrier écrit le code (un seul ouvrier à la fois, sauf E en parallèle)
5. PROUVER   l'orchestrateur relance `make test ARGS=...` puis les mutations
             (script muter.py : attendre un 200, compter seulement `FAILED ` /
             `ERROR tests/`, restaurer, sha256 identique)
6. OBSERVER  `git diff --stat` : chaque fichier touché est annoncé par la fiche.
             Sinon : arrêt, question au mainteneur.
7. CLORE     suite complète (`make test`, `make e2e` si caisse/admin), CHANGELOG,
             ligne §3 mise à jour, message de commit proposé au mainteneur.
8. RELIRE    fin de fiche (et fin de A) : relecteur Fable ; constats traités
             comme une nouvelle session (retour en 2).
```

Un ouvrier ne s'arrête **jamais au milieu d'un brief** : un brief trop gros se coupe
avant d'être délégué, pas pendant.

## 3. Tableau de bord

Statuts : `à faire` · `brief écrit` · `rouge prouvé` · `vert` · `mutations OK` ·
`relu` · `prêt à committer` · `commité (hash)`.

| Session | Sujet | Statut | Rouge (preuve) | Vert | Mutations | CHANGELOG | Commit |
|---|---|---|---|---|---|---|---|
| 04-F-1 | Anti-rejeu QR (autre session) | livré, non commité (vérifier le commit avant 05-C) | | | | | |
| 05-0 | Menu des rapports | à faire | | | | | |
| 05-A | Vente, Reglement, service, empreinte | à faire | | | | | |
| 05-A-relu | Relecture Fable de A | à faire | | | | | |
| 05-A′ | Tests de caractérisation (5 fichiers, 11 mutations) — avant B | à faire | vert attendu (pas de rouge) | | | | |
| 05-B-1 | Caisse : un moyen, recharges, consigne reliée | à faire | | | | | |
| 05-B-2 | Caisse : cascade, jetons, legacy | à faire | | | | | |
| 05-B-3 | Caisse : tables, vider carte, correction | à faire | | | | | |
| 05-C | Tireuse, QR/NFC (réseau d'abord) | à faire (après 04-F-1) | | | | | |
| 05-D-1 | Stripe : une vente par paiement, écart | à faire | | | | | |
| 05-D-2 | Ventes sans Stripe, recharge API v2 | à faire | | | | | |
| 05-D-3 | Avoirs, « Remboursé par » | à faire | | | | | |
| 05-E | Plan comptable unique | à faire (parallélisable avec B) | | | | | |
| 05-F-1 | Rapport unique | à faire | | | | | |
| 05-F-2 | Clôture unique (fin de service + 4 h) | à faire | | | | | |
| 05-F-3 | FEC / CSV équilibrés | à faire | | | | | |
| 05-G-1 | Clôture caisse, gardes, archive, intégrité | à faire | | | | | |
| 05-G-2 | Écrans et tickets caisse | à faire | | | | | |
| 05-G-3 | Admin Vente, totaux, exports, API | à faire | | | | | |
| 05-H-1 | Une ligne par article, D15 | à faire | | | | | |
| 05-H-2 | Retrait champs et ancienne clôture | à faire | | | | | |
| 05-H-3 | Démo, fixtures, tests existants | à faire | | | | | |

## 4. Écarts à la spec décidés en cours de route

Tout écart est **écrit ici avant d'être codé**, avec qui l'a décidé. Si l'écart change
une décision D ou un choix R, la fiche et le tronc sont corrigés dans la même étape.

| Date | Session | Écart | Raison | Décidé par |
|---|---|---|---|---|

## 5. En attente du mainteneur

| Date | Question | Contexte (fichier:ligne, sortie) | Réponse |
|---|---|---|---|
| 2026-09-28 | Valider D8 (règlement « offert » de trace) et R1-R6 | tronc §4.2, §4.4 | |
| 2026-09-28 | Avoir émis dans l'admin sur un achat payé par Stripe : **vrai remboursement Stripe** (nouveau mouvement d'argent) ou seulement l'enregistrement « Remboursé par » ? Défaut écrit : vrai remboursement par `partial_refund_payment`, test mocké | fiche D §4 (ligne « Avoir émis dans l'admin, ligne payée par Stripe », test 18b) ; aujourd'hui `emettre_avoir` n'appelle pas Stripe (`Administration/admin_tenant.py` ~l.2082-2099) | |
| 2026-09-28 | **T8** : la règle de la ligne précédente (remboursement Stripe automatique ou non) vaut-elle aussi pour l'**annulation d'adhésion** payée par Stripe ? Défaut écrit : même règle pour les deux écrans | annexe machine à états T8 ; `BaseBillet/views.py` ~l.4593 | |
| 2026-09-28 | **T7** (question métier) : annuler une adhésion crée aujourd'hui un avoir pour l'achat **et tous les renouvellements** passés. Est-ce voulu ? Défaut écrit : comportement gardé, une vente `AVOIR` par vente d'origine | annexe T7 ; `BaseBillet/views.py` ~l.4595-4602 | |
| 2026-09-28 | **T9** : annulation par l'utilisateur d'une réservation / booking payé hors Stripe (pas d'écran « Remboursé par ») : quel moyen ? Défaut écrit : moyen d'origine si espèces / CB / chèque / virement, sinon « inconnu » (compte d'attente 471) + alerte | annexe T9 ; fiche D | |
| 2026-09-28 | **T11** : le Z automatique de 4 h doit-il, comme le bouton, annuler les commandes de table ouvertes et libérer les tables ? Défaut écrit : non (comme l'auto-clôture actuelle) | annexe T11 ; `laboutik/views.py` ~l.2727-2737 ; fiche G | |
| 2026-09-28 | **T12** : billet offert vendu dans l'admin écrit `amount = 0` (pas de trace de l'offert). Garder, ou passer au prix + part offerte en H ? Défaut écrit : garder | annexe T12 ; `Administration/admin_tenant.py` ~l.3092 | |
| 2026-09-28 | **T13** (bug actuel, hors chantier) : un rejeu `PAID → PAID` repasse les avoirs en `PAID`. Figé par un test A′. Corriger dans un autre chantier ? | annexe T13 ; `BaseBillet/signals.py` ~l.42 | |
| 2026-09-28 | J de fin de service à cheval sur minuit ou sur deux mois : à quelle date / quel mois va son écriture FEC ? Défaut écrit : datée du jour de début de service ; le rapport M compte chaque vente à sa date d'encaissement ; l'écart aux bords de mois est écrit dans le rapport M ; le FEC fait foi par J. Filet de 4 h en heure locale du lieu (tâche horaire, `TiBillet/celery.py`) | fiche F §3.1 et §4, tests 15b et 25b | |

## 6. Journal

Une ligne par événement, la plus récente en haut. Format :
`AAAA-MM-JJ HH:MM — session — ce qui s'est passé (preuve : commande / fichier)`.

- 2026-09-28 — spec — relecture finale Opus (5 bloquants, 23 importants, 11 mineurs) appliquée.
- 2026-09-28 — spec — audit de la machine à états (annexe, trous T1-T22 dont 3 bloquants) reporté dans A, B, C, D, G, H ; fiche A′ (caractérisation) créée ; décisions T7-T9, T11-T13 en attente (§5).
- 2026-09-28 — spec — spec rédigée, relue Fable + Opus, corrigée ; décisions D26-D28 ; relecture finale Opus lancée.

## 7. État des suites

| Date | `make test` | `make e2e` | Remarque |
|---|---|---|---|
| 2026-09-28 | 2082 passed | 116 passed | départ (après chantier 04 A-E) |

## 8. Pièges rencontrés pendant le chantier

(à reporter ensuite dans `tests/PIEGES.md` par le mainteneur)
