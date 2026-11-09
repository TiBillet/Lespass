# RECAP_QUOTIDIEN — Chantier 02 : un récap plus court, et des compteurs dans les rapports H/M

> **Status :** spec du 2026-10-22. **Codée le 2026-10-22** (§2, §3, §5 ; non commité). Fiche : `CHANGELOG/2026-10-22-recap-allege.md`.
> **Hub :** [INDEX.md](INDEX.md) · **Chantier 01 :** [SPEC.md](SPEC.md) (le récap tel qu'il est).
> **Consigne : pas de sur-ingénierie, conformité `djc`. Deux migrations (§5.5) : `comptabilite` (singleton + données) puis `BaseBillet` (suppression de deux champs).**
>
> **Décisions du mainteneur (2026-10-22) :**
> - **tout objet du récap quotidien est né la veille**, même s'il est en attente : plus de
>   « stock » qui remonte chaque matin les vieilles demandes ;
> - les rubriques « en attente » qui font doublon avec une rubrique « nouveaux » sont **retirées** ;
> - une ligne **« Tombés en rupture hier »** pour les articles d'inventaire passés à 0 ou moins la veille ;
> - plus de gros bouton « Ouvrir l'administration » par rubrique (N) ;
> - le financement participatif tient en **une seule rubrique**, une ligne par projet, avec des
>   compteurs (C) ; les votes sont **comptés** par projet, pas listés (D) ;
> - le statut n'est écrit que **s'il apprend quelque chose** (E) ;
> - **5 lignes** au plus par rubrique (F) ;
> - remboursements et annulations : **une seule rubrique** (G) ;
> - ce qui **demande une action** passe en tête (H) ;
> - les **rapports de clôture hebdomadaire et mensuel** (mails Z H/M existants) reçoivent des
>   **compteurs** de l'activité de la période, sans détail. Le détail reste au récap quotidien.
>
> **Relue le 2026-10-22 par un agent Fable** (exactitude face au code) : corrections intégrées.
> Le §5 a eu sa propre relecture Fable le même jour : corrections intégrées.
> **Arbitrages du mainteneur après relecture (2026-10-22) :** les ajustements d'inventaire ne
> comptent pas comme rupture ; annulations et remboursements = **deux** compteurs dans les H/M ;
> une annulation écrit son statut réel ; « dont N propositions » gardé (état à l'envoi).
>
> **Réglages des envois (2026-10-22, §5) :** un singleton dans `comptabilite` avec un booléen par
> périodicité (J, H, M, A) et une liste de destinataires choisis parmi les users du lieu. **La liste
> seule** reçoit (plus d'admins d'office) ; **pas d'adresse libre** ; les anciens champs
> `Configuration.rapport_emails` / `rapport_periodicite` sont **copiés puis supprimés** ; par
> défaut **tout est coché**. Lien de désabonnement en pied de mail vers la page des réglages
> (réservée aux admins, accepté). **La liste est vide par défaut** : la migration n'y met aucun
> admin (les lieux existants ne reçoivent plus le récap sauf s'ils s'inscrivent) ; seul
> l'**onboarding** ajoute le premier admin d'un nouveau lieu.

---

## 1. Pourquoi

Le récap du chantier 01 est trop long :
- les cinq rubriques « en attente » montrent **tout le stock** : une demande oubliée depuis un mois
  revient chaque matin ;
- une fois ces stocks bornés à la veille, trois d'entre eux (propositions, lignes de budget,
  participations) deviennent des **sous-ensembles exacts** d'une rubrique « nouveaux » ;
- jusqu'à 17 gros boutons bleus, dont 7 pointent sur la même liste (les initiatives) ;
- le financement participatif occupe 7 rubriques, et chaque vote est une ligne ;
- le statut est répété sur chaque ligne, même quand il est le statut normal ;
- un même remboursement apparaît deux fois (« Remboursements » et « Annulations — remboursé »).

---

## 2. Le récap quotidien

### 2.1 Les rubriques, dans l'ordre

La fenêtre ne change pas : `fenetre_de_la_veille` (minuit à minuit, heure du lieu). **Toutes** les
rubriques filtrent sur cette fenêtre.

| # | Rubrique | Source | Filtre | Date |
|---|---|---|---|---|
| **À valider** | | | | |
| 1 | Demandes d'adhésion en attente | `Membership` | `status=ADMIN_WAITING` | `date_added` dans la fenêtre |
| 2 | Demandes de réservation de ressources en attente | `booking.Booking` | `status=ADMIN_WAITING` ; le lien garde son filtre `?status__exact=WA` | `booked_at` dans la fenêtre |
| **Inventaire** | | | | |
| 3 | Tombés en rupture hier | `inventaire.MouvementStock` | voir §2.3 | `cree_le` dans la fenêtre |
| **Nouveautés** | | | | |
| 4 | Nouvelles adhésions | `Membership` | inchangé (chantier 01) | `date_added` |
| 5 | Nouvelles réservations | `Reservation` | inchangé | `created_at` |
| 6 | Nouvelles réservations de ressources | `booking.Booking` | inchangé | `booked_at` |
| 7 | Nouvelles inscriptions de bénévoles | `InscriptionBenevole` | inchangé | `created_at` |
| 8 | Nouveaux événements | `Event` | inchangé (une proposition y est marquée « proposition en attente ») | `created_at` |
| 9 | Financement participatif | `crowds.*` | voir §2.4 | voir §2.4 |
| 10 | Annulations et remboursements | `Reservation`, `Booking`, `Membership`, `LigneArticle` | voir §2.5 | voir §2.5 |
| **Caisse** | | | | |
| — | Tickets Z | `ClotureCaisse` niveau J | inchangé (chantier 01 §3.1) | — |

Les adhésions et les réservations de ressources gardent leur rubrique « à valider » : leur rubrique
« nouvelles » **exclut déjà** `ADMIN_WAITING`, il n'y a pas de doublon.

Une demande créée hier et validée avant l'envoi du récap n'est plus « en attente » : elle tombe dans
la rubrique « nouvelles » si son statut y entre, sinon nulle part. C'est voulu : le récap montre
l'état au moment de l'envoi.

### 2.2 Ce qui disparaît

- Les rubriques `propositions_en_attente`, `lignes_de_budget_en_attente`,
  `participations_en_attente` (doublons de « nouveaux »).
- Les rubriques `nouveaux_projets`, `nouvelles_lignes_de_budget`, `contributions_payees`,
  `nouveaux_votes`, `nouvelles_participations` : remplacées par la rubrique 9.
- Les rubriques `remboursements` et `annulations` : remplacées par la rubrique 10.
- La notion de **stock** : les clés `est_un_stock` et `nombre_de_nouveaux` du dict de rubrique,
  le paramètre `est_un_stock` de `_construire_la_rubrique`, la phrase « dont N nouvelles hier » du
  gabarit.
- `le_recap_a_du_contenu` se simplifie : **une rubrique non vide ou un Z suffit**. Le §3.5 du
  chantier 01 (« un stock ne déclenche pas le mail à lui seul ») n'a plus d'objet.

Conséquence assumée : une vieille demande oubliée **n'est plus rappelée** par le récap. Le mail en
temps réel « adhésion en attente » ne change pas.

### 2.3 Tombés en rupture hier

**Une seule ligne**, pas une liste : « Bière blonde, Chips, Sirop de menthe ».

Un article est « tombé en rupture hier » s'il existe au moins un `MouvementStock` :
- `cree_le` dans la fenêtre ;
- `type_mouvement` différent de `TypeMouvement.AJ` (décision du mainteneur, 2026-10-22 : un
  ajustement d'inventaire est une correction faite par l'admin, pas une rupture) ;
- `quantite_avant > 0` ;
- `quantite_avant + quantite <= 0`.

Un article déjà à 0 avant-hier n'y est pas (il n'est pas *tombé* hier). Un article tombé à 0 puis
réapprovisionné dans la journée y est (il a été en rupture hier). Un article compté une fois même
s'il est tombé deux fois.

