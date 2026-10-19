### Tâche 4 : les rubriques financement participatif, remboursements, annulations

**Fichiers :** modifier `Administration/recap_quotidien.py` ; test : classe `TestLesRubriquesSuite`.

**Interfaces — consomme :** le format de rubrique de la tâche 3 ; `annulee_le` (tâches 1-2).
**Produit :** les rubriques ci-dessous, ajoutées à la fin de la liste rendue par `rubriques_de_la_veille`.

| `cle` | Source | Filtre |
|---|---|---|
| `nouveaux_projets` | `crowds.Initiative` | `created_at` fenêtre |
| `nouvelles_lignes_de_budget` | `crowds.BudgetItem` | `created_at` fenêtre |
| `lignes_de_budget_en_attente` (stock) | `crowds.BudgetItem` | `state=BudgetItem.State.REQUESTED` |
| `contributions_payees` | `crowds.Contribution` | `paid_at` fenêtre ; `payment_status` dans `PaymentStatus.PAID`, `PaymentStatus.PAID_ADMIN` |
| `nouveaux_votes` | `crowds.Vote` | `created_at` fenêtre |
| `nouvelles_participations` | `crowds.Participation` | `created_at` fenêtre |
| `participations_en_attente` (stock) | `crowds.Participation` | `state=Participation.State.REQUESTED` |
| `remboursements` | `LigneArticle` | `datetime` fenêtre ; `status` dans `REFUNDED`, `CREDIT_NOTE`. Ligne : l'objet remboursé (via `reservation`, `membership`, `booking` ; repli `ligne.pricesold.productsold.name` pour un article de caisse) + **l'argent rendu** `euros_a_la_francaise(-ligne.total_ttc)` (`comptabilite/presentation.py`) — pas `-qty × amount`, qui ignore la part offerte et la part en jetons |
| `annulations` | `Reservation`, `Booking`, `Membership` | `annulee_le` fenêtre ; ligne marquée « remboursé » s'il existe une `LigneArticle` `REFUNDED`/`CREDIT_NOTE` qui pointe vers l'objet |

Lien des rubriques `crowds` : `f"https://{domaine}/admin/crowds/initiative/"` (seule `Initiative`
a une liste dans l'admin ; les autres sont des inlines).

- [ ] **Étape 1 : tests qui échouent** — même grille que la tâche 3 (présent hier / absent
  avant-hier et aujourd'hui / statut exclu), plus :
  - `test_une_contribution_creee_avant_hier_et_payee_hier_compte` ;
  - `test_une_contribution_en_attente_ne_compte_pas` (`paid_at=None`) ;
  - `test_une_contribution_sans_contributeur_ne_fait_pas_planter` (`contributor=None`, `contributor_name=None`) ;
  - `test_un_remboursement_d_hier_nomme_la_reservation_et_le_montant` : écrire l'avoir **par le
    service** (`Reservation.cancel_and_refund_resa(annulation_par_l_admin=True, moyen_rembourse=…)`
    sur une réservation payée en espèces, cf. `tests/pytest/test_avoirs_ecrivent_la_vente.py`) →
    la ligne contient le nom de l'événement et le montant à la française ;
  - `test_un_remboursement_d_un_article_de_caisse_nomme_l_article` (avoir sans réservation, adhésion ni booking) ;
  - `test_le_montant_rembourse_est_l_argent_rendu` : article à 10 € dont 4 € offerts → « 6,00 € ».
  - `test_une_annulation_remboursee_est_marquee_rembourse` ;
  - `test_une_annulation_sans_argent_est_listee` (réservation gratuite annulée hier).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichier neuf).
- [ ] **Étape 5 : commit suggéré** : `feat(recap): financement participatif, remboursements, annulations`.

---

