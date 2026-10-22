# RECAP_QUOTIDIEN — Chantier 02 : un récap plus court, et des compteurs dans les rapports H/M

> **Status :** spec du 2026-10-22. **Pas encore de code.**
> **Hub :** [INDEX.md](INDEX.md) · **Chantier 01 :** [SPEC.md](SPEC.md) (le récap tel qu'il est).
> **Consigne : pas de sur-ingénierie, conformité `djc`. Aucune migration.**
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
| **Stock** | | | | |
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
- `quantite_avant > 0` ;
- `quantite_avant + quantite <= 0`.

Un article déjà à 0 avant-hier n'y est pas (il n'est pas *tombé* hier). Un article tombé à 0 puis
réapprovisionné dans la journée y est (il a été en rupture hier). Un article compté une fois même
s'il est tombé deux fois.

Noms des produits (`stock.product.name`) par ordre alphabétique. Au-delà de 5 noms : « … et N
autres ». Le lien pointe sur la liste des stocks de l'admin (`Administration/admin/inventaire.py`,
`StockAdmin`) — chemin exact à relever au plan.

Le dict de rubrique garde sa forme : `nombre` = nombre d'articles, `lignes` = **une** chaîne
(les noms joints par « , »), `nombre_de_lignes_cachees` = 0 (le « et N autres » est dans la chaîne).

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
> 12 votes, 1 participation à valider

- « à valider » : `BudgetItem.State.REQUESTED`, `Participation.State.REQUESTED`, au moment de l'envoi.
- Le montant des contributions : leur somme, dans la devise du projet
  (`_montant_dans_la_devise_du_projet`, inchangée).
- Pluriels par `ngettext`.

Ordre des projets : le plus d'éléments d'abord (somme des compteurs), puis le nom. 5 projets au
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
- un objet annulé hier sans aucune ligne d'avoir : « Personne — Objet — annulé ».

Ordre : le plus récent d'abord (`annulee_le`, ou la date de la dernière ligne d'avoir). 5 lignes au
plus. Lien : la liste des ventes (`/admin/BaseBillet/vente/`), qui porte les avoirs.

### 2.6 La forme du mail

- **Plus de bouton par rubrique.** Le titre de la rubrique devient un lien (couleur `#2d76a6`,
  sans fond). Le lien « Ouvrir l'administration » du bas reste.
- **5 lignes** au plus : `NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE = 5`.
- Les trois groupes (« À valider », « Nouveautés », « Caisse ») n'ont **pas** d'intertitre : l'ordre
  suffit. (Pas de sur-ingénierie ; à revoir si le mainteneur le demande.)

### 2.7 Le statut sur une ligne (E)

Le statut n'est écrit que s'il n'est pas le statut **normal** de la rubrique.

| Rubrique | Statut tu (normal) | Statut écrit |
|---|---|---|
| Demandes en attente (1, 2) | `ADMIN_WAITING` — toujours tu, le titre le dit | — |
| Nouvelles adhésions | `ONCE`, `AUTO`, `ADMIN`, `LABOUTIK` | `ADMIN_VALID`, `PAYMENT_PENDING`, `IMPORT` |
| Nouvelles réservations | `VALID`, `PAID`, `FREERES_USERACTIV` | `FREERES`, `PAID_ERROR`, `PAID_NOMAIL` |
| Nouvelles réservations de ressources | `PAID_BY_USER`, `NO_ADMIN_VALID`, `FREERES_USERACTIV` | `ADMIN_VALID`, `FREERES` |
| Nouveaux événements | « publié » | « brouillon », « proposition en attente » |

Les listes exactes (constantes du modèle) sont à revérifier au plan contre `BaseBillet/models.py`
et `booking/models.py` : un statut absent des deux colonnes est **écrit** (par défaut, on informe).

---

## 3. Les rapports de clôture hebdomadaire et mensuel

### 3.1 Où

