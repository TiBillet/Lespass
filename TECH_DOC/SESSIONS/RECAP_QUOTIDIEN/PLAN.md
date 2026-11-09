# Récap quotidien des admins — Plan d'implémentation

> **Archive du chantier 01, périmée par le chantier 02** ([CHANTIER-02-recap-allege.md](CHANTIER-02-recap-allege.md)) : les clés de rubriques citées ici ont changé.

> **Pour les agents :** SOUS-SKILL REQUIS — `superpowers:subagent-driven-development` (recommandé)
> ou `superpowers:executing-plans`. Les étapes sont en cases à cocher (`- [ ]`).
>
> **Hub :** [INDEX.md](INDEX.md) · **Spec :** [SPEC.md](SPEC.md) — à lire en entier avant la
> tâche 1. Le plan ne répète pas les raisons : elles sont dans la spec.

**But :** chaque matin, un mail par lieu aux admins (et à `rapport_emails` en périodicité J) qui
résume tout ce qui s'est passé la veille, avec les tickets Z en pièce jointe. Aucun mail sans
contenu. Le mail séparé du Z journalier disparaît.

**Décisions du mainteneur sur le plan (2026-10-18) :** montant d'un remboursement = l'argent
rendu (`-total_ttc`) ; exécution **un agent par tâche, relu avant la suivante** ; tâche 8 ajoutée
(démo du flush).

**Architecture :** un module `Administration/recap_quotidien.py` calcule et envoie le récap d'un
lieu. Il est appelé **à la fin** de `generer_les_clotures_automatiques_du_lieu`
(`comptabilite/tasks.py`), après le filet J et les H/M/A, dans la même sous-tâche horaire : pas
de nouvelle tâche Celery beat. Six champs de date nouveaux rendent « créé hier » et « annulé
hier » fiables.

**Stack :** Django 4.2 · django-tenants · django-solo · Celery · pytest (`FastTenantTestCase`).
Aucune nouvelle dépendance.

---

## Contraintes globales

1. **AUCUNE opération git d'écriture.** Ni `add`, `commit`, `push`, `merge`, `rebase`,
   `checkout --`, `restore`, `stash`, `reset --hard`, `clean -f`, `branch -D`. Les étapes
   « Commit » demandent **d'afficher le message suggéré** (sans aucune mention de Claude) dans le
   rapport, puis de **s'arrêter**.
2. **Toute commande Python passe par le conteneur** (`.venv` partagé par bind-mount : `poetry`,
   `pytest` ou `ruff` lancés depuis l'hôte le détruisent). Tests : `make test ARGS="tests/pytest/<fichier>.py"`
   ou `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/<fichier>.py -v`.
3. **`ruff format` seulement sur un fichier NEUF.** Sur un fichier pré-existant : jamais. `ruff
   check --fix` sur un pré-existant seulement après inspection à la main des imports « inutiles »
   (`admin*.py` surtout), puis `manage.py check`.
4. **Ne jamais lancer `makemessages` ni `compilemessages`.** msgid des `_()` en **français**.
   Signaler en fin de tâche le nombre de chaînes ajoutées.
5. **Ne pas lancer de serveur.** Le serveur de dev est tenu par le mainteneur (byobu).
6. **D'autres agents travaillent sur la même base** : lancer les fichiers de test ciblés ; la
   suite complète seulement avec l'accord du mainteneur. Les migrations se **génèrent** avec
   `makemigrations` ; leur application sur la base de dev se fait **avec l'accord du mainteneur**.
7. **FALC** (skill `djc`) : noms verbeux, commentaires FR (FALC) + une ligne EN, boucles `for`
   simples, `LOCALISATION` en tête de docstring. Le commentaire décrit le code tel qu'il est,
   jamais l'historique de la session.
8. **Laisser planter** : pas de `try/except` qui étouffe une erreur de calcul. Une erreur remonte
   à la sous-tâche du lieu (Sentry).
9. **Chaque test est vu ÉCHOUER** sur une mutation volontaire du code avant d'être livré (noter
   la mutation dans le rapport). Zéro `pytest.skip`.
10. **Toutes les heures par `timezone.now()`** (jamais `datetime.now()` ni `date.today()`). Les
    tests patchent `django.utils.timezone.now`.
