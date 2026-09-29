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
| **Relecteur** | Fable (sous-agent) | relit le diff d'une fiche entière + CHANGELOG + sorties de tests ; aussi à la fin de la fiche A ; vérifie la **conformité djc / `GUIDELINES.md`** au même rang que la conformité à la fiche | corriger |

**Lisibilité** : le skill `djc` et `GUIDELINES.md` s'appliquent à tout code et test du
chantier (commun numérique). Chaque agent qui écrit ou relit du code les charge **avant**
de commencer ; l'orchestrateur relit le `git diff` avec ces règles avant de déclarer une
session verte.
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
             À LA MAIN : Edit de la mutation → `make test ARGS=...` → Edit inverse →
             `sha256sum` identique. Compter seulement `FAILED ` / `ERROR tests/`.
             Aucun script, pas de serveur à attendre (pytest seul).
6. OBSERVER  `git diff --stat` : chaque fichier touché est annoncé par la fiche.
             Sinon : arrêt, question au mainteneur.
7. CLORE     fin de session : fichier de tests de la fiche + tests de
             caractérisation. Fin de FICHE : `make test` complet ; `make e2e` en fin
             de B, G et H seulement. CHANGELOG, ligne §3 mise à jour, message de
             commit proposé au mainteneur.
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
| 04-F-1 | Anti-rejeu QR (autre session) | commité | | | | | |
| 05-0 | Menu des rapports (1 test) | commité | `FAILED tests/pytest/test_menu_rapports.py::test_menu_ventes_comptabilite_range_les_deux_rapports` — `AssertionError: La section Ventes & comptabilité doit lister le rapport en ligne puis le rapport caisse. Liens trouvés : ['/admin/comptabilite/cloturecaisse/', '/admin/BaseBillet/lignearticle/']` (1 failed) | 1 passed (+ 74 voisins) | 3/3 tuées, sha256 identique | `CHANGELOG/2026-09-29-montants-entiers-0-menu-rapports.md` | `d36c0c1e` |
| 05-A′-1 | Caractérisation en ligne (7 tests + `etat_metier`, 5 mutations) | prêt à committer | vert attendu (pas de rouge) | 7 passed (×3) | 5/5 tuées, sha256 identiques | `CHANGELOG/2026-09-29-montants-entiers-A2-caracterisation.md` | |
| 05-A′-2 | Caractérisation annulations (5 tests, 2 mutations) | prêt à committer | vert attendu | 5 passed (12 avec A′-1, ×3) | 2/2 tuées, sha256 identiques | idem A′-1 | |
| 05-A′-3 | Caractérisation admin / API (4 tests, 2 mutations) | prêt à committer | vert attendu | 4 passed (16 avec A′-1/2, ×3) | 2/2 tuées, sha256 identiques | idem A′-1 | |
| 05-A′-4 | Caractérisation caisse + QR (4 + 2 tests, 3 mutations) | prêt à committer | vert attendu | 6 passed (22 au total, ×3) | 3/3 tuées, sha256 identiques | idem A′-1 | |
| 05-A′-5 | Corrections relecture Fable (billet offert caisse par la vraie route ; docstrings) | prêt à committer | vert attendu | 22 passed (×3) | aucune mutation de production (mutation côté test `edit_mode=False` → 400, test tombe) | idem A′-1 | |
| 05-A | Vente, Reglement, contraintes, service, empreinte | à faire | | | | | |
| 05-A-relu | Relecture Fable de A | à faire | | | | | |
| 05-B-0 | Caisse : effets d'adhésion communs (fonction partagée avec `trigger_A`) | à faire |
| 05-B-1 | Caisse : un moyen, recharges, consigne reliée | à faire | | | | | |
| 05-B-2 | Caisse : cascade, jetons, legacy | à faire | | | | | |
| 05-B-3 | Caisse : tables, vider carte, correction | à faire | | | | | |
| 05-C | Tireuse, QR/NFC (réseau d'abord) | à faire (après 04-F-1) | | | | | |
| 05-D-1 | Stripe : une vente par paiement, écart | à faire | | | | | |
| 05-D-2 | Ventes sans Stripe, recharge API v2 | à faire | | | | | |
| 05-D-3 | Avoirs, « Remboursé par » | à faire | | | | | |
| 05-E | Plan comptable unique | à faire (parallélisable avec B) | | | | | |
| 05-F-1 | Rapport unique | à faire | | | | | |
| 05-F-2 | Clôture unique (fin de service, filet fermeture + 2 h) | à faire | | | | | |
| 05-F-3 | FEC / CSV équilibrés | à faire | | | | | |
| 05-G-1 | Clôture caisse, gardes, archive, intégrité | à faire | | | | | |
| 05-G-2 | Écrans et tickets caisse | à faire | | | | | |
| 05-G-3 | Admin Vente, totaux, exports, API | à faire | | | | | |
| 05-H-1 | Une ligne par article, D15 | à faire | | | | | |
| 05-H-2 | Retrait champs et ancienne clôture | à faire | | | | | |
| 05-H-3 | Démo, fixtures, tests existants | à faire |
| 05-H-4 | Mails vérifiés de bout en bout (Mailpit, E2E) — dernière session | à faire | | | | | |

## 4. Écarts à la spec décidés en cours de route

Tout écart est **écrit ici avant d'être codé**, avec qui l'a décidé. Si l'écart change
une décision D ou un choix R, la fiche et le tronc sont corrigés dans la même étape.

| Date | Session | Écart | Raison | Décidé par |
|---|---|---|---|---|
| 2026-09-29 | B-0 (nouvelle) | Adhésion caisse V2 : facture par mail et récompense en monnaie, par une fonction commune avec `trigger_A` (pas via la machine à états) ; pas d'envoi legacy. Session séparée en tête de B. Test A′-4 `…sans_facture…` ajouté à la liste fermée A′ §4 (change en B-0). Fiches B, A′, annexe §6.3 corrigées. | Même logique métier en ligne et en caisse, un seul code. | mainteneur |
| 2026-09-29 | C (nouveau) | **Envoi à l'ancien LaBoutik débranché pour le paiement QR / NFC** (personne ne s'en sert). Fiche C §2-§4 (test 11 réécrit), fiche G (T10, test 18b retiré), fiche A′ §4 (test QR change en C), annexe §6.3-§6.4 corrigées. Résout la contradiction G / H sur la charge utile QR (relecture Fable A′, constat 2). | Simplification ; plus de charge utile « en parts » à préserver. | mainteneur |
| 2026-09-29 | A′-1, A′-3 | Adaptations au code (pas de changement de sens) : P2 ajoute une réservation gratuite au panier (seule une réservation sans ligne passe par la `Commande` : sinon la mutation `set_ligne_article_paid` est invisible) ; T13 posé par `update()` (don et `error_in_mail` n'y mènent plus) ; P16 passe par le vrai POST admin au lieu de `vente_admin_especes` (qui simule elle-même les tâches). | Rendre les tests atteignables et les mutations visibles. | orchestrateur (adaptation, pas de décision D/R) |
| 2026-09-29 | A′-2 | Test `test_annuler_reservation_caisse_payee_en_cascade_avoir_sur_la_part_rattachee` retiré : A′ = 22 tests. | Parcours inexistant : la cascade caisse ne crée ni réservation ni billet. | mainteneur |

## 5. En attente du mainteneur

| Date | Question | Contexte (fichier:ligne, sortie) | Réponse |
|---|---|---|---|
| 2026-09-28 | Valider D8 (règlement « offert » de trace) et R1-R6 | tronc §4.2, §4.4 | **Validé (2026-09-29)** : D8 (trace des jetons et d'OFFRIR) et R1-R6. |
| 2026-09-28 | Avoir émis dans l'admin sur un achat payé par Stripe : **vrai remboursement Stripe** (nouveau mouvement d'argent) ou seulement l'enregistrement « Remboursé par » ? Défaut écrit : vrai remboursement par `partial_refund_payment`, test mocké | fiche D §4 (ligne « Avoir émis dans l'admin, ligne payée par Stripe », test 18b) ; aujourd'hui `emettre_avoir` n'appelle pas Stripe (`Administration/admin_tenant.py` ~l.2082-2099) | **Tranché (D27)** : comportement actuel gardé, aucun appel Stripe, l'admin est prévenu. |
| 2026-09-28 | **T8** : la règle de la ligne précédente (remboursement Stripe automatique ou non) vaut-elle aussi pour l'**annulation d'adhésion** payée par Stripe ? Défaut écrit : même règle pour les deux écrans | annexe machine à états T8 ; `BaseBillet/views.py` ~l.4593 | **Tranché (D27)** : même règle (pas d'appel Stripe) pour l'annulation d'adhésion. |
| 2026-09-28 | **T7** (question métier) : annuler une adhésion crée aujourd'hui un avoir pour l'achat **et tous les renouvellements** passés. Est-ce voulu ? Défaut écrit : comportement gardé, une vente `AVOIR` par vente d'origine | annexe T7 ; `BaseBillet/views.py` ~l.4595-4602 | **Tranché (D30), précisé le 2026-09-29** : un seul avoir, sur le **dernier** paiement (période en cours) ; les années passées ne sont pas touchées. |
| 2026-09-28 | **T9** : annulation par l'utilisateur d'une réservation / booking payé hors Stripe (pas d'écran « Remboursé par ») : quel moyen ? Défaut écrit : moyen d'origine si espèces / CB / chèque / virement, sinon « inconnu » (compte d'attente 471) + alerte | annexe T9 ; fiche D | **Tranché (D31)** : pas de remboursement hors Stripe, donc aucun avoir. |
| 2026-09-28 | **T11** : le Z automatique de 4 h doit-il, comme le bouton, annuler les commandes de table ouvertes et libérer les tables ? Défaut écrit : non (comme l'auto-clôture actuelle) | annexe T11 ; `laboutik/views.py` ~l.2727-2737 ; fiche G | **Tranché (D29)** : non. |
| 2026-09-28 | **T12** : billet offert vendu dans l'admin écrit `amount = 0` (pas de trace de l'offert). Garder, ou passer au prix + part offerte en H ? Défaut écrit : garder | annexe T12 ; `Administration/admin_tenant.py` ~l.3092 | **Tranché (D32)** : billet gardé, écrit comme un offert de la caisse (origine admin). |
| 2026-09-28 | **T13** (bug actuel, hors chantier) : un rejeu `PAID → PAID` repasse les avoirs en `PAID`. Figé par un test A′. Corriger dans un autre chantier ? | annexe T13 ; `BaseBillet/signals.py` ~l.42 | **Tranché (D33)** : bug à corriger dans un autre chantier. |
| 2026-09-28 | J de fin de service à cheval sur minuit ou sur deux mois : à quelle date / quel mois va son écriture FEC ? Défaut écrit : datée du jour de début de service ; le rapport M compte chaque vente à sa date d'encaissement ; l'écart aux bords de mois est écrit dans le rapport M ; le FEC fait foi par J. Filet de 4 h en heure locale du lieu (tâche horaire, `TiBillet/celery.py`) | fiche F §3.1 et §4, tests 15b et 25b | **Tranché** : filet = heure de fermeture + 2 h (D28). **Validé (2026-09-29)** : écriture FEC datée du jour de début du service. |
| 2026-09-28 | `Reservation.total_paid()` lit `total_ttc` (fiche G) : un billet **entièrement offert** (FREE à prix non nul, caisse ou admin D32) n'a plus rien à rembourser → son annulation ne crée plus d'avoir d'argent, seule la trace `FREE −X` (fiche D). Le test A′ `test_annuler_un_billet_caisse_offert_cree_un_avoir` change en G. **Défaut écrit : oui** (plus d'avoir d'argent) | fiche G §4, A′ §4, machine à états §0.4 | **Validé (2026-09-29)** : pas d'avoir d'argent pour un billet offert, seulement la trace de l'offert annulé. |
| 2026-09-28 | Traductions ajustées à la relecture finale, sans changer le fond des décisions : D10 (pas de nature `RECHARGE` : le rapport lit `hors_chiffre_affaires` ; recharge cadeau en `source_offert = OFFRIR`, plus de valeur `CADEAU`) ; D16 (`EXPIRE` laisse la vente `EN_ATTENTE`, plus de réouverture ; `ANNULEE` seulement sur `CANCELED` / SEPA refusé). **Défaut écrit : oui** | tronc D10, D16 ; fiche D §2.2, §3 ; fiche A §3 | **Validé (2026-09-29)** : D10 et D16 tels qu'écrits. |
| 2026-09-29 | Adhésion vendue en caisse V2 : pas d'envoi à l'ancien LaBoutik (figé par A′-4 `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik`) — voulu ? | annexe P9 ; `laboutik/views.py` `_creer_ou_renouveler_adhesion` | **Voulu (mainteneur, 2026-09-29)** : la caisse V2 ne parle pas à la caisse legacy. Facture par mail et récompense en monnaie : **« doivent fonctionner »** (2026-09-29) → aujourd'hui absentes = bug. **Tranché : session B-0** (fonction commune avec `trigger_A`). A′-4 fige l'actuel, B-0 le change. |
| 2026-09-29 | **A′-2, 6ᵉ test** `test_annuler_reservation_caisse_payee_en_cascade_avoir_sur_la_part_rattachee` : son parcours n'existe pas. Seuls les chemins caisse à un seul moyen créent réservation et billets (`_creer_billets_depuis_panier`, appelé l.7453 et l.7678) ; les chemins en cascade (`_payer_par_nfc` l.8457, complément l.9562, l.10147) ne rattachent que les adhésions. Le retirer (A′ = 22 tests ; fiche A′ §4 et fiche H à corriger), ou le remplacer ? | ouvrier A′-2 §4 A, vérifié par l'orchestrateur | **Retiré (mainteneur, 2026-09-29).** Fiche A′ §3-§4, annexe §6.2-§6.3, fiche H §T14 corrigées. |
| 2026-09-29 | **Billet vendu en caisse et payé en NFC / cascade** : d'après l'ouvrier, lignes créées mais **ni réservation ni billet**. Non vérifié à l'écran (une garde de l'interface peut l'empêcher). Bug à vérifier hors chantier ? | `laboutik/views.py` chemins cascade | **Hors chantier** (tronc §9). |
| 2026-09-29 | **Bug constaté (non figé)** : annuler **un seul** billet vendu en caisse échoue toujours (« Aucun paiement remboursable… ») : la ligne caisse porte un tarif vendu sans événement, le billet un tarif vendu avec événement ; `_lignes_hors_stripe(pricesold_ids=…)` ne trouve rien. Seule l'annulation de toute la réservation marche. Corriger hors chantier ? | `laboutik/views.py` l.5384, l.6554 ; `BaseBillet/models.py` l.3168 | **Hors chantier** (tronc §9). |
| 2026-09-29 | **Fiche G fausse** : dans `cancel_and_refund_resa`, la boucle des avoirs hors Stripe tourne quel que soit `total_paid()` : passer `total_paid` sur `total_ttc` ne suffira pas à supprimer l'avoir d'un billet offert. À corriger dans la fiche G avant de l'ouvrir (pas bloquant pour A′). | ouvrier A′-2 §4 C | |
| 2026-09-29 | « Payée ailleurs » (API v2, `paymentMethod` cash/card) : la réservation passe `CREATED → VALID`, transition absente de `PRE_SAVE_TRANSITIONS` → **aucun mail de billet**, alors que le commentaire `validators.py` ~l.458 dit le contraire. Bug hors chantier ? | `BaseBillet/validators.py` ~l.458 ; `BaseBillet/signals.py` | **Hors chantier** (tronc §9). |
| 2026-09-29 | P15 : un renouvellement d'abonnement envoie deux fois `webhook_membership`. Bug hors chantier ? | `triggers.py` l.137 puis `set_deadline` l.267 | **Hors chantier** (tronc §9). |
| 2026-09-29 | **Adhésion créée dans l'admin** : un mail de connexion (`connexion_celery_mailer`) part à l'adhérente si son adresse n'est pas confirmée — `MembershipAddForm.save()` appelle `get_or_create_user(email)` avec `send_mail=True` par défaut, alors que `clean_email` le fait avec `send_mail=False`. Voulu ou bug (hors chantier) ? Figé par A′-3. Même cause que P15 : deux `webhook_membership` à la création aussi. | `Administration/admin_tenant.py` l.1381, l.1438 | **Bug, hors chantier** (2026-09-29) → `TODO/BUGS-constats-chantier-05.md` (avec les autres bugs hors chantier). |
| 2026-09-29 | **Pour la fiche F (comptabilité légale)** : la clôture caisse actuelle est globale au lieu (numéro, tables, commandes de tous les points de vente), mais le **début de période** est cherché depuis la dernière clôture du **seul point de vente qui clôture**. Un point de vente qui n'a jamais clôturé repart de la première vente caisse du lieu. La clôture unique de F doit prendre le Z précédent **du lieu** (D28) : à vérifier explicitement dans F, pas de décision ici. | `laboutik/views.py` l.2601-2632 ; constat ouvrier A′-4 | à traiter à l'ouverture de F |

## 6. Journal

Une ligne par événement, la plus récente en haut. Format :
`AAAA-MM-JJ HH:MM — session — ce qui s'est passé (preuve : commande / fichier)`.

- 2026-09-29 — 05-A′ — `make test` complet après A′-5 : 2113 passed, 0 FAILED/ERROR. Fiche A′ prête à committer ; commit proposé au mainteneur.
- 2026-09-29 — 05-A′-5 — vert (22 passed, relancé). Billet offert caisse par `POST /laboutik/paiement/payer/` (`gift`, carte primaire mode gérant, PV billetterie caché, config en mémoire) : relu conforme djc. Docstrings corrigées (date retirée ; QR « change en C »). Puce CHANGELOG A′-2 corrigée par l'orchestrateur. Suite complète relancée.
- 2026-09-29 — 05-A′ — relecture Fable : 0 bloquant, 4 importants, 10 mineurs. Doc corrigée par l'orchestrateur : fiche D (réécriture T7 sans `payment_method=`, n°4), fiche A′ §5 (« payée ailleurs », n°12), SUIVI §4 (adaptations, n°13), 11 mutations / 12 jeux (n°14). n°2 → décision mainteneur : envoi legacy QR débranché en C (couvre aussi n°1). n°3 et n°9 → session A′-5 (tests). Mineurs 5-8, 10, 11 acceptés.
- 2026-09-29 — 05-A′ — `make test` complet : 2113 passed, 0 FAILED/ERROR. Relecture Fable lancée.
- 2026-09-29 — 05-A′-4 — vert (22 passed, relancé). Relecture djc des deux fichiers : conforme (mineur : P12 suppose une monnaie locale dans `lespass` en base de dev, sinon erreur, jamais faux vert). Mutations 3/3 tuées (`laboutik/views.py` ×2, `ApiBillet/serializers.py`), sha256 identiques (interruption : classifieur d'autorisation en panne, reprise après redémarrage de Claude Code). Constats : table servie non payée libérée à la clôture (figé) ; début de période de clôture par point de vente (→ §5, fiche F). **Fiche A′ : 22 tests, 12 mutations jouées, toutes tuées.** Suite complète lancée.
- 2026-09-29 — TODO — `TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md` créé (6 bugs hors chantier, mail de connexion admin compris) + ligne dans `TODO/INDEX.md`.
- 2026-09-29 — 05-A′-4 — brief `05-A2-4.md` écrit ; ouvrier Opus lancé.
- 2026-09-29 — 05-A′-3 — vert (16 passed, relancé). Relecture djc conforme (mineurs acceptés : T21 enchaîne 4 parcours sous un nom de contrat ; 2 assistants de lecture recopiés d'A′-2). Écarts figés depuis le code : mail de connexion à l'adhésion admin, 2 webhooks, réservation payante `U`. Mutations 2/2 tuées (`triggers.py`, `api_v2/views.py`), sha256 identiques.
- 2026-09-29 — H-4 — ajoutée (mainteneur) : mails vérifiés par Mailpit en E2E, dernière session du chantier ; test `mailoutbox` validé en B-0.
- 2026-09-29 — B-0 — validée par le mainteneur : effets d'adhésion communs caisse / en ligne par une fonction explicite ; session écrite dans la fiche B §2 bis. A′-4 débloquée.
- 2026-09-29 — 05-A′-3 — brief `05-A2-3.md` écrit ; ouvrier Opus lancé.
- 2026-09-29 — 05-A′-2 — décisions mainteneur : 6ᵉ test retiré (écart §4, spec corrigée) ; 4 bugs hors chantier (tronc §9) ; adhésion caisse V2 : facture et récompense « doivent fonctionner » → question ouverte, bloque A′-4. A′-2 : mutations OK.
- 2026-09-29 — 05-A′-2 — 5 tests sur 6 (12 passed avec A′-1). Relecture djc : conforme. Mutations 2/2 tuées (`PaiementStripe/utils.py` l.38, `BaseBillet/views.py` `break` après l.4687), sha256 identiques. 6ᵉ test non écrit : parcours inexistant (vérifié) → question §5, **A′-2 bloquée**. Autres constats ajoutés au §5.
- 2026-09-29 — 05-A′-2 — brief `05-A2-2.md` écrit (imite A′-1, importe `etat_metier`, ne modifie pas le fichier A′-1) ; ouvrier Opus lancé.
- 2026-09-29 — 05-A′-1 — vert (7 passed, relancé par l'orchestrateur). Relecture djc ligne à ligne : conforme (noms verbeux, docstrings FR/EN au présent, `for` simples, attendus en clair, aucun champ retiré en H lu sur la ligne). Écarts ouvrier acceptés (adaptation au code, rien d'inventé) : réservation gratuite ajoutée au panier P2 pour que la mutation `set_ligne_article_paid` soit visible ; état de départ T13 posé par `update()` (don et `error_in_mail` n'y mènent plus) ; `etat_metier(reservations=[...])`. Surprenants figés : T13, P15 double `webhook_membership`, T1, T5. Mutations 5/5 tuées (`triggers.py`, `signals.py`, `ApiBillet/views.py`), sha256 identiques. Aucun fichier de production modifié.
- 2026-09-29 — 05-A′ — 05-0 commité (`d36c0c1e`). A′ découpée en 4 sessions (fiche : une par fichier, QR avec caisse). Outillage et points de mutation de l'annexe §6 vérifiés présents dans le code. Brief `05-A2-1.md` écrit (règle de lisibilité djc en 2ᵉ position) ; ouvrier Opus lancé.
- 2026-09-29 — méthode — à la demande du mainteneur : djc + `GUIDELINES.md` rendus obligatoires pour tout agent qui écrit ou relit du code (PROMPT-ORCHESTRATEUR : règle non négociable, lecture au démarrage, critère du relecteur, étape OBSERVER ; MODELE : « Règle de lisibilité » juste après la règle git + auto-contrôle djc dans le rapport ; SUIVI §1). 05-0 : conformité djc vérifiée par le relecteur Fable (critère 5 de son prompt) ; l'ouvrier ne l'avait que par une ligne du brief.
- 2026-09-29 — 05-0 — relu par Fable : 0 bloquant, 0 important, 5 mineurs. Corrigés par l'orchestrateur dans le CHANGELOG : libellé affiché « Ventes et comptabilité », fil d'Ariane de la liste des clôtures caisse (retombe sur le défaut Unfold, comme les autres entrées autonomes). Laissés : lignes `laboutik.cloturecaisse` des dictionnaires d'aide devenues sans effet (question au mainteneur), docstring du test au passé (style toléré), `db` + `django_db` redondants (sans effet). Commit proposé au mainteneur.
- 2026-09-29 — 05-0 — `make test` complet : 2091 passed, 0 FAILED/ERROR. Vérification visuelle Chrome non faite (extension non connectée) : laissée au mainteneur (CHANGELOG « Comment tester »). Relecture Fable lancée.
- 2026-09-29 — 05-0 — vert : `make test ARGS="tests/pytest/test_menu_rapports.py + 4 voisins navigation"` 75 passed. Mutations à la main sur `Administration/admin/dashboard.py` (append→insert(0) ; « Closures » remise dans la section caisse ; `if True:`) : 3/3 tuées, sha256 `718a27ab…` identique. `git diff --stat` : seuls `dashboard.py` + test + CHANGELOG + SUIVI/brief. Caractérisation : aucun fichier encore (A′ pas faite). Suite complète lancée.
- 2026-09-29 — 05-0 — rouge prouvé par l'orchestrateur (`make test ARGS="tests/pytest/test_menu_rapports.py"` : 1 failed). Constat ouvrier : `DESCRIPTION_DES_PAGES` / `CATEGORIE_DES_PAGES` ne servent qu'aux pages de module (sections à `_slug`) ; « Ventes & comptabilité » n'en a pas → « Le bilan de chaque journée. » ne s'affichera plus nulle part. Pas un écart : la fiche dit « suit l'entrée », on déplace les deux lignes, textes inchangés. Feu vert étape 2.
- 2026-09-29 — 05-0 — fiche vérifiée face au code (`Administration/admin/dashboard.py` l.419, l.473-480, l.827-852, l.1289, l.1360 : concorde) ; brief `CHANTIER-05-briefs/05-0.md` écrit ; ouvrier Opus lancé (étape 1 : test seul).
- 2026-09-29 — spec — toutes les questions du §5 tranchées avec le mainteneur (D8, R1-R6, T7 précisé, billet offert annulé, date FEC, D10/D16). Spec prête ; plus aucune question ouverte.
- 2026-09-28 — spec — relecture finale Fable appliquée (coupes §A, constats 1-24) : ordre 0, A′, A ; mutations à la main ; suite complète par fiche ; ~30 j.
- 2026-09-28 — spec — relecture finale Opus (5 bloquants, 23 importants, 11 mineurs) appliquée.
- 2026-09-28 — spec — décisions du mainteneur D27 (gardé), D28 (fermeture + 2 h), D29-D33 appliquées dans le tronc, D, F, G, A′.
- 2026-09-28 — spec — audit de la machine à états (annexe, trous T1-T22 dont 3 bloquants) reporté dans A, B, C, D, G, H ; fiche A′ (caractérisation) créée ; décisions T7-T9, T11-T13 en attente (§5).
- 2026-09-28 — spec — spec rédigée, relue Fable + Opus, corrigée ; décisions D26-D28 ; relecture finale Opus lancée.

## 7. État des suites

| Date | `make test` | `make e2e` | Remarque |
|---|---|---|---|
| 2026-09-29 | 2113 passed (0 FAILED / ERROR) | — | fin de fiche 05-A′ après A′-5 (relancé) |
| 2026-09-29 | 2113 passed (0 FAILED / ERROR) | — | fin de fiche 05-A′ (+22 tests de caractérisation) |
| 2026-09-29 | 2091 passed (0 FAILED / ERROR) | — | fin de fiche 05-0 (e2e pas exigé en 0) |
| 2026-09-28 | 2082 passed | 116 passed | départ (après chantier 04 A-E) |

## 8. Pièges rencontrés pendant le chantier

(à reporter ensuite dans `tests/PIEGES.md` par le mainteneur)

- 2026-09-29 (A′-1) — Mutation : un seul `curl` 200 juste après l'Edit ne suffit pas, le serveur byobu n'a pas encore commencé à recharger → `make test` sort en 502 sans lancer pytest (sortie vide, faux « survit »). Attendre **3 réponses 200 d'affilée** (1 s d'écart) avant `make test`, et vérifier qu'une ligne `passed`/`failed` sort.