Noms des produits (`stock.product.name`) par ordre alphabétique. Au-delà de 5 noms : « … et N
autres ». Le lien : `https://{domaine}/admin/inventaire/stock/` (`StockAdmin`, enregistré sur
`staff_admin_site`, `Administration/admin/inventaire.py:100`).

Le dict de rubrique garde sa forme : `nombre` = nombre d'articles, `lignes` = **une** chaîne
(les noms joints par « , »), `nombre_de_lignes_cachees` = 0 (le « et N autres » est dans la chaîne).
**Piège :** `_dict_de_la_rubrique` calcule `nombre_de_lignes_cachees = nombre - len(lignes)`. La
rubrique rupture ne passe donc pas par `_construire_la_rubrique` ; elle construit son dict et force
`nombre_de_lignes_cachees` à 0, sinon le gabarit écrirait « et N autres » deux fois.

Les mouvements qui peuvent faire tomber un article (`inventaire/services.py`) : ventes (`VE`),
offerts (`OF`), pertes (`PE`), débit mètre (`DM`) — les sorties réelles. Une réception est positive et ne déclenche jamais. Aucun
mouvement inverse n'est écrit à l'annulation d'une vente. `quantite_avant` est lu en mémoire
(`services.py:71`) : deux caisses simultanées peuvent écrire le même `quantite_avant` ; le
dédoublonnage par produit absorbe le cas.

