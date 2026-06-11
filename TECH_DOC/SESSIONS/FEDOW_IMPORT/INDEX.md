# FEDOW_IMPORT — Hub du chantier

**Scénario acté (2026-06-10) : S6 — hybride additif.** Aucune fusion, aucune
migration. Fedow standalone reste en place pour les 500 lieux existants et
pour le FED. La caisse laboutik V2 + `fedow_core` sont copiées de lespass-main
(branche `new_pairing_and_nfc`) : monnaies locales des nouveaux tenants en DB
locale, tokens legacy acceptés au POS via l'API Fedow (signature user, sans
handshake). Feuille de route : **[ROADMAP.md](./ROADMAP.md)** (8-10 sessions).
La fusion complète (S4, strangler fig) reste documentée comme option future.

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [ROADMAP.md](./ROADMAP.md) | **Feuille de route S6** : lots C-A (socle) → C-B (durcissement) → C-C (interop legacy) → C-D (pilote), checkpoints et critères de recette | 2026-06-10 — **ACTÉE, pilote le chantier** |
| [TESTS-STRATEGIE.md](./TESTS-STRATEGIE.md) | Stratégie de tests : non-régression (735 tests), invariant de conservation de la monnaie, concurrence/stress, mocks à payloads réels, intégration Fedow docker, fixture « pont » | 2026-06-10 |
| [SPEC.md](./SPEC.md) | Spec S5 d'origine (D1-D6) — D3-D6 toujours valables, découpage remplacé par ROADMAP | 2026-06-10 — révisée |
| [01-recherche-etat-des-lieux.md](./01-recherche-etat-des-lieux.md) | Recherche initiale : cartographie des deux moteurs, points durs, questions ouvertes | 2026-06-10 — terminé |
| [02-audit-profond.md](./02-audit-profond.md) | Audit multi-agents (42 agents) : 9 bloquants, verdict + plan révisé | 2026-06-10 — 19 contre-expertises à relancer |
| [02b-audit-findings-detail.md](./02b-audit-findings-detail.md) | Annexe générée : détail des 68 findings avec verdicts | 2026-06-10 |
| [03-scenarios-coexistence.md](./03-scenarios-coexistence.md) | Comparaison S1 (population) / S2 (zéro migration) / S3 (split par asset, FED legacy) | 2026-06-10 — dépassé par S4 |
| [04-scenario-S4-strangler.md](./04-scenario-S4-strangler.md) | S4 : import de Fedow tel quel + bascule DNS + désamorçage progressif (strangler fig). Verdict : S4 > S3 > S2 > S1 | 2026-06-10 — arbitrage en attente |
| [05-scenario-S5-laboutik-sur-fedow-distant.md](./05-scenario-S5-laboutik-sur-fedow-distant.md) | S5 : aucune fusion — Fedow reste en place, LaBoutik V2 (intégré) s'y branche en HTTP via FedowAPI. Composable avec S4 (phase produit → phase infra) | 2026-06-10 — **ACTÉ** |
| [06-revue-laboutik-new-pairing-estimation.md](./06-revue-laboutik-new-pairing-estimation.md) | Revue complète branche `new_pairing_and_nfc` (appairage PIN, NFC, 2 clients matériels) + estimation S5 : **15-22 sessions** | 2026-06-10 |
| [07-variante-additive.md](./07-variante-additive.md) | Variante additive (renommée **S6**) : fedow_core local conservé (copier-coller), interop legacy EN AJOUT | 2026-06-10 — creusée en doc 08 |
| [08-s6-creusage-profond.md](./08-s6-creusage-profond.md) | Creusage S6 : débit legacy sans handshake CONFIRMÉ, pont cartes à construire, 4 parades obligatoires, périmètre phase 1 (cartes liées). **8-10 sessions** | 2026-06-10 — arbitrage en attente |
| [09-philosophie-v2-vs-s6.md](./09-philosophie-v2-vs-s6.md) | La V2 a choisi S2-présent + S1-différé (réseau scindé, migration repoussée). S6 = V2 moins une décision. **C-A + C-B = tronc commun**, embranchement au C-C | 2026-06-10 |

## Branche de travail

`main-fedow-import` (Lespass V1, ce repo).

## Repères

- **Fedow standalone** : `/home/jonas/TiBillet/dev/Fedow` (branche `main`)
- **Prototype V2** : `/home/jonas/TiBillet/dev/lespass-main` (branche `V2`) — contient
  un `fedow_core` réécrit (modèles + services) dont les décisions sont réutilisables.