11. **Les champs `auto_now_add` ne se fixent pas à la création** : dans les tests, créer l'objet
    puis `Modele.objects.filter(pk=…).update(champ=moment)`.
12. Avant d'écrire un test, relire dans `tests/PIEGES.md` : 9.1 (`tenant_context`, jamais
    `schema_context`), 13.4 (intercepter les `.delay()`), 13.5 (le cache django-solo survit au
    rollback ; le piège recommande de patcher `get_solo()`. Ici on suit le motif de
    `test_cloture_unique.py` : **chaque `setUp` écrit toutes les valeurs lues par le récap puis
    fait `configuration.save()`**, pour que le cache porte les valeurs du test), 9.63, 9.86,
    P.ONBOARD.5.
13. Heures des tests : **jamais une égalité d'heure** avec un seuil (convention des tests de
    clôture) : 7h10, 8h10, 4h10…

## Points de vigilance (non couverts par la spec, à tester)

1. **Nuit de changement d'heure** : la veille dure 23 h ou 25 h. La fenêtre se calcule en heure
   locale (minuit → minuit) puis se convertit en UTC → test dans la tâche 3.
2. **Objets sans personne** : une `Membership` peut avoir `user=None` (accepté par design), une
   `Contribution` peut avoir `contributor=None`. Une ligne du récap ne plante jamais sur un `None`
   → tests dans les tâches 3 et 4.
3. **Plus de 10 lignes** dans une rubrique : 10 montrées, puis « et N autres » → test tâche 3.
4. **Aucun destinataire** (aucun admin, `config.email` vide) : pas de mail, un `logger.warning`,
   le marqueur est posé quand même → test tâche 6.
5. **Les tests horaires existants** (`test_cloture_unique.py`, `test_reprise_clotures.py`,
   `test_comptabilite_celery.py`) passent désormais par le récap : ils ne doivent ni casser ni
   envoyer de mail réel → tâche 7, étape de vérification.

---

## Fichier de test

Un seul fichier neuf : **`tests/pytest/test_recap_quotidien.py`**, une classe par tâche, toutes en
`FastTenantTestCase` sur le schéma **`test_recap_quotidien`** (domaine
`test-recap-quotidien.tibillet.localhost`, `setup_tenant` pose `tenant.name = "Test recap
quotidien"`). Motif à copier : l'en-tête et le `setUp` de `tests/pytest/test_cloture_unique.py`
(`connection.set_tenant`, `LaboutikConfiguration.get_solo().save()`, `Configuration` réécrite :
`fuseau_horaire="Europe/Paris"`, `heure_de_fermeture=time(2, 0)`, `language="fr"`,
`rapport_emails=""`, `rapport_periodicite=Configuration.PERIODICITE_NONE`, `email="lieu@example.org"`).

Fabriques existantes à utiliser plutôt que de réécrire : `tests/pytest/fabriques_vente.py`
(`creer_tarif_vendu`, `fabriquer_vente_encaissee`), `fabriques_panier.py` (`creer_utilisateur`,
`creer_adhesion`, `creer_ressource_avec_tarif`, `creer_evenement_avec_tarif`),
`fabriques_reservation.py` (`creer_evenement_et_produit`). Pour les bénévoles :
`tests/pytest/test_benevolat_equipe.py` ; pour les initiatives : `tests/pytest/test_en_ligne_ecrit_la_vente.py`.

Dates de référence des tests : **le mardi 13 octobre 2026**, heure de Paris (CEST, UTC+2).
« La veille » = lundi 12 octobre. Pour la nuit de changement d'heure : **dimanche 25 octobre
2026** (passage à CET), récap du lundi 26.

---

### Tâche 1 : les six champs de date et leur migration

**Fichiers :**
- Modifier : `BaseBillet/models.py` (`Reservation`, `Event`, `Membership`, `Configuration`)
- Modifier : `booking/models.py` (`Booking`)
- Créer : `BaseBillet/migrations/0235_recap_quotidien_dates.py`, `booking/migrations/0006_booking_annulee_le.py` (générées)
- Test : `tests/pytest/test_recap_quotidien.py` (classe `TestLesDatesDeCreation`)