Le mail existant de la clôture H ou M : `_envoyer_l_email_de_la_cloture` (`comptabilite/tasks.py`),
gabarit `comptabilite/templates/comptabilite/email/cloture_rapport_email.html`. On n'ajoute **ni
mail, ni tâche, ni réglage**.

Limites assumées (choix du mainteneur) : ce mail ne part que si le lieu a une clôture H/M (donc des
ventes en caisse) et des adresses dans `rapport_emails` avec la bonne périodicité — ou par l'envoi
à la demande depuis l'admin (`envoyer_email_cloture_demande`), qui reçoit les mêmes compteurs.

Niveaux concernés : **H et M**. Pas J (le Z J est dans le récap quotidien), pas A (non demandé).

### 3.2 Quoi

Un bloc « L'activité de la période » : une liste de compteurs **non nuls**, sans aucun détail.

> 12 nouvelles adhésions · 3 demandes d'adhésion · 48 nouvelles réservations · 5 réservations de
> ressources · 2 demandes de réservation de ressources · 9 inscriptions de bénévoles ·
> 4 nouveaux événements (dont 1 proposition) · 2 nouveaux projets · 7 contributions · 31 votes ·
> 3 participations · 6 annulations · 4 remboursements · 3 articles tombés en rupture

La période : `[cloture.datetime_debut, cloture.datetime_fin[`, les bornes de la clôture elle-même.
Chaque compteur reprend **exactement le filtre** de la rubrique quotidienne correspondante, sur
cette période au lieu de la veille. Les compteurs de financement participatif sont ceux du §2.4,
additionnés sur tous les projets. « Annulations » = objets annulés dans la période ;
« remboursements » = lignes d'avoir de la période.

Aucun compteur non nul : pas de bloc (le mail du Z part quand même, comme aujourd'hui).

Textes dans la langue du lieu (`translation.override(configuration.language)`, comme le récap).

### 3.3 Comment, sans dupliquer

Les filtres vivent **une seule fois**, dans `Administration/recap_quotidien.py` : une fonction par
source rend l'ensemble filtré sur `[debut, fin[` (ex. `_nouvelles_adhesions(debut, fin)`). La
rubrique quotidienne l'utilise pour ses lignes, `compteurs_de_la_periode(debut, fin)` pour son
`.count()`. `comptabilite/tasks.py` importe `compteurs_de_la_periode` en import local (le module du
récap importe déjà `comptabilite`).

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
- `tests/pytest/test_demo_recap_de_la_veille.py` et
  `Administration/management/commands/_demo_data_v2_recap.py` : les clés de rubriques attendues.

### 4.2 Tests nouveaux

- Une demande d'adhésion en attente d'avant-hier n'est pas dans le récap ; celle d'hier y est.
- Idem pour une demande de réservation de ressource.
- Rupture : un mouvement d'hier de 3 à 0 → l'article y est ; de 0 à -1 → il n'y est pas ; de 3 à
  -2 → il y est ; un mouvement d'avant-hier → il n'y est pas ; deux chutes le même jour → un seul nom.
- Financement : un projet avec 2 votes et 1 contribution d'hier → une ligne, compteurs exacts ;
  un projet sans activité hier → absent.
- Annulations et remboursements : une réservation annulée hier avec un avoir → **une** ligne avec
  le montant ; un avoir de caisse sans objet → une ligne ; un objet annulé sans avoir → « annulé ».
- Statut : une adhésion `ONCE` sans statut écrit, une `PAYMENT_PENDING` avec.
- 6 adhésions → 5 lignes + « et 1 autre ».
- Compteurs H/M : un mail de clôture H contient les compteurs de sa période et pas ceux d'avant ;
  pas de bloc quand tout est nul.

---

## 5. Documentation et suivi

- `SPEC.md` : une note en tête du §3.2 et du §3.5, « remplacé par le chantier 02 ».
- `INDEX.md` : le chantier 02 dans la table.
- `CHANGELOG/2026-10-22-recap-allege.md` : migration **Non**.
- i18n : nouvelles chaînes (titres, compteurs, pluriels) → **signaler au mainteneur**, ne pas lancer
  `makemessages`.
