### Tâche 8 : la démo du flush — l'activité d'hier, et le récap envoyé à l'admin

Demande du mainteneur : après un `flush.sh`, le lieu `lespass` contient l'activité d'hier de
**plusieurs personnes différentes** (adhésions, ventes, réservations de ressources, tâches
bénévoles), et **le récap est envoyé à l'admin à la fin du flush**.

**Ce que le flush crée déjà (à réutiliser, pas à refaire) :**
- `_seed_ventes_de_la_veille` (`Administration/management/commands/demo_data_v2.py`) appelle
  `seed_ventes_de_la_veille_par_le_moteur()` (`_demo_data_v2_ventes.py`) : 2 billets de concert,
  1 adhésion en ligne et 3 ventes au Bar, **hier**, par le vrai moteur de vente, **avec un seul
  client** (`demo-ventes@example.com`) ; puis crée la J par `generer_cloture_pour_tenant`.
- `create_booking_fixtures` : les ressources (« Petite salle », « Coworking »…) et les plannings
  bénévoles (« Bar associatif », « Festival ») de `lespass`.
- L'admin de `lespass` : `ADMIN_EMAIL` du `.env` (`client_admin`).

**Fichiers :**
- Créer : `Administration/management/commands/_demo_data_v2_recap.py`
- Modifier : `Administration/management/commands/demo_data_v2.py` (`_seed_ventes_de_la_veille`, `handle`)
- Test : `tests/pytest/test_demo_recap_de_la_veille.py` (motif : `tests/pytest/test_demo_ventes_de_la_veille.py`, même mise en place `FastTenantTestCase` + `create_test_pos_data`)

**Interfaces — consomme :** `preparer_le_recap_du_lieu`, `envoyer_le_recap` (tâche 6) ; les
outils privés de `_demo_data_v2_ventes.py` (`_une_vente_reglee`, `_membership_demo`,
`_reservation_demo`, `_tarif_vendu_par_le_moteur`) — les importer, ne pas les recopier.

**Produit :**

```python
def seed_activite_de_la_veille_pour_le_recap() -> dict:
    """Dans tenant_context(lespass), APRÈS seed_ventes_de_la_veille_par_le_moteur et AVANT la J.
    Rend {"ecrites": [phrases], "sautees": [phrases]}."""
```

Quatre personnes de démo, `recap-<prenom>@example.com` (`get_or_create`, actives, sans mail) :

| Personne | Hier (heure du lieu) |
|---|---|
| Alice | adhésion payée en ligne (vente par le moteur, motif de l'adhésion de `seed_ventes_de_la_veille_par_le_moteur`) ; inscription à un besoin du planning « Bar associatif » |
| Bruno | réservation de la « Petite salle » (`Booking`, payée sur place : vente par le moteur avec `champs={"booking": …}`) ; 1 billet de concert |
| Chloé | demande d'adhésion **en attente** (`Membership`, `status=ADMIN_WAITING`, sans vente) ; inscription à un besoin du planning « Festival » |
| David | 3 bières au Bar (vente par le moteur, `client=David`) ; une réservation de concert **annulée hier** (`annulee_le` hier) |

Règles :
- Toutes les dates d'hier en heure du lieu, **avant la J** : `date_added`, `booked_at`,
  `created_at` fixés par `.update()` après création (champs `auto_now_add`) ; les ventes par
  l'`heure` du moteur.
- **Idempotent** : rien n'est écrit si `recap-alice@example.com` a déjà une adhésion, ou si le
  lieu a déjà une J (même garde que `seed_ventes_de_la_veille_par_le_moteur`).
- **Jamais `status=Membership.ADMIN`** (un signal écrirait une vente en plus).
- Un objet introuvable (mode `--quick`, planning absent) → une phrase dans `"sautees"`, pas d'erreur.

Branchements dans `demo_data_v2.py` :
- `_seed_ventes_de_la_veille` : appeler `seed_activite_de_la_veille_pour_le_recap()` juste
  **après** `seed_ventes_de_la_veille_par_le_moteur()`, dans le même `tenant_context`, et
  **avant** `generer_cloture_pour_tenant` (la J reprend ainsi les ventes de David, d'Alice et de
  Bruno).
- Nouvelle méthode `_envoyer_le_recap_de_demo(self, options)`, appelée **en dernier** dans
  `handle` (après `_verifier_les_sites_de_demo`) : dans `tenant_context(lespass)`,
  `recap = preparer_le_recap_du_lieu(timezone.now(), <veille 00:00 heure du lieu, en UTC>, timezone.now())`.
  La borne haute des Z est **maintenant**, pas le seuil d'aujourd'hui : le flush crée la J à
  l'instant, elle finit donc après le seuil du jour. Puis `envoyer_le_recap(recap)` et une ligne
  dans la sortie : destinataires et nombre de rubriques, ou « rien à envoyer ». Ne pose **pas**
  le marqueur `recap_quotidien_traite_le`. Sautée avec `--no-sales`. Une erreur d'envoi remonte
  (même règle que `_verifier_caisse_ouvrable_ou_planter`).

- [ ] **Étape 1 : tests qui échouent** (dans `test_demo_recap_de_la_veille.py`)
  - `test_quatre_personnes_differentes_ont_une_activite_d_hier` : 4 utilisateurs `recap-*`, chacun au moins un objet daté d'hier.
  - `test_le_recap_de_demo_a_toutes_les_rubriques_attendues` : `preparer_le_recap_du_lieu(...)` → les clés `nouvelles_adhesions`, `adhesions_en_attente`, `nouvelles_reservations`, `nouvelles_reservations_de_ressources`, `nouvelles_inscriptions_benevoles`, `annulations` sont présentes ; `len(recap["clotures"]) == 1`.
  - `test_la_j_reprend_les_ventes_des_personnes_de_demo` : la J contient la vente de David.
  - `test_un_second_passage_n_ecrit_rien` : `"ecrites" == []`.
  - `test_le_recap_de_demo_part_a_l_admin` : `_envoyer_le_recap_de_demo` avec `Administration.recap_quotidien.CeleryMailerClass` remplacé → un appel, l'admin du lieu dans `email`, un PDF en pièce jointe.
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichiers neufs seulement ; `demo_data_v2.py` est pré-existant : pas de `ruff format`).
- [ ] **Étape 5 : essai réel — avec l'accord du mainteneur** (le flush efface la base de dev partagée) : `docker exec lespass_django bash /DjangoFiles/flush.sh` ; la sortie montre « Récap envoyé à … » ; le mail est reçu dans la boîte de dev, avec ses rubriques et le PDF du Z. Ajouter ce scénario au CHANGELOG.
- [ ] **Étape 6 : commit suggéré** : `feat(demo): activité d'hier et récap du matin envoyé à la fin du flush`.