### 2.4 Financement participatif

Une ligne **par projet touché hier**. Un projet est touché s'il a, dans la fenêtre :
- été créé (`Initiative.created_at`) ;
- ou reçu une ligne de budget (`BudgetItem.created_at`) ;
- ou une contribution payée (`Contribution.paid_at`, `payment_status` `PAID` ou `PAID_ADMIN`, comme
  au chantier 01) ;
- ou un vote (`Vote.created_at`) ;
- ou une demande de participation (`Participation.created_at`).

La ligne : le nom du projet, puis les seuls compteurs non nuls, séparés par « , » :

> Jardin partagé — nouveau projet, 2 lignes de budget dont 1 à valider, 3 contributions (45,00 €),
> 12 votes, 1 participation dont 1 à valider

- « à valider » : `BudgetItem.State.REQUESTED`, `Participation.State.REQUESTED`, au moment de l'envoi.
- Le montant des contributions : leur somme, dans la devise du projet
  (`_montant_dans_la_devise_du_projet`, inchangée).
- Pluriels par `ngettext`.

Ordre des projets : le plus d'éléments d'abord (somme des compteurs, « nouveau projet » vaut 1),
puis le nom. 5 projets au
plus, puis « et N autres ». `nombre` = nombre de projets touchés. Lien : la liste des initiatives.

### 2.5 Annulations et remboursements

Une ligne **par objet**, jamais deux.

1. Les objets annulés hier (`annulee_le` dans la fenêtre), comme au chantier 01 : réservations,
   réservations de ressources, adhésions.
2. Les lignes d'avoir écrites hier (`LigneArticle`, `status` `REFUNDED` ou `CREDIT_NOTE`, `datetime`
   dans la fenêtre), comme l'ancienne rubrique « Remboursements ».

Fusion :
- un objet annulé hier qui a **au moins une** ligne d'avoir (d'hier ou d'avant — comme le
  « remboursé » actuel) : une ligne « Personne — Objet — remboursé 12,00 € ». Le montant est
  la somme de `-total_ttc` de **toutes** ses lignes d'avoir, quelle que soit leur date ;
- une ligne d'avoir d'hier dont l'objet (`reservation`, `booking`, `membership`) n'est **pas** annulé
  hier, ou qui n'a pas d'objet (article de caisse) : regroupée par objet, une ligne « Objet —
  remboursé 12,00 € » (nommage : `_nom_de_l_objet_rembourse`, inchangé) ;
- un objet annulé hier sans aucune ligne d'avoir : « Personne — Objet — Statut ».

Le mot de l'annulation est le **statut réel** de l'objet (`get_status_display()`), pas « annulé » :
il dit qui a annulé (`Booking.USER_CANCELED` / `ADMIN_CANCELED`, `Membership.ADMIN_CANCELED`…).
Décision du mainteneur (2026-10-22), conforme à la règle E. Exemple : « Léa Martin — Salle de
répétition — Annulée par l'utilisateur — remboursé 12,00 € ».

Ordre : le plus récent d'abord (`annulee_le`, ou la date de la dernière ligne d'avoir). 5 lignes au
plus. Lien : la liste des ventes (`/admin/BaseBillet/vente/`), qui porte les avoirs.

Cas limites :
- la ligne d'avoir **copie** `reservation`, `membership` et `booking` de la ligne d'origine
  (`BaseBillet/services_vente.py:895-897`) : le regroupement par objet se fait sur ces FK, sans
  passer par `credit_note_for` ;
- une réservation de 3 billets remboursée = 3 lignes d'avoir, mais **une** ligne dans la rubrique ;
- annulation **partielle** d'une réservation (un billet sur deux, `BaseBillet/models.py:3851-3863`) :
  `annulee_le` reste nul, l'avoir tombe dans le cas « Objet — remboursé », sans la personne ;
- hérité du chantier 01 : `Membership.annulee_le` n'est posé que par l'annulation admin
  (`BaseBillet/views.py:6060`). Une adhésion annulée par un autre chemin n'entre pas dans la rubrique.

### 2.6 La forme du mail

