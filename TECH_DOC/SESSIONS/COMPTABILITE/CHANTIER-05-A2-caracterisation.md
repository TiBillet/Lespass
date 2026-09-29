# Chantier 05-A′ — Tests de caractérisation : figer la logique métier avant d'y toucher

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — §8
> Détail complet : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §6
> Effort : 1,5 j (une session par fichier, sauf QR) — Dépend de : rien. **Livrée avant
> A** (ordre du §6 du tronc), donc avant tout changement de code métier. Aucun code de
> production modifié.

## 1. Pourquoi

Le chantier touche tous les chemins où l'argent entre ou sort. Il ne doit **pas** changer
la logique métier : statuts des paiements, des réservations, des billets, des
adhésions, des bookings, des commandes ; e-mails ; billets et adhésions créés ; appels
Stripe et Fedow ; envois à l'ancien LaBoutik.

Ces tests **figent le comportement d'aujourd'hui**, parcours par parcours (annexe §4,
P1 à P17). Ils restent verts **sans modification** de B à H. Un test qui tombe pendant
une fiche = une logique métier changée sans le vouloir.

## 2. Règles d'écriture

- Un test de caractérisation est **vert** sur le code actuel : pas de « vu rouge ». Sa
  force se prouve par **mutation** (annexe §6.4 : 11 mutations, chacune doit faire
  tomber au moins un test).
- Il n'asserte **que des effets observables** : statuts finaux, objets créés, **noms et
  arguments des tâches Celery demandées**, appels Stripe / Fedow simulés, **charge utile**
  envoyée à l'ancien LaBoutik. **Jamais** un champ que la fiche H retire, lu sur la ligne
  (`payment_method`, `asset`…) : la charge utile est le contrat, pas la colonne.
- Outils existants uniquement (annexe §6.1) : `fabriques_panier`, `fabriques_reservation`,
  `mock_stripe`, `django_capture_on_commit_callbacks(execute=True)`, `tenant_context`
  (jamais `schema_context`). Marque `django_db` (rollback) : aucun de ces tests ne lit la
  numérotation ni la chaîne.
- Un assistant commun `etat_metier(...)` rend le dictionnaire des statuts utiles et des
  noms de tâches ; chaque test compare à un dictionnaire attendu écrit en clair.
- Un bug actuel trouvé en écrivant est **figé tel quel** (ex. T13 : le rejeu `PAID → PAID`
  repasse les avoirs en `PAID`) et signalé au mainteneur, pas corrigé ici.

## 3. Les fichiers

| Fichier | Parcours | Nombre de tests |
|---|---|---|
| `tests/pytest/test_caracterisation_en_ligne.py` | P1-P3, P15 | 7 |
| `tests/pytest/test_caracterisation_annulations.py` | P5-P8 | 6 |
| `tests/pytest/test_caracterisation_admin_api.py` | P13, P16, décision Stripe / gratuit | 4 |
| `tests/pytest/test_caracterisation_caisse.py` | P9, P12, clôture | 4 |
| `tests/pytest/test_caracterisation_qr.py` | P10 (en complément de `test_qrcodescanpay_flux_complet.py`, après 04-F-1) | 2 |

**23 tests** : ceux qui portent une des 11 mutations (annexe §6.4), ceux qui doivent
changer volontairement (§4), et les parcours Stripe P1, P3, P5, P15. Les autres
parcours sont déjà couverts par `test_commande_service.py`,
`test_qrcodescanpay_flux_complet.py` et les tests de `controlvanne`. Liste nominative
et ce que chacun fige : annexe §6.2.

## 4. Ceux qui ont le droit de changer

Seuls ces tests peuvent être modifiés, **dans la fiche qui change volontairement le
comportement**, dans la même session, avec la raison au CHANGELOG :

| Test | Fiche | Pourquoi |
|---|---|---|
| `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` | D | D30 : un seul avoir, pour le dernier paiement |
| `test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir` | D | D31 : plus d'avoir ni de remboursement hors Stripe |
| `test_billets_vendus_dans_l_admin_offert_montant_zero` | D | D32 : offert écrit comme à la caisse |
| `test_annuler_un_billet_caisse_offert_cree_un_avoir` | G | `total_paid()` lit `total_ttc` : un billet **entièrement offert** n'a rien à rembourser → plus d'avoir d'argent, seule la trace `FREE −X` (validé le 2026-09-29) |
| `test_annuler_reservation_caisse_payee_en_cascade_avoir_sur_la_part_rattachee` | H | une ligne par article |

Tableau « qui garde quoi vert » : annexe §6.3.

## 5. Livrable

- Les 5 fichiers, verts sur le code actuel (`make test ARGS=...`), sortie collée dans
  le SUIVI.
- Les 11 mutations de l'annexe §6.4 jouées par l'orchestrateur, chacune fait tomber son
  test.
- CHANGELOG `CHANGELOG/2026-MM-JJ-montants-entiers-A2-caracterisation.md` (« Refactoring
  interne / tests seulement ») avec la liste des comportements actuels surprenants figés
  (annexe : réservation « payée ailleurs » sans e-mail, adhésion vendue en caisse sans
  facture ni envoi LaBoutik ni récompense, T13…).
