# Stratégie de tests — Chantier S6

Date : 2026-06-10. Compagnon de [ROADMAP.md](./ROADMAP.md).
Règles générales : `tests/TESTS_README.md` + `tests/PIEGES.md` (~80 pièges,
à relire avant tout nouveau test). Deux conftest séparés (pytest / e2e),
jamais de conftest racine.

## Principe

Deux filets existent déjà : la suite V1 (618 pytest + 117 E2E, verte) et la
suite V2 qui voyage avec le code copié. Le chantier ajoute trois étages
spécifiques S6 : **invariants monétaires**, **concurrence**, **contrat legacy**.

## Par lot

### C-A — Non-régression
1. **Baseline** : suite V1 complète lancée AVANT tout transport (état de
   référence), puis après chaque étape. Toujours verte.
2. **Suite V2 portée** : tests fedow_core + laboutik (+ E2E POS : paiement,
   recharge, adhésion NFC, vider-carte) — adaptés aux chemins V1
   (pièges : FastTenantTestCase vs schema_context, cf. PIEGES.md).
3. Mécanique : `manage.py check` 0 issue, `migrate_schemas` complet,
   `makemigrations --check` (zéro drift), smoke test Chrome
   (`https://lespass.tibillet.localhost/`, caisse espèces/CB).

### C-B — TDD + invariants + concurrence
1. **Test de conservation de la monnaie** (nouveau, central) : après une
   rafale d'opérations aléatoires (ventes, recharges, remboursements,
   fusions), pour chaque asset :
   `somme(crédits) − somme(débits) == somme(Token.value)`.
   C'est le test qui aurait détecté le bug DRIFT.
2. **Tests de concurrence** (threads + connexions séparées) :
   - double débit simultané du même token → un seul passe ;
   - recharge concurrente pendant fusion/vidage → zéro reliquat orphelin ;
   - double livraison webhook → un seul crédit (contrainte DB).
3. **Stress test** (la phase ⑨ que la V2 n'a pas faite) : management command
   ~2 000 transactions concurrentes puis `verify_transactions` = 0 divergence.
   Devient un outil de recette permanent.
4. Chaque garde du C-B naît d'un test rouge. Test B1 type : créer un
   BANK_TRANSFER → `verify_transactions` rend 0 divergence, `--fix-tokens`
   ne modifie rien.

### C-C — Pyramide à trois étages
1. **Pytest, FedowAPI mocké par payloads RÉELS** : les réponses du Fedow
   docker (`card_tag_id_retrieve`, `retrieve_by_signature`, `qrcodescanpay`)
   sont enregistrées en fixtures JSON ; les mocks rejouent ces payloads
   (anti-dérive de contrat). Cas : segment legacy nominal, échec/timeout →
   complément, refus fail-fast, pont carte miroir, carte anonyme → invitation,
   double déclaration perte, pas de retry aveugle.
2. **Intégration contre Fedow docker réel** (marqueur `@pytest.mark.fedow_integration`,
   skip si conteneur absent) : flux signés RSA bout en bout, vérification
   DES DEUX CÔTÉS (LigneArticle locale ET transaction QRS côté Fedow,
   montants égaux).
3. **E2E Playwright** : appairage PIN → scan NFC simulé (mode NFCSIMU du
   proto) → vente cascade local+legacy → clôture → ticket. Scénario réseau
   coupé : la vente aboutit en espèces, zéro double débit après reprise.

### C-D — Recette pilote
Checklist manuelle des 8 critères ROADMAP §6, supervisée, dont :
- preuve du réseau unique (carte d'un lieu V1 débitée au POS V2, transaction
  visible côté Fedow standalone) ;
- `verify_transactions` = 0 divergence après une journée réelle ;
- journée mixte → clôture, ticket Z, export FEC corrects.

## Fixtures

| Fixture | Source | Usage |
|---|---|---|
| Fixtures V1 (`flush.sh`) | existant | baseline, non-régression |
| `create_test_pos_data --schema=lespass` | portée de V2 | PV, articles, cartes locales, carte primaire |
| Fixtures bar/asso (session 20 V2) | portées | clôtures, comptabilité, profils CSV/FEC |
| **Fixture « pont » (à créer, session C1)** | nouveau script | côté Fedow docker : place du tenant de test (handshake dev → FedowConfig rempli) + user avec wallet/clés RSA + **carte legacy liée** (tokens FED/TLF) + **carte legacy anonyme** — le couple qui teste les deux chemins du C-C |
| Payloads JSON legacy | capturés sur Fedow docker | contrat des mocks pytest |
| `demo_data` (Fedow) | existant côté Fedow | peuplement du docker de dev |

## Rythme

- Tests du domaine touché à CHAQUE session (règle projet existante).
- Suite complète (pytest + E2E) en fin de chaque lot.
- Le stress test C-B est rejoué en fin de C-C (le segment legacy ne doit pas
  dégrader les invariants locaux) et avant le pilote.
- Carte Stripe de test : 4242 4242 4242 4242, 12/42, 424 (peu utilisée ici :
  la recharge en ligne locale est hors scope phase 1).
