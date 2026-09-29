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
| 05-A-1 | Formule d'argent, modèles, migrations, marqueur TVA, T1 | prêt à committer | `test_montants_article.py` : `ModuleNotFoundError: No module named 'BaseBillet.services_vente'` (collecte) ; `test_vente_modeles.py` : 5 failed, 1 passed (`tva_zero` : `Decimal('20.00') == Decimal('0.00')` ; `models_vente` absent ×2 ; `Paiement_stripe` sans `moyen` ×2) — `create_sans_vat` vert par construction (non-régression) | 19 passed + 22 caractérisation | 12/12 tuées (9 code dont SR, 3 contraintes en base), sha256 et témoin identiques | `CHANGELOG/2026-09-29-montants-entiers-A-vente-reglement.md` | |
| 05-A-2 | Service de vente, fabrique, `verifier_egalites`, garde d'immutabilité | prêt à committer | `test_vente_service.py` : `ImportError: cannot import name 'EgaliteDeVenteRompue'` (collecte, 16 tests) ; `test_vente_modeles.py` : `tva_zero` `ImportError: cannot import name 'ajouter_article'` (1 failed, 7 passed) | 22 + 8 + 11 (A-1/A-2) + 22 caractérisation = 63 passed | 17/17 tuées (M2 d'abord survivante → test ajouté → tuée), sha256 identiques | idem A-1 | |
| 05-A-3 | Empreinte chaînée, `verifier_chaine_ventes`, altérations, concurrence | prêt à committer | `ImportError: cannot import name 'calculer_hmac_vente'` ; contre un service vide (plugin jetable hors dépôt) : 5 failed, 22 passed | 27 + 8 + 11 + 22 = 68 passed ; script de concurrence OK | 7/8 tuées (3 clés du message, `previous_hmac`, numérotation, ordre du statut, `atomic`) ; `select_for_update` survit (redondant avec le verrou, documenté) ; sha256 identiques | idem A-1 | |
| 05-A-4 | Corrections relecture Fable : types (float refusé, garde normalisée), `choices`, djc | prêt à committer | 6 failed, 40 passed : 3 « DID NOT RAISE » (`float` : quantité, quantité pour coût, TVA) ; 9 centimes non entiers acceptés ; faux refus de la garde sur `qty` (28 décimales contre 6) ; 3 valeurs hors choix acceptées | 54 passed (17 + 8 + 29) + 22 caractérisation | 6/6 tuées, sha256 identiques | idem A-1 | |
| 05-A-relu | Relecture Fable de A | fait : 0 bloquant, 2 importants, 9 mineurs → A-4 (corrigés) | | | | | |
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
| 2026-09-29 | A-3 | Fiche §4 corrigée : `statut = REGLEE` posé **avant** le calcul de l'empreinte (le statut fait partie du message). `select_for_update` gardé bien que redondant avec le verrou pour l'encaissement (mutation survivante, documentée). | Ordre littéral de la fiche impossible (aucune vente ne se vérifierait). | orchestrateur (technique) |
| 2026-09-29 | A-3 | Fixé au rouge : anomalie = `{numero, uuid, raison}` (raison FR avec « empreinte fausse » / « maillon cassé » / « trou de numéro » / « égalité rompue ») ; trou signalé sur la vente qui suit ; cas « `total_ttc` altéré » fait par un faux offert cohérent (les contraintes de base refusent `total_ttc` seul) ; test ajouté `test_empreinte_precedente_modifiee_signale_un_maillon_casse` ; (règle « début de chaîne au n° 1 » **retirée** : chaîne simple, décision du mainteneur) ; clé encodée comme `calculer_hmac` (UTF-8, `hexdigest`). | Fiche muette ; sans ces tests, « maillon cassé » et le début de chaîne ne seraient vus par aucun test. | orchestrateur (technique) |
| 2026-09-29 | A-2 | Ajouts après le vert (constats de l'ouvrier) : `ajouter_article` / `ajouter_reglement` refusent une vente non `EN_ATTENTE` (D14 : une vente encaissée ne se modifie plus) ; `ajouter_article` recopie `vente.origine` dans `sale_origin` sauf valeur passée par le producteur ; `annuler_vente` testée (vente réglée refusée, vente annulée rendue telle quelle). Garde de `LigneArticle.save()` gardée telle quelle (une requête par clé à chaque modification : négligeable, et elle ne peut pas être contournée en vidant `vente` en mémoire). | Trous du service : une mutation survivrait, ou une vente réglée pourrait être complétée. | orchestrateur (technique, dans la ligne de D14) |
| 2026-09-29 | A-2 | Fixé au rouge : refus par `ValueError` (sauf égalités : `EgaliteDeVenteRompue`, message avec les deux sommes) ; TVA ≠ 0 sur une vente en points refusée dans `ajouter_article` ; garde d'immutabilité des trois modèles **une fois la vente `REGLEE`** (lecture de la phrase de la fiche §2) ; `verifier_egalites` compare aussi `Vente.total_ht` à Σ HT des lignes (jamais à un HT recalculé). Tests ajoutés : `test_hors_chiffre_affaires_calcule_depuis_le_produit_ou_force` (sinon la liste RE/RC/TM/VR/FD/R n'est vue par aucun test), `test_vente_sans_article_refusee_sauf_vidage_et_correction`, `test_ouvrir_vente_meme_cle_rend_la_meme_vente` (règles du §3-§4 sans test : une mutation survivrait). | Fiche muette sur ces points. | orchestrateur (technique) |
| 2026-09-29 | A-2 | `hors_chiffre_affaires` : calculé par `ajouter_article` depuis le produit (`RE`, `RC`, `TM`, `VR`, `FD`, `RECHARGE_CASHLESS`) **ou** forcé à `True` par le paramètre (écart d'encaissement, fiche D). Empreinte repoussée en A-3 (`encaisser_vente` laisse un TODO). | Fiche ambiguë (signature avec paramètre + liste figée). | orchestrateur (technique) |
| 2026-09-29 | A-1 | `PaiementStripe/views.py` ajouté au périmètre de la fiche A (pose `Paiement_stripe.moyen = SR` à la création du paiement d'une échéance), avec un cas `SR` au test T1. | Seul endroit où `SR` part dans l'INSERT sans relancer la machine à états. | mainteneur |
| 2026-09-29 | A-1 | Détails fixés au rouge : fiche §7, mutation `ROUND_HALF_EVEN` vue seulement par « net 111 » (451,5 → 452 est pair) ; second cas du montant imposé (1000 × 0,333333, imposé 334 → 334/278/56) sinon le test ne prouve rien ; `ValueError` si offert hors bornes ; `Vente.Nature` / `Vente.Statut` imbriqués ; `Paiement_stripe.moyen` : `SP` si SEPA, sinon `SN`, posé par `update_checkout_status`, `SR` par la facture d'abonnement (cas carte ajouté au test T1). | Fiche muette ou fausse sur ces points. | orchestrateur (technique) |
| 2026-09-29 | A-1 | 2ᵉ `CheckConstraint` de `LigneArticle` conditionnelle : `vente IS NULL OR total_ht + total_tva = total_ttc` jusqu'à H (qui rend `vente` obligatoire). Tests de modèles dans `test_vente_modeles.py` (base partagée), en plus des deux fichiers de la fiche. | 25 lignes de `lespass` (dev) ont `total_ht ≠ 0` (chantier 04-B) avec `total_ttc = 0` : la contrainte inconditionnelle ferait échouer la migration. | orchestrateur (technique, pas de D/R) |
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
| 2026-09-29 | Fiche A : `VR` (« Virement pot central ») et `FD` (« Fidélité », inutilisé) hors chiffre d'affaires ? | fiche A §2 ; `BaseBillet/services_refund.py` l.74 | **Oui, hors CA, mais visibles** (mainteneur) : ils restent dans le Z et le FEC. |
| 2026-09-29 | **Pour la fiche E** : quel compte pour `VR` (virement du pot central : 467 réseau ? 512 ?) et `FD` ? La fiche E ne les couvre pas (`compte_pour_article` : recharges → 4191 seulement). | fiche E §3 ; décision A ci-dessus | à trancher à l'ouverture de E |
| 2026-09-29 | **A-1 : fichier non annoncé** `PaiementStripe/views.py` (+5 lignes) : `moyen = SR` posé dans le `dict_paiement` de `CreationPaiementStripe._send_paiement_stripe_in_db` (bloc facture, appelé seulement par `new_entry_from_stripe_subscription_invoice`), pour l'avoir dans l'INSERT (un `save()` plus tard relancerait la machine à états). Conséquence de la consigne de l'orchestrateur. **Aucun test ne couvre `SR`** : une mutation survivrait. Garder, avec un test (cas `SR` ajouté au test T1 via le flux `invoice.paid` de P15) ? | `PaiementStripe/views.py` l.117-121 | **Gardé, avec un test `SR`** (mainteneur, 2026-09-29). Fichier ajouté au périmètre de la fiche A. |
| 2026-09-29 | **Pour la fiche F (comptabilité légale, D19)** : la chaîne des ventes ne peut pas voir sa propre **fin tronquée** (dernière vente supprimée, ou sortie de `REGLEE` par `.update()`) : il faut une ancre extérieure. Proposition : chaque Z enregistre le **numéro et l'empreinte de la dernière vente couverte**, et `verifier_chaine_ventes` (ou la vérification d'intégrité de G) compare la chaîne à la dernière ancre. | constat ouvrier A-3 ; tronc D19 | **Mis de côté (mainteneur, 2026-09-29)** : chaîne simple dans le chantier 05 ; sécurisation et certification NF525 dans un autre chantier → `TODO/COMPTABILITE-certification-NF525.md`. |

## 6. Journal

Une ligne par événement, la plus récente en haut. Format :
`AAAA-MM-JJ HH:MM — session — ce qui s'est passé (preuve : commande / fichier)`.

- 2026-09-29 — 05-A — `make test` complet après A-4 : 2167 passed, 0 FAILED/ERROR (1er lancement perdu sur un 502 du serveur en rechargement, relancé). Fiche A prête à committer ; commit proposé au mainteneur.
- 2026-09-29 — 05-A-4 — vert (54 + 22 ; `check`, `makemigrations --check` propres). Relecture djc conforme ; dernière mention de session retirée de `models.py` (renvois « D14 », « fiche H » gardés : ce sont des liens vers la spec). Mutations 6/6 tuées, sha256 identiques. À savoir pour B : le service n'accepte que `Decimal` / `int` pour les quantités et taux (un `float` ou `"3"` est refusé) ; les producteurs convertiront. Suite complète lancée.
- 2026-09-29 — 05-A-4 — rouge prouvé par l'orchestrateur (6 failed). `float` refusé même quand la valeur n'est pas utilisée (`quantite_pour_cout` sans prix d'achat) : une seule règle. Feu vert étape 2.
- 2026-09-29 — 05-A — relecture Fable : 0 bloquant ; **2 importants** (formule qui accepte un `float` → centime faux en silence ; garde de `LigneArticle.save()` qui compare la mémoire brute à la base → faux refus d'un changement de statut) ; 9 mineurs. Doc corrigée par l'orchestrateur : fiche A §7 (fichiers, 9 tests ajoutés, « 10 cas », phrase sur `delete()`), TODO NF525 (périmètre de l'empreinte, suppressions). Code : session A-4 (importants + mineurs 3, 5-8), ceinture et bretelles.
- 2026-09-29 — 05-A — `make test` complet : 2159 passed, 0 FAILED/ERROR. Relecture Fable de la fiche A lancée.
- 2026-09-29 — méthode — **précision du mainteneur** : la simplification ne vaut que pour le chaînage (NF525 plus tard). Pour tout le reste du chantier : « ceinture et bretelles » (vérifications redondantes gardées, aucune étape de la boucle allégée).
- 2026-09-29 — 05-A-3 — vert (68 passed ; `check`, `makemigrations --check` propres ; 49 tests voisins d'`integrity` verts). Relecture djc : conforme. Mutations : 7/8 tuées ; `select_for_update` survit (redondant avec le verrou du lieu pour l'encaissement) → gardé, documenté, signalé au mainteneur. Script de concurrence dans `test_vente_service` : OK, ÉCHEC sous `atomic` retiré. Bug `Product.delete()` sans image → TODO. Fiche §4 corrigée (ordre du statut). Suite complète de fin de fiche lancée.
- 2026-09-29 — méthode — mainteneur : **chaîne simple** (fiche §5 telle quelle) dans le chantier 05 ; durcissement et certification NF525 repoussés à un autre chantier (`TODO/COMPTABILITE-certification-NF525.md`). Ouvrier A-3 prévenu : pas de règle de début de chaîne, pas d'ancre.
- 2026-09-29 — 05-A-3 — rouge prouvé par l'orchestrateur (`ImportError` ; 5 failed contre un service vide). Constats tranchés (§4) ; fin de chaîne tronquée → exigence pour F (§5). Feu vert étape 2.
- 2026-09-29 — 05-A-3 — brief `05-A-3.md` écrit (script de concurrence dans le schéma `test_vente_service`, jamais `lespass`) ; ouvrier Opus lancé (étape 1).
- 2026-09-29 — 05-A-2 — vert (63 passed avec A-1 et la caractérisation ; `check`, `makemigrations --check` propres). Relecture djc du service : conforme. Ajouts (vente close, origine, annulation) tests d'abord. Mutations : 17 jouées ; la 1ʳᵉ égalité retirée **survivait** (le test 1050/1049 est aussi refusé par la 2ᵉ égalité) → `test_encaisser_refuse_un_offert_sans_reglement_de_trace` ajouté, puis tuée. Toutes les empreintes identiques.
- 2026-09-29 — 05-A-2 — rouge prouvé par l'orchestrateur (`ImportError` à la collecte ; `tva_zero` rouge). Fabrique et tests relus conformes djc. Points tranchés (§4). Feu vert étape 2.
- 2026-09-29 — 05-A-2 — brief `05-A-2.md` écrit ; ouvrier Opus lancé (étape 1 : tests seuls).
- 2026-09-29 — 05-A-1 — test `SR` ajouté (`test_paiement_stripe_moyen_sr_pose_a_la_creation_d_une_echeance`, vrai webhook `invoice.paid`) ; 19 passed + 22 ; mutation `SR` tuée, sha256 identique. Session A-1 close (commit en fin de fiche A).
- 2026-09-29 — 05-A-1 — vert : 18 passed + 22 caractérisation, `check` et `makemigrations --check` propres ; migrations `BaseBillet 0230`, `laboutik 0007` appliquées sur 49 schémas (dont 22 `test_*`). Relecture djc du code : conforme (`on_delete` motivés, import de `models_vente` en fin de `models.py` commenté). Mutations 11/11 tuées. `git diff --stat` : `PaiementStripe/views.py` non annoncé → question §5, arrêt.
- 2026-09-29 — 05-A-1 — rouge prouvé par l'orchestrateur (`ModuleNotFoundError` sur la formule ; 5 failed / 1 passed sur les modèles). Tests relus conformes djc. Points de l'ouvrier tranchés (§4). Feu vert étape 2.
- 2026-09-29 — 05-A — A′ commitée (`8cce96c5`). Fiche A confrontée au code : ancrages présents, `makemigrations` propre. Décision VR/FD hors CA (§5). Écart A-1 (contrainte conditionnelle, §4). Fiche découpée A-1 / A-2 / A-3 ; brief `05-A-1.md` écrit ; ouvrier Opus lancé.
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
| 2026-09-29 | 2167 passed (0 FAILED / ERROR) | — | fin de fiche 05-A après A-4 (+8) |
| 2026-09-29 | 2159 passed (0 FAILED / ERROR) | — | fin de fiche 05-A (+46 : 11 formule, 8 modèles, 27 service/chaîne) |
| 2026-09-29 | 2113 passed (0 FAILED / ERROR) | — | fin de fiche 05-A′ après A′-5 (relancé) |
| 2026-09-29 | 2113 passed (0 FAILED / ERROR) | — | fin de fiche 05-A′ (+22 tests de caractérisation) |
| 2026-09-29 | 2091 passed (0 FAILED / ERROR) | — | fin de fiche 05-0 (e2e pas exigé en 0) |
| 2026-09-28 | 2082 passed | 116 passed | départ (après chantier 04 A-E) |

## 8. Pièges rencontrés pendant le chantier

(à reporter ensuite dans `tests/PIEGES.md` par le mainteneur)

- 2026-09-29 (A′-1) — Mutation : un seul `curl` 200 juste après l'Edit ne suffit pas, le serveur byobu n'a pas encore commencé à recharger → `make test` sort en 502 sans lancer pytest (sortie vide, faux « survit »). Attendre **3 réponses 200 d'affilée** (1 s d'écart) avant `make test`, et vérifier qu'une ligne `passed`/`failed` sort.