**Interfaces — produit :**
- `Reservation.created_at = DateTimeField(auto_now_add=True, null=True, verbose_name=_("Créée le"))`
- `Event.created_at = DateTimeField(auto_now_add=True, null=True, verbose_name=_("Créé le"))` — `Event.created` (auto_now) reste tel quel.
- `Reservation.annulee_le`, `Membership.annulee_le`, `Booking.annulee_le` =
  `DateTimeField(null=True, blank=True, editable=False, verbose_name=_("Annulée le"))`
- `Configuration.recap_quotidien_traite_le = DateField(null=True, blank=True, editable=False, verbose_name=_("Récap du matin traité le"))`
- Dans le même changement de modèle (une seule migration `BaseBillet`) : le `help_text` de
  `Configuration.rapport_emails` devient `_("Adresses séparées par des virgules. Elles reçoivent le récap du matin (périodicité « Journalier ») ou le rapport de chaque clôture (hebdomadaire, mensuelle, annuelle). Vide : aucun envoi.")` ;
  le libellé du choix `PERIODICITE_JOURNALIER` devient `_("Chaque jour, dans le récap du matin")`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
def test_une_reservation_garde_sa_date_de_creation_quand_on_la_modifie(self):
    # created_at est posé à la création, puis ne bouge plus.
    reservation = ...  # fabrique
    date_de_creation = reservation.created_at
    with patch("django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)):
        reservation.save()
    reservation.refresh_from_db()
    assert reservation.created_at == date_de_creation
    assert reservation.created_at is not None

def test_un_evenement_garde_sa_date_de_creation_quand_on_le_modifie(self): ...  # même forme

def test_annulee_le_est_vide_a_la_creation(self):
    # Réservation, booking, adhésion : annulee_le vaut None tant que rien n'est annulé.
    assert reservation.annulee_le is None
    assert booking.annulee_le is None
    assert adhesion.annulee_le is None
```

- [ ] **Étape 2 : lancer, vérifier l'échec** — `make test ARGS="tests/pytest/test_recap_quotidien.py"` → `AttributeError … created_at`.
- [ ] **Étape 3 : ajouter les champs**, puis générer : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet booking`. Vérifier que `makemigrations` **ne pose aucune question** (colonnes nullables) et que les fichiers ne contiennent que les `AddField` / `AlterField` attendus. Les renommer comme ci-dessus.
- [ ] **Étape 4 : relancer** — PASS. Puis `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → `System check identified no issues`.
- [ ] **Étape 5 : message de commit suggéré** (ne pas committer) : `feat(recap): dates de création et d'annulation pour le récap du matin`.

---

### Tâche 2 : `annulee_le` posé à chaque annulation

**Fichiers :**
- Modifier : `BaseBillet/models.py` — `Reservation.cancel_and_refund_resa` (vers la ligne 3633) et `Reservation.cancel_and_refund_ticket` (vers la ligne 3807, le `save(update_fields=["status"])` devient `update_fields=["status", "annulee_le"]`)
- Modifier : `booking/models.py` — `Booking.cancel_and_refund_booking` (vers la ligne 765)
- Modifier : `BaseBillet/views.py` — l'action `cancel` de l'annulation d'adhésion par un admin (vers la ligne 5959, `membership.status = Membership.ADMIN_CANCELED`)
- Modifier : `Administration/admin/resources.py` — **ajouter** `BookingAdmin.save_model` (il n'existe pas encore)
- **Ne pas toucher** : `BaseBillet/signals.py` (`activator_free_reservation` : annulation automatique d'une réservation gratuite sur un événement devenu complet), `ApiBillet/views.py` (arrêt du renouvellement d'une adhésion)
- Test : classe `TestAnnuleeLe`

**Interfaces — consomme :** les champs de la tâche 1. **Produit :** `annulee_le` fiable sur les trois modèles.

`BookingAdmin.save_model(self, request, obj, form, change)` : si `change`, que `"status" in form.changed_data`, que `obj.status in (Booking.ADMIN_CANCELED, Booking.USER_CANCELED)` et que `obj.annulee_le is None` → `obj.annulee_le = timezone.now()` ; puis `super().save_model(...)`.

- [ ] **Étape 1 : tests qui échouent**
  - `test_annuler_une_reservation_pose_annulee_le` : `reservation.cancel_and_refund_resa(annulation_par_l_admin=True)` sur une réservation gratuite à `moment` → `annulee_le == moment`.
  - `test_annuler_le_dernier_billet_pose_annulee_le` : `cancel_and_refund_ticket` sur l'unique billet → `annulee_le == moment`.
  - `test_annuler_un_booking_pose_annulee_le` : `cancel_and_refund_booking()` → `annulee_le == moment`, `status == Booking.USER_CANCELED`.
  - `test_annuler_un_booking_dans_l_admin_pose_annulee_le` : `BookingAdmin(Booking, staff_admin_site).save_model(request, booking, form, change=True)` (`staff_admin_site` : `Administration/admin/site.py`) avec un `form` factice dont `changed_data == ["status"]` et `booking.status = Booking.ADMIN_CANCELED` → `annulee_le == moment`.
  - `test_annuler_une_adhesion_par_l_admin_pose_annulee_le` : vue `MembershipMVT.cancel` (`BaseBillet/views.py`), URL `reverse("membership_mvt-cancel", kwargs={"pk": adhesion.pk})` = `/memberships/<uuid>/cancel/`. Admin : `creer_utilisateur()` puis `admin.client_admin.add(self.tenant)` et `client.force_login(admin)` (permission `TenantAdminPermission` : admin du lieu, actif, humain). POST `{"with_credit_note": "0"}` sur une adhésion **sans** ligne payée (sinon `moyen_rembourse` est exigé) → réponse `HX-Redirect`, `annulee_le == moment`.
  - `test_l_annulation_automatique_d_une_reservation_gratuite_ne_pose_pas_annulee_le` (documente la ligne « Non » de la spec §3.4) : utilisateur inactif ; `Event(jauge_max=0)` ; `Reservation(status=FREERES, to_mail=True, user_commande=utilisateur)` + un `Ticket` ; `Reservation.objects.filter(pk=…).update(datetime=<il y a 1 h>)` ; puis `utilisateur.is_active = True; utilisateur.save()` → `status == CANCELED` **et** `annulee_le is None`.
  - `test_l_arret_du_renouvellement_ne_pose_pas_annulee_le` : le chemin de `ApiBillet/views.py` (`membership.status = Membership.CANCELED`) → `annulee_le is None`.
- [ ] **Étape 2 : échec vérifié.**
- [ ] **Étape 3 : implémenter** — `self.annulee_le = timezone.now()` juste à côté de chaque `status = …CANCELED` listé.
- [ ] **Étape 4 : PASS**, puis relancer les tests existants des annulations : `tests/pytest/test_avoirs_ecrivent_la_vente.py`, `tests/pytest/test_cancel_subscription.py`, et `rg -l "cancel_and_refund" tests/pytest booking/tests` → tous verts.
- [ ] **Étape 5 : commit suggéré** : `feat(recap): annulee_le posé à chaque annulation`.

---

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

### Tâche 5 : les Z à joindre, « y a-t-il du contenu ? », les destinataires

**Fichiers :** modifier `Administration/recap_quotidien.py` ; test : classe `TestZContenuDestinataires`.

**Interfaces — produit :**

```python
def clotures_j_a_joindre(seuil_de_la_veille, seuil_d_aujourd_hui) -> list[ClotureCaisse]:
    """Les J dont seuil_de_la_veille < datetime_fin <= seuil_d_aujourd_hui, sauf celles qui
    finissent à ou avant la mise en service (comptabilite.tasks.mise_en_service_du_lieu()).
    Ordre : numero_sequentiel croissant."""

def le_recap_a_du_contenu(rubriques, clotures) -> bool:
    """Vrai s'il y a au moins un Z, ou une rubrique qui n'est pas un stock, ou un stock avec
    nombre_de_nouveaux > 0."""

def destinataires_du_recap(tenant, configuration) -> list[str]:
    """Admins du lieu (TibilletUser.client_admin=tenant), sinon configuration.email ; plus
    rapport_emails si rapport_periodicite == PERIODICITE_JOURNALIER. Minuscules, sans espaces,
    sans doublon, dans l'ordre d'apparition."""
```

- [ ] **Étape 1 : tests qui échouent** (J fabriquées par `generer_cloture_pour_tenant` après des
  ventes de `fabriquer_vente_encaissee`, motif `_vendre_des_jus_a` / `_cloturer_a` de
  `test_cloture_unique.py`) :
  - `test_le_z_manuel_d_hier_soir_et_le_filet_de_ce_matin_sont_joints` : vente lundi 20h, Z manuel lundi 23h ; vente lundi 23h30, filet mardi 4h → les deux J, dans l'ordre.
  - `test_un_z_de_ce_matin_10h_n_est_pas_joint` (il appartient au service d'aujourd'hui).
  - `test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe` (motif : `tests/pytest/test_reprise_clotures.py`).
  - `test_une_cloture_hebdomadaire_n_est_pas_jointe`.
  - `test_sans_rubrique_ni_z_il_n_y_a_pas_de_contenu` → `False`.
  - `test_un_stock_sans_nouveau_n_est_pas_du_contenu` → `False`.
  - `test_un_stock_avec_un_nouveau_est_du_contenu` → `True`.
  - `test_un_z_seul_est_du_contenu` → `True`.
  - `test_les_destinataires_sont_les_admins_du_lieu` ; `test_sans_admin_le_mail_du_lieu_sert_de_secours` ;
    `test_rapport_emails_ajoute_en_periodicite_journaliere` ; `test_rapport_emails_ignore_hors_periodicite_journaliere` ;
    `test_un_admin_aussi_dans_rapport_emails_n_est_compte_qu_une_fois` (« Admin@Example.org » et « admin@example.org »).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichier neuf).
- [ ] **Étape 5 : commit suggéré** : `feat(recap): tickets Z de la veille, contenu, destinataires`.

---

### Tâche 6 : l'envoi, le gabarit, le marqueur, l'heure

**Fichiers :**
- Modifier : `Administration/recap_quotidien.py`
- Créer : `BaseBillet/templates/emails/recap_quotidien.html` (`{% extends 'emails/base.html' %}`, styles inline comme `emails/email_generique.html`)
- Test : classe `TestEnvoiDuRecap`

**Interfaces — consomme :** tâches 3-5. **Produit :**

```python
HEURE_D_ENVOI_DU_RECAP = 7

def preparer_le_recap_du_lieu(maintenant, borne_basse_des_z, borne_haute_des_z) -> dict | None:
    """Calcule le récap du lieu courant, sans rien écrire ni envoyer.
    Rend None s'il n'y a pas de contenu, sinon {"configuration", "date_de_la_veille",
    "rubriques", "clotures", "destinataires"}."""

def envoyer_le_recap(recap) -> bool:
    """Sans destinataire : logger.warning, False. Sinon les PDF des Z, puis le mail. True."""

def envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_de_la_veille, seuil_d_aujourd_hui) -> bool:
    """Appelée par comptabilite/tasks.py, dans le tenant_context du lieu.
    Rend True si un mail est parti."""
```

Les deux premières fonctions servent aussi à la démo du flush (tâche 8). Chacune travaille sous
`translation.override(config.language)` : les titres des rubriques (`preparer…`), le sujet `_()`
et `CeleryMailerClass(...)`, qui rend le gabarit dans son `__init__` (`envoyer…`).

L'ordre de `envoyer_le_recap_du_lieu_si_c_est_l_heure` est imposé (spec §4.1) :
1. `config = Configuration.get_solo()` ; `maintenant = timezone.now()` ; `maintenant_local = timezone.localtime(maintenant, config.get_tzinfo())`.
2. Sortir (`False`) si `maintenant_local.hour < HEURE_D_ENVOI_DU_RECAP`, ou si `maintenant < seuil_d_aujourd_hui`, ou si `Configuration.objects.filter(pk=config.pk, recap_quotidien_traite_le=maintenant_local.date()).exists()` (requête, **pas** `get_solo()`).
3. `recap = preparer_le_recap_du_lieu(maintenant, seuil_de_la_veille, seuil_d_aujourd_hui)`.
4. Poser le marqueur : `Configuration.objects.filter(pk=config.pk).update(recap_quotidien_traite_le=maintenant_local.date())` puis `Configuration.clear_cache()`. **Jamais `config.save()`** (il appelle Stripe).
5. `recap is None` → `False`.
6. `return envoyer_le_recap(recap)`. Les PDF (`generer_pdf_cloture(cloture)` → `(octets, nom_du_fichier, _type)`) ne sont fabriqués **que là**, une fois sûr qu'un mail part : WeasyPrint ne tourne pas pour rien. Puis `CeleryMailerClass(email=destinataires, title=…, template="emails/recap_quotidien.html", context=…, attached_files={nom: octets, …}).send()`.

Sujet : `f"[{config.organisation}] " + _("Le récap du %(date)s") % {"date": <veille au format JJ/MM/AAAA>}`.
Contexte du gabarit : `config`, `date_de_la_veille`, `rubriques`, `clotures` (liste de `dict` :
`numero_sequentiel`, `chiffre_affaires_ttc_en_euros` via `euros_a_la_francaise(total_general)`,
`nombre_transactions`, `fin_en_heure_du_lieu` en `%d/%m/%Y %H:%M`), `lien_admin`. Une rubrique :
titre, nombre (« dont N nouvelles » pour un stock), ses lignes, « et N autres » si besoin, bouton
vers `lien`. Chaînes du gabarit en `{% translate %}`, msgid en français.

Les tests remplacent `Administration.recap_quotidien.CeleryMailerClass` par un `MagicMock` et lisent ses arguments.

- [ ] **Étape 1 : tests qui échouent**
  - `test_a_6h10_rien_ne_part` ; `test_a_7h10_le_recap_part` ; `test_un_second_passage_a_8h10_n_envoie_rien`.
  - `test_fermeture_a_6h_rien_a_7h10_envoi_a_8h10` (`heure_de_fermeture=time(6, 0)` : seuil à 8 h).
  - `test_sans_contenu_aucun_pdf_n_est_genere` : `patch("Administration.recap_quotidien.generer_pdf_cloture")` jamais appelé.
  - `test_sans_contenu_pas_de_mail_mais_le_marqueur_est_pose`.
  - `test_sans_destinataire_pas_de_mail_un_avertissement_et_le_marqueur` (`assertLogs`).
  - `test_le_marqueur_est_pose_sans_configuration_save` : `patch.object(Configuration, "save")` → jamais appelé.
  - `test_une_erreur_de_calcul_ne_pose_pas_le_marqueur` : une rubrique qui lève → l'exception remonte, `recap_quotidien_traite_le` reste `None`.
  - `test_les_z_sont_en_piece_jointe` : `attached_files` contient les noms des PDF des deux J.
  - `test_le_mail_est_dans_la_langue_du_lieu` : `language="en"` → un `side_effect` sur le mock de `CeleryMailerClass` relève `translation.get_language()` **au moment de la construction** du mailer → `"en"` (la traduction EN des nouvelles chaînes n'est pas encore compilée : on teste la langue active, pas le texte).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichiers neufs). Contrôle visuel : rendre le gabarit avec un contexte de test et l'ouvrir dans un navigateur (fichier HTML dans le dossier scratchpad), clair et lisible.
- [ ] **Étape 5 : commit suggéré** : `feat(recap): envoi du récap du matin`.

---

### Tâche 7 : brancher le récap sur le filet J, et fusionner avec le mail du Z

**Fichiers :**
- Modifier : `comptabilite/tasks.py` — `generer_les_clotures_automatiques_du_lieu`, `demander_l_email_automatique_si_configure`, en-tête du module, docstrings de `envoyer_email_cloture`
- Modifier : `comptabilite/pdf.py` (en-tête), `laboutik/views.py` (commentaire de `CaisseViewSet.cloturer` sur « l'e-mail automatique de la J »)
- Modifier les tests : `tests/pytest/test_cloture_caisse.py`, `tests/pytest/test_reprise_clotures.py`, `tests/pytest/test_comptabilite_celery.py`, `tests/pytest/test_comptabilite_exports.py`
- Créer : `CHANGELOG/2026-10-18-recap-quotidien-admins.md` (date du jour de la livraison)
- Test : classe `TestBranchementEtFusion`

**Interfaces — consomme :** `envoyer_le_recap_du_lieu_si_c_est_l_heure` (tâche 6).

Dans `generer_les_clotures_automatiques_du_lieu`, **après** la boucle H/M/A, toujours dans le
`tenant_context` : calculer `seuil_d_aujourd_hui = _seuil_du_filet_d_un_jour(maintenant_local.date(), fuseau_du_lieu, configuration.heure_de_fermeture)` et `seuil_de_la_veille` (même appel avec `maintenant_local.date() - timedelta(days=1)`), puis import local et appel de `envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_de_la_veille, seuil_d_aujourd_hui)`.

Dans `demander_l_email_automatique_si_configure` : sortie immédiate si `cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER` (le Z journalier part dans le récap). H/M/A inchangés.

- [ ] **Étape 1 : tests qui échouent**
  - `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` : `heure_de_fermeture=time(5, 0)` (seuil 7 h), vente lundi 23h, **aucun** Z manuel ; tâche horaire mardi 7h10 → le filet crée la J **et** le mock du mailer reçoit son PDF.
  - `test_une_j_ne_demande_plus_de_mail_separe` : périodicité J + `rapport_emails` → `demander_l_email_automatique_si_configure(schema, j)` ne lance aucune tâche (helper `taches_celery_enregistrees` de `fabriques_panier.py`).
  - `test_une_h_demande_toujours_son_mail` (périodicité H).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS.**
- [ ] **Étape 5 : adapter les tests existants** (spec §5) :
  - `test_cloture_caisse.py::test_bouton_lieu_en_periodicite_j_un_seul_email_pour_cette_j` → renommer `test_bouton_lieu_en_periodicite_j_aucun_email_separe` et attendre **zéro** demande de mail ;
  - `test_cloture_caisse.py::test_broker_en_panne_effets_faits_avant_et_ecran_du_z_affiche` → `etats_vus_a_chaque_appel` n'a plus qu'**un** élément (l'impression). `test_envoi_demande_du_z_broker_en_panne_message_clair_pas_d_erreur_500` (bouton « Envoyer par e-mail ») : inchangé ;
  - `test_reprise_clotures.py::test_j_reprise_n_envoie_aucun_mail` → périodicité **hebdomadaire**, et la preuve passe par la tâche horaire du lundi suivant à 4h10 (motif de `test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service`, même fichier). La règle de la mise en service pour les J est désormais portée par `test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe` (tâche 5) ;
  - `test_comptabilite_celery.py::test_envoyer_email_cloture_envoie_si_config_ok`, `test_comptabilite_exports.py::test_email_de_cloture_montre_le_chiffre_d_affaires_ttc` et `::test_email_de_cloture_en_heure_du_lieu` → passer par `envoyer_email_cloture_demande` (le gabarit reste celui du bouton de la caisse).
- [ ] **Étape 6 : vérifier les tests horaires existants** (point de vigilance 5) : `make test ARGS="tests/pytest/test_cloture_unique.py tests/pytest/test_reprise_clotures.py tests/pytest/test_comptabilite_celery.py tests/pytest/test_cloture_caisse.py tests/pytest/test_comptabilite_exports.py tests/pytest/test_recap_quotidien.py"` → tout vert. Tests horaires existants qui tournent **après 7h** heure locale et joignent une J
  (relevé du 2026-10-18) : `test_cloture_unique.py::test_filet_apres_un_z_la_vente_du_lendemain_soir_attend_le_seuil_suivant`
  (19 h) et `test_cloture_unique.py::test_filet_ne_cree_qu_une_j_par_jour…` (16 h). Leur schéma n'a
  ni admin ni `Configuration.email` → `logger.warning`, aucun PDF, aucun envoi. Tous les autres
  appels de la tâche horaire sont avant 7h. Si l'un échoue, remplacer
  `Administration.recap_quotidien.CeleryMailerClass` dans ce test, jamais affaiblir le code.
- [ ] **Étape 7 : CHANGELOG** au format `djc` (résumé bilingue, « Migration : Oui » avec les deux migrations, `---`, scénarios de test manuel : un lieu de dev, des objets d'hier, `generer_les_clotures_automatiques_du_lieu` lancée à la main à 7h via `manage.py shell` avec `timezone.now` patché, mail vu dans la boîte de dev). Mettre à jour [INDEX.md](INDEX.md).
- [ ] **Étape 8 : rapport final** : mutations vues échouer, nombre de chaînes traduisibles ajoutées (workflow i18n au mainteneur), migrations à appliquer, demande d'accord pour lancer la suite complète.
- [ ] **Étape 9 : commit suggéré** : `feat(recap): récap du matin branché sur le filet J, fin du mail Z séparé`.

---

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