- **Plus de bouton par rubrique.** Le titre de la rubrique devient un lien (couleur `#2d76a6`,
  sans fond). Le lien « Ouvrir l'administration » du bas reste.
- **5 lignes** au plus : `NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE = 5`.
- **Pied du mail : le lien de désabonnement** (§5.7).
- Les quatre groupes (« À valider », « Inventaire », « Nouveautés », « Caisse ») n'ont **pas**
  d'intertitre : l'ordre suffit. (Pas de sur-ingénierie ; à revoir si le mainteneur le demande.)

### 2.7 Le statut sur une ligne (E)

Le statut n'est écrit que s'il n'est pas le statut **normal** de la rubrique.

| Rubrique | Statut tu (normal) | Statut écrit |
|---|---|---|
| Demandes en attente (1, 2) | `ADMIN_WAITING` — toujours tu, le titre le dit | — |
| Nouvelles adhésions | `ONCE`, `AUTO`, `ADMIN`, `LABOUTIK` | `ADMIN_VALID`, `PAYMENT_PENDING`, `IMPORT` |
| Nouvelles réservations | `VALID`, `PAID`, `FREERES_USERACTIV` | `FREERES`, `PAID_ERROR`, `PAID_NOMAIL` |
| Nouvelles réservations de ressources | `PAID_BY_USER`, `NO_ADMIN_VALID`, `FREERES_USERACTIV` | `ADMIN_VALID`, `FREERES` |
| Nouveaux événements | « publié » | « brouillon », « proposition en attente » |

Les deux colonnes couvrent tous les statuts qui restent après les `exclude` de chaque rubrique
(vérifié à la relecture). Un statut ajouté plus tard, absent des deux colonnes, est **écrit** : par
défaut, on informe.

---

## 3. Les rapports de clôture hebdomadaire et mensuel

### 3.1 Où

Le mail existant de la clôture H ou M : `_envoyer_l_email_de_la_cloture` (`comptabilite/tasks.py`),
gabarit `comptabilite/templates/comptabilite/email/cloture_rapport_email.html`. On n'ajoute **ni
mail, ni tâche, ni réglage**.

Limites assumées (choix du mainteneur) : ce mail ne part que si le lieu a une clôture H/M (donc des
ventes en caisse), que le booléen du niveau est coché et que la liste des destinataires n'est pas
vide (§5).
(`envoyer_email_cloture_demande` passe par la même fonction, mais n'a aucun appelant aujourd'hui.)

Niveaux concernés : **H et M**. Pas J (le Z J est dans le récap quotidien), pas A (non demandé).
La même fonction envoie aussi le mail A : le bloc n'est ajouté que si
`cloture.niveau in (NIVEAU_HEBDOMADAIRE, NIVEAU_MENSUEL)`.

### 3.2 Quoi

Un bloc « L'activité de la période » : une liste de compteurs **non nuls**, sans aucun détail.

> 12 nouvelles adhésions · 3 demandes d'adhésion · 48 nouvelles réservations · 5 réservations de
> ressources · 2 demandes de réservation de ressources · 9 inscriptions de bénévoles ·
> 4 nouveaux événements (dont 1 proposition) · 2 nouveaux projets · 7 contributions · 31 votes ·
> 3 participations · 6 annulations · 4 remboursements · 3 articles tombés en rupture

La période : `[cloture.datetime_debut, cloture.datetime_fin[`, les bornes de la clôture elle-même.
Chaque compteur reprend **exactement le filtre** de la rubrique quotidienne correspondante, sur
cette période au lieu de la veille. Les compteurs de financement participatif sont ceux du §2.4,
additionnés sur tous les projets.

**Deux compteurs** pour la rubrique 10 (décision du mainteneur, 2026-10-22) :
- « annulations » = objets dont `annulee_le` est dans la période ;
- « remboursements » = **lignes d'avoir** de la période (`LigneArticle` `REFUNDED`/`CREDIT_NOTE`).
  Une réservation de 3 billets remboursée compte donc 3. Un objet annulé et remboursé compte dans
  les deux. Le périmètre est celui de l'ancienne rubrique « Remboursements » du récap (caisse
  comprise) : il diffère de la section « Remboursements » du PDF du Z, qui exclut
  `sale_origin=LABOUTIK` (`comptabilite/services.py:59`, `:170`). On ne les aligne pas.

**« dont N propositions »** : parmi les nouveaux événements de la période, ceux qui sont
`is_proposal=True` et `published=False` **au moment de l'envoi** (même règle que
`_etat_d_un_evenement`). Le sous-compteur n'est écrit que s'il est non nul.

