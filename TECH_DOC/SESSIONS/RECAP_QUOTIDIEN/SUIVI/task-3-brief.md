### Tâche 3 : la fenêtre et les rubriques billetterie, adhésions, ressources, bénévoles, événements

**Fichiers :**
- Créer : `Administration/recap_quotidien.py`
- Test : classe `TestLesRubriques`

**Interfaces — produit :**

```python
NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE = 10

def fenetre_de_la_veille(maintenant, fuseau_du_lieu) -> tuple[datetime, datetime]:
    """[veille 00:00, aujourd'hui 00:00[ en heure du lieu, rendus en UTC."""

def rubriques_de_la_veille(debut, fin, domaine) -> list[dict]:
    """Les rubriques NON VIDES, dans l'ordre du tableau ci-dessous."""
```

Une rubrique est un `dict` :
`{"cle": str, "titre": str, "est_un_stock": bool, "nombre": int, "nombre_de_nouveaux": int,
"lignes": list[str], "nombre_de_lignes_cachees": int, "lien": str}`.
- `nombre` = toutes les lignes de la rubrique ; `lignes` = les 10 premières (ordre : la plus
  récente d'abord) ; `nombre_de_lignes_cachees = nombre - len(lignes)`.
- `nombre_de_nouveaux` : pour un stock, celles créées dans la fenêtre ; sinon égal à `nombre`.
- `lien` : `f"https://{domaine}/admin/<app>/<modele>/"` (motif de `send_membership_pending_admin`).
- Une ligne est un texte court ; elle affiche le statut (`get_status_display()`), et ne plante
  jamais sur un champ `None` (repli : `_("(sans nom)")`).

Les rubriques de cette tâche (clé — source — filtre ; « fenêtre » = `debut <= date < fin`) :

| `cle` | Source | Filtre |
|---|---|---|
| `nouvelles_adhesions` | `Membership` | `date_added` fenêtre ; `status` hors `WAITING_PAYMENT`, `CANCELED`, `ADMIN_CANCELED`, `ADMIN_WAITING` |
| `adhesions_en_attente` (stock) | `Membership` | `status=ADMIN_WAITING` |
| `nouvelles_reservations` | `Reservation` | `created_at` fenêtre ; `status` hors `CREATED`, `UNPAID`, `CANCELED` |
| `nouvelles_reservations_de_ressources` | `booking.Booking` | `booked_at` fenêtre ; `status` hors `WAITING_PAYMENT`, `ADMIN_CANCELED`, `USER_CANCELED` |
| `nouvelles_inscriptions_benevoles` | `InscriptionBenevole` | `created_at` fenêtre |
| `nouveaux_evenements` | `Event` | `created_at` fenêtre ; état par ligne : « proposition en attente » (`is_proposal and not published`), « publié » (`published`), sinon « brouillon » |
| `propositions_en_attente` (stock) | `Event` | `is_proposal=True, published=False` |

- [ ] **Étape 1 : tests qui échouent**
  - `test_la_veille_va_de_minuit_a_minuit_heure_du_lieu` : `maintenant = heure_de_paris(2026,10,13,7)` → `(heure_utc(2026,10,11,22), heure_utc(2026,10,12,22))`.
  - `test_la_veille_d_une_nuit_de_changement_d_heure_dure_25_heures` : `maintenant = heure_de_paris(2026,10,26,7)` → `fin - debut == timedelta(hours=25)`.
  - `test_la_veille_en_martinique` : fuseau `America/Martinique`, `maintenant = 13/10 7h locale` → `(heure_utc(2026,10,12,4), heure_utc(2026,10,13,4))`.
  - Pour **chaque** rubrique, deux tests : `test_<cle>_compte_hier_et_pas_avant_hier_ni_aujourd_hui` (trois objets, `nombre == 1`), et, s'il y a des statuts exclus, `test_<cle>_ignore_les_statuts_exclus` (une boucle `for statut in …` avec `self.subTest(statut=statut)`).
  - Fabriquer les adhésions par `Membership.objects.create(...)` ou `creer_une_adhesion_active(...)` (`fabriques_panier.py`) — `creer_adhesion` crée un produit et un tarif, pas une adhésion. **Jamais `status=Membership.ADMIN`** : un signal post_save écrit alors une vente. Inscriptions bénévoles : motif `InscriptionBenevole.objects.create` de `tests/pytest/test_benevolat_rappel.py`.
  - `test_une_demande_d_adhesion_d_hier_est_dans_le_stock_et_pas_dans_les_nouvelles` : `adhesions_en_attente.nombre == 1`, `nombre_de_nouveaux == 1`, pas de rubrique `nouvelles_adhesions`.
  - `test_une_vieille_demande_en_attente_est_dans_le_stock_sans_etre_nouvelle` : `nombre == 1`, `nombre_de_nouveaux == 0`.
  - `test_une_reservation_ancienne_modifiee_hier_ne_compte_pas` : `created_at` avant-hier, `datetime` hier → pas de `nouvelles_reservations`.
  - `test_une_proposition_creee_et_validee_hier_est_dans_les_nouveaux_evenements` : `is_proposal=False, published=True`, `created_at` hier → ligne contenant « publié ».
  - `test_une_adhesion_sans_personne_ne_fait_pas_planter` : `Membership(user=None)` d'hier → une ligne, aucune exception.
  - `test_une_rubrique_de_douze_lignes_en_montre_dix` : 12 adhésions d'hier → `len(lignes) == 10`, `nombre_de_lignes_cachees == 2`.
- [ ] **Étape 2 : échec vérifié.**
- [ ] **Étape 3 : implémenter** — une petite fonction par rubrique (`_rubrique_nouvelles_adhesions(debut, fin, domaine) -> dict | None`), appelées dans l'ordre par `rubriques_de_la_veille`. `fenetre_de_la_veille` : `aujourd_hui = timezone.localtime(maintenant, fuseau).date()`, puis `datetime.combine(jour, time(0), tzinfo=fuseau).astimezone(UTC)` pour la veille et pour aujourd'hui.
- [ ] **Étape 4 : PASS.** `ruff check --fix` puis `ruff format` sur `Administration/recap_quotidien.py` (fichier neuf).
- [ ] **Étape 5 : commit suggéré** : `feat(recap): fenêtre de la veille et premières rubriques`.

---

