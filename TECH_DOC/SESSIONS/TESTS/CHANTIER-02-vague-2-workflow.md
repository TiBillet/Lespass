# CHANTIER 02 — Vague 2 de migration TS → Python (workflow multi-agents)

Statut : ✅ TERMINÉ (2026-06-11 après-midi)

## Incident serveur résolu au passage

Pendant le run de validation de la suite TS simplifiée (matin), le serveur
dev s'est **gelé à 10:56** au milieu du signal `send_membership_product_to_fedow`
(spec 25, duplication produit). Toutes les requêtes partaient en 504, d'où
une cascade de faux échecs sur les specs 33-39 (dont le spec 34).

- **Cause racine** : `fedow_connect/fedow_api.py` (`_post` et `_get`) faisait
  ses appels HTTP vers le serveur Fedow **sans `timeout`**. Si Fedow ne répond
  pas, le thread du runserver mono-thread pend pour toujours.
- **Fix** : `timeout=30` ajouté sur les deux appels (commentaire FALC avec
  référence incident).
- Le spec 34 repassait au vert dès le redémarrage du serveur (2/2 en 39 s) —
  ce n'était pas un bug du spec.

## Vague 2 — 8 specs migrés par workflow

Workflow `migrate-ts-specs-to-python` : 8 agents de conversion en parallèle
(écriture des fichiers seulement), puis vérification **strictement
séquentielle** (un pytest à la fois — le serveur dev est mono-thread).

| Spec TS | Fichier Python | Tests | Verdict |
|---|---|---|---|
| 01-login | `test_login.py` | 2 | ✅ passed |
| 02-admin-configuration | `test_admin_configuration.py` | 1 | ✅ passed (restauration config en try/finally) |
| 16-user-account-summary | `test_user_account_summary.py` | 1 | ✅ corrigé puis vert |
| 19-reservation-limits | `test_reservation_limits.py` | 1 | ✅ corrigé puis vert |
| 21-membership-account-states | `test_membership_account_states.py` | 1 | ✅ corrigé puis vert |
| 23-crowds-participation | `test_crowds_participation.py` | 1 | ✅ corrigé puis vert (initiative dédiée au lieu du « premier lien ») |
| 24-crowds-summary | `test_crowds_summary.py` | 1 | ✅ corrigé puis vert |
| 99-theme_language | `test_theme_language.py` | 3 | ✅ passed |

Les 8 specs TS correspondants sont supprimés de `tests/playwright/tests/`.

## Notes des agents à retenir

- Le conftest e2e n'a pas de fixtures `create_reservation` / `create_membership`
  ni l'option `membershipRequiredProduct` sur `create_product` : les tests 16,
  19 et 21 ont des helpers HTTP locaux qui répliquent `utils/api.ts`.
  → Candidats à centraliser dans le conftest quand un 2e test en aura besoin.
- `django_shell` échappe les guillemets doubles : utiliser des quotes simples
  (ou base64 pour les valeurs arbitraires, cf. test_admin_configuration).
- Thème = localStorage, langue = cookie par contexte navigateur → pas de
  restauration nécessaire dans test_theme_language.

## Validation finale de la suite TS restante (22 specs)

Run du 2026-06-11 après-midi : 37 passed, 1 flaky, 1 failed → corrigés :

- **Spec 36 (SEPA)** : son snippet shell importait `Paiement_stripe` depuis
  `PaiementStripe.models` alors que le modèle vit dans `BaseBillet.models`.
  L'`ImportError` était avalée → le test ne créait jamais le paiement PENDING
  et ne testait donc PAS vraiment la protection doublon (flaky en bonus).
  Import corrigé.
- **Spec 26 (admin custom form)** : timeout `execSync` 15 s trop court pour
  le boot de `tenant_command shell` sous charge → passé à 60 s.

Re-run des deux specs : **4 passed (59 s)**. Suite TS restante : 22 specs verts.

## Reste à migrer (22 specs TS)

- **Vague 3 (admin Unfold)** : 26, 32, 33, 34, 35, 37, 38, 39
- **Vague 4 (adhésions spécifiques)** : 03, 04, 05, 06, 07, 14, 17, 22, 27, 36, 43
- **Vague 5 (divers)** : 25 (duplication produit), 29 (event quick create), 40 (explorer markers)