Aucun compteur non nul : pas de bloc (le mail du Z part quand même, comme aujourd'hui).

Le pied du mail H/M/A reçoit le même lien de désabonnement que le récap (§5.7).

**Langue :** aujourd'hui, `_envoyer_l_email_de_la_cloture` ne pose aucune langue : le mail part dans
la langue courante du worker Celery (`fr` par défaut, ou celle laissée par une tâche précédente qui
a fait `activate()` sans restaurer). Le bloc des compteurs doit être dans la langue du lieu : on
enveloppe **tout** le rendu du mail dans `translation.override(configuration.language)`, comme le
récap. C'est un changement pour tout le mail H/M/A (gabarit existant et `get_niveau_display()` du
sujet). Le littéral « Clôture » du sujet (f-string, `comptabilite/tasks.py:1230-1234`) n'est pas
traduit : on le laisse tel quel (hors périmètre).

### 3.3 Comment, sans dupliquer

Les filtres vivent **une seule fois**, dans `Administration/recap_quotidien.py` : une fonction par
source rend l'ensemble filtré sur `[debut, fin[` (ex. `_nouvelles_adhesions(debut, fin)`). La
rubrique quotidienne l'utilise pour ses lignes, `compteurs_de_la_periode(debut, fin)` pour son
`.count()`. `comptabilite/tasks.py` importe `compteurs_de_la_periode` en import local, dans
`_envoyer_l_email_de_la_cloture` : même convention que l'import du récap déjà en place
(`comptabilite/tasks.py:1078`). Pas de cycle réel.

---

## 4. Tests

### 4.1 Tests impactés (`tests/pytest/test_recap_quotidien.py`)

- Tous les tests « stock » (adhésions, demandes de réservation, propositions, lignes de budget,
  participations en attente) : réécrits ou supprimés. Une vieille demande en attente **n'apparaît
  plus**.
- Les tests de `le_recap_a_du_contenu` sur les stocks (`une_rubrique(cle, est_un_stock, …)`) :
  réécrits sans la notion de stock.
- Le test « stock sans nouveau + Z d'avant-hier » (vers la ligne 1579) : à revoir.
- Les tests des rubriques crowds, remboursements et annulations : réécrits sur les rubriques 9 et 10.
- `test_une_rubrique_de_douze_lignes_en_montre_dix` (≈ l. 529) et
  `test_une_rubrique_d_annulations_de_douze_lignes_en_montre_dix` (≈ l. 1178) : passent à 5 lignes.
- `test_le_gabarit_montre_les_rubriques_et_les_z` (≈ l. 1737) : passe `est_un_stock` et attend
  « dont 3 nouvelles hier » ; `test_le_gabarit_echappe_les_noms_saisis` (≈ l. 1775) : retirer
  `est_un_stock` du dict.
- `tests/pytest/test_demo_recap_de_la_veille.py` (l. 268-276) : la clé `annulations` devient celle
  de la rubrique 10 ; `adhesions_en_attente` reste (la demande de démo est d'hier,
  `_demo_data_v2_recap.py:183-186`). La commande de démo elle-même ne cite aucune clé.

### 4.2 Tests nouveaux

- Une demande d'adhésion en attente d'avant-hier n'est pas dans le récap ; celle d'hier y est.
- Idem pour une demande de réservation de ressource.
- Rupture : un mouvement d'hier de 3 à 0 → l'article y est ; de 0 à -1 → il n'y est pas ; de 3 à
  -2 → il y est ; un mouvement d'avant-hier → il n'y est pas ; deux chutes le même jour → un seul nom ;
  un ajustement (`AJ`) de 5 à 0 → il n'y est pas.
- Financement : un projet avec 2 votes et 1 contribution d'hier → une ligne, compteurs exacts ;
  un projet sans activité hier → absent.
- Annulations et remboursements : une réservation annulée hier avec un avoir → **une** ligne avec
  le montant ; un avoir de caisse sans objet → une ligne ; un objet annulé sans avoir → « annulé ».
- Statut : une adhésion `ONCE` sans statut écrit, une `PAYMENT_PENDING` avec.
- 6 adhésions → 5 lignes + « et 1 autre ».
- Compteurs H/M : un mail de clôture H contient les compteurs de sa période et pas ceux d'avant ;
  pas de bloc quand tout est nul.

---

### 4.3 Tests des réglages (§5)

- **27 fichiers** sous `tests/pytest/` posent `rapport_emails` / `rapport_periodicite` sur
  `Configuration` (relevé Fable du 2026-10-22). Seuls **10** cassent tout seuls, ceux qui citent
  `Configuration.PERIODICITE_*` (à condition de supprimer ces constantes) : test_api_v2_comptabilite,
  test_api_v2_ventes_comptables, test_cloture_caisse, test_comptabilite_celery,
  test_demo_recap_de_la_veille, test_demo_ventes_de_la_veille, test_rapport_temps_reel,
  test_recap_en_cours_coherence_admin, test_recap_quotidien, test_reprise_clotures. Les **17 autres**
  font seulement `configuration.rapport_emails = ""` : après la suppression du champ, c'est un
  attribut Python muet et le test **reste vert**. La ligne se supprime (liste vide par défaut =
  aucun mail, même effet). **Le plan part du `rg`, pas des tests rouges.**
- `tests/pytest/test_demo_recap_de_la_veille.py:181-185` crée l'admin sans `client_achat` : même
  ajouté à la liste, il n'est pas rendu par `destinataires.all()` (manager de `HumanUser`). Lui
  ajouter `client_achat.add(self.tenant)` (ou passer par `get_or_create_user`).
- J décoché → aucun récap, et le marqueur `recap_quotidien_traite_le` n'est pas posé.
- H coché, M décoché → la clôture H envoie son mail, la M non.
- Liste vide → aucun mail, aucun niveau.
- Les destinataires sont les e-mails des users de la liste, et eux seuls (un admin hors liste ne
  reçoit rien).
- Admin : l'autocomplétion ne propose que les users du lieu ; un pk d'un user d'un autre lieu posté
  à la main est refusé.
- Migration de données : périodicité `H` + deux e-mails dont un connu → J et H cochés, M et A
  décochés, la liste contient le user connu et aucun admin ; l'e-mail inconnu est écrit dans la
  sortie de la migration.

---

## 5. Les réglages des envois (singleton de la comptabilité)

### 5.1 Le modèle

Aucun singleton n'existe dans `comptabilite/models.py`. On en crée un :

```python
class ConfigurationDesRapports(SingletonModel):
    envoyer_le_recap_quotidien = models.BooleanField(default=True)     # J
    envoyer_le_rapport_hebdomadaire = models.BooleanField(default=True)  # H
    envoyer_le_rapport_mensuel = models.BooleanField(default=True)       # M
    envoyer_le_rapport_annuel = models.BooleanField(default=True)        # A
    destinataires = models.ManyToManyField("AuthBillet.HumanUser", blank=True)
```

Chaque champ a un `verbose_name` et un `help_text` en français : `tests/pytest/test_admin_verbose_name.py`
balaie tous les admins, ils sont obligatoires.

- **Les booléens se cumulent** : on peut cocher J, H et M à la fois. Aujourd'hui, un lieu ne
  choisit qu'une seule périodicité.
- **Une seule liste** pour toutes les périodicités.
- **Le M2M vise `HumanUser`**, pas `TibilletUser` : son manager (`AuthBillet/models.py:416`) ne
  rend que les users du lieu courant (`client_achat`). C'est ce queryset qui **valide** les pk
  postés par le formulaire : un pk forcé vers un user d'un autre lieu est refusé (`HumanUserAdmin`
  n'a pas d'`ordering`, le formfield prend donc `HumanUser._default_manager`). C'est le **premier**
  M2M du projet vers ce proxy (`History.user`, `BaseBillet/models.py:5731`, vise `TibilletUser`).
  Ça fonctionne : la FK vise la table concrète `authbillet_tibilletuser`, `comptabilite` est en
  TENANT_APPS seul et `AuthBillet` en SHARED_APPS seul.
- **Piège : `.add()` exige un `HumanUser`.** Ajouter un `TibilletUser` (ce que rend
  `get_or_create_user`) lève `TypeError: 'HumanUser' instance expected`. Toujours écrire
  `destinataires.add(user.pk)` (onboarding, démos, tests).
- Un user qui quitte `client_achat` du lieu disparaît en silence des destinataires
  (`destinataires.all()` passe par le manager filtré). Accepté.
- **Un admin est toujours un `HumanUser` du lieu** (vérifié le 2026-10-22). Tous les chemins qui
  créent un admin passent par `get_or_create_user` dans le `tenant_context` du lieu, qui ajoute
  le lieu à `client_achat` (`AuthBillet/utils.py:122`) : onboarding (`BaseBillet/validators.py:1457`),
  `install`, `batch_new_tenant`. `set_staff` ajoute les deux (`AuthBillet/models.py:313-314`).
  Le bouton « droit admin » de l'admin (`BaseBillet/views.py:866`) part d'un `HumanUser`.
  Seuls des comptes de **test** en base de dev sont admins sans `client_achat` (3 sur 8, créés
  par les fixtures). La migration ne met aucun admin dans la liste (§5.5) : pas de filet à prévoir.

### 5.2 Qui reçoit

**La liste, et elle seule.** Plus d'admins d'office, plus de repli sur `Configuration.email`, plus
d'adresse libre. Liste vide = aucun mail (récap et rapports).

`destinataires_du_recap` (`Administration/recap_quotidien.py`) et les destinataires de
`_envoyer_l_email_de_la_cloture` (`comptabilite/tasks.py`) lisent la même liste : les e-mails des
users, en minuscules, sans espaces, sans doublon, sans vide.

Un cabinet comptable sans compte : on lui crée un compte, il apparaît dans la recherche dès qu'il
est user du lieu.

### 5.3 Ce que pilotent les booléens

| Booléen | Effet quand il est décoché |
|---|---|
| J | `envoyer_le_recap_du_lieu_si_c_est_l_heure` rend False tout de suite, **sans poser** le marqueur `recap_quotidien_traite_le`. Aucun récap, donc aucun Z journalier envoyé (il reste téléchargeable dans l'admin). |
| H, M, A | `demander_l_email_automatique_si_configure` ne demande pas le mail du niveau. `_envoyer_l_email_de_la_cloture` relit le booléen (le test `respecter_la_periodicite` devient « le booléen du niveau est coché »). |

### 5.4 L'admin

- `comptabilite/admin.py` : `ConfigurationDesRapportsAdmin(SingletonModelAdmin, ModelAdmin)`,
  enregistré sur `staff_admin_site`, `autocomplete_fields = ["destinataires"]` (appuyé sur
  `HumanUserAdmin` et ses `search_fields`, `Administration/admin_tenant.py:1272`), permissions
  `TenantAdminPermissionWithRequest` comme les autres pages de la compta. `SingletonModelAdmin` pose
  déjà `has_add_permission` / `has_delete_permission` à False : seuls `has_view_permission` et
  `has_change_permission` sont à écrire. Modèle à copier : `controlvanne/admin.py:902-932` (sans son
  `has_add_permission`).
- Accès :
  - menu : un dict `{"title", "icon", "link": _safe_rev("staff_admin:comptabilite_configurationdesrapports_changelist"), "permission": admin_permission}`
    dans `items_ventes_et_comptabilite` (`Administration/admin/dashboard.py:1002-1017`, section
    toujours visible, même sans caisse) ;
  - bouton sur la liste des clôtures : la carte existante
    `comptabilite/templates/comptabilite/admin/changelist_before.html` (`ClotureCaisseAdmin.list_before_template`,
    URL posée par `changelist_view` dans `extra_context`, `comptabilite/admin.py:111-127`).
  Skill `unfold` au plan.

### 5.5 La migration

Deux migrations, dans l'ordre :

1. **`comptabilite`** : crée `ConfigurationDesRapports`, puis une **migration de données** (garde
   `schema_name == "public"` → return, cf. skill `djc`) qui crée le singleton de chaque lieu.
   Dépend de la dernière migration `BaseBillet` (pas de cycle : vérifié). Précisions d'écriture :
   - le modèle historique n'a pas `get_solo()` : `update_or_create(id=1, ...)`, comme
     `BaseBillet/migrations/0225` ; `Configuration.objects.first()` peut être `None` → return ;
   - le manager historique de `HumanUser` ne filtre rien : filtrer à la main,
     `HumanUser.objects.filter(espece="HU", client_achat__schema_name=connection.schema_name, email__in=[...])`
     (jamais `connection.tenant.pk` en migration ; `test_modele` n'a pas de `Client`) ;
   - les e-mails de `rapport_emails` passent en minuscules et sans espaces avant le `email__in`
     (`HumanUser.save` force la minuscule).

   Le contenu :
   - `rapport_periodicite == NONE` (le défaut, presque tous les lieux) → **tout coché** ;
   - `rapport_periodicite == X` (X = J, H, M ou A) → J coché (le récap partait déjà aux admins) et X
     coché, le reste décoché ;
   - la liste : **aucun admin** (décision du mainteneur, 2026-10-22 : « plus safe ») ; seulement
     les users du lieu dont l'e-mail figure dans `rapport_emails` (quelqu'un a demandé ces envois) ;
   - les e-mails de `rapport_emails` **sans user** du lieu sont **perdus** : la migration les écrit
     dans sa sortie (`print`, avec le schéma) pour que le mainteneur les relève.

   **Conséquence : après la migration, les lieux existants ne reçoivent plus rien** (ni récap du
   matin, ni rapports H/M/A), sauf les users venus de `rapport_emails`. Un admin qui veut le récap
   s'inscrit sur la page des réglages.
2. **`BaseBillet`** : supprime `Configuration.rapport_emails` et `Configuration.rapport_periodicite`
   **et les constantes `PERIODICITE_*`** (`BaseBillet/models.py:746-757`) : hors tests, seuls ce champ
   et `destinataires_du_recap` les lisent. Recommandé par la relecture : les garder laisserait des
   tests verts en silence. Dépend de la migration 1.

Pour mémoire : aujourd'hui les mails H/M/A ne partent qu'aux adresses de `rapport_emails`
(`comptabilite/tasks.py:837`, `:1208`), jamais aux admins d'office ; les admins reçoivent d'office
le récap du matin (`destinataires_du_recap`) et les mails en temps réel (inchangés).
`rapport_emails` n'a aucune interface d'édition (ni admin, ni API) : il n'est rempli que là où
quelqu'un l'a posé au shell. Relevé à faire en prod avant la migration.

Les champs `LaboutikConfiguration.rapport_emails` / `rapport_periodicite` (ancienne caisse, plus
lus) ne sont pas touchés ici.

### 5.6 Un nouveau lieu

`get_solo()` crée le singleton avec tout coché, mais **une liste vide**.

**Décision du mainteneur (2026-10-22) : seul l'onboarding ajoute le premier admin à la liste**
(`BaseBillet/validators.py`, juste après `user.client_admin.add(tenant)`, ≈ l. 1458, dans le
`tenant_context` du lieu ; `client_achat` y est déjà posé par `get_or_create_user`). Écrire
`ConfigurationDesRapports.get_solo().destinataires.add(user.pk)` — par pk, cf. §5.1. Pas de signal. Un admin ajouté plus tard (bouton « droit admin »,
`batch_new_tenant`, `install`, démos) **s'ajoute lui-même** à la liste depuis la page des réglages.

Les commandes de démo (`demo_data_v2`…) peuvent ajouter leur admin à la liste pour que le récap de
démo parte (`tests/pytest/test_demo_recap_de_la_veille.py`) : relevé au plan.

### 5.7 Le lien de désabonnement

Demande du mainteneur (2026-10-22). En pied du récap quotidien **et** des mails de clôture H/M/A :

> Vous pouvez vous désabonner de cette lettre d'information : [réglages des envois](lien)

- Le lien : la page du singleton dans l'admin du lieu,
  `https://{domaine}/admin/comptabilite/configurationdesrapports/`, construit par
  `reverse("staff_admin:comptabilite_configurationdesrapports_changelist")` (le nom `_changelist`,
  comme le menu ; solo déclare deux routes `_change`).
- Le contexte du mail de clôture n'a pas de domaine aujourd'hui : l'ajouter depuis
  `tenant.get_primary_domain().domain` (`tenant` est déjà là dans `_envoyer_l_email_de_la_cloture`).
- Dans `cloture_rapport_email.html`, la phrase « Envoyé automatiquement… demandez à un
  administrateur du tenant de modifier la configuration » est **un seul msgid** : on le remplace en
  entier (nouvelle chaîne à traduire).
- Ce n'est **pas** un lien de désabonnement en un clic : la page est réservée aux admins du lieu.
  Un destinataire qui n'est pas admin (un comptable) arrive sur l'écran de connexion de l'admin et
  doit demander à un admin. Accepté pour la v1 ; un vrai lien « en un clic » (jeton signé, sans
  connexion) serait un autre chantier.

---

## 6. Documentation et suivi

- `SPEC.md` : une note en tête du §3.2 et du §3.5, « remplacé par le chantier 02 ».
- `INDEX.md` : le chantier 02 dans la table.
- `PLAN.md` et `SUIVI/` citent les clés supprimées : archive du chantier 01, on n'y touche pas ;
  une ligne « périmé par le chantier 02 » en tête de `PLAN.md`.
- `CHANGELOG/2026-10-22-recap-allege.md` : migration **Oui** (les deux du §5.5, avec la commande `migrate_schemas`).
- i18n : nouvelles chaînes (titres, compteurs, pluriels) → **signaler au mainteneur**, ne pas lancer
  `makemessages`.
