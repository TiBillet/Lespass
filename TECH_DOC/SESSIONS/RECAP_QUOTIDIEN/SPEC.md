# ADMIN — Le récap du matin : l'activité de la veille et le ticket Z, en un seul mail

> **Status :** spec du 2026-10-18. **Pas encore de code.**
> **Décisions du mainteneur (2026-10-18) :**
> - le récap **fusionne** avec le mail du ticket Z journalier : un seul mail par jour et par lieu ;
> - **pas de mail pour rien** : on vérifie qu'il y a du contenu avant d'envoyer ;
> - destinataires : **les admins du lieu** ;
> - les **mails en temps réel ne bougent pas** (surtout « adhésion en attente ») ;
> - le mail Z journalier actuel (`rapport_periodicite = J`) est **remplacé** par le récap, qui part
>   aussi aux adresses de `rapport_emails` ;
> - heure : **7h, heure du lieu**, ou juste après le Z automatique s'il passe plus tard.
> - **on veut être au courant de TOUT ce qui s'est passé la veille** : financement participatif
>   et propositions d'événements compris (réponses au §8 du 2026-10-18) ;
> - un stock « en attente » ne déclenche pas le mail à lui seul ; `Reservation.created_at` et
>   `Event.created_at` sont ajoutés ; pas de réglage on/off en v1 (plus tard) ;
> - `annulee_le` sur `Reservation`, `Booking`, `Membership` : les annulations sont dans le récap ;
> - `rapport_emails` reçoit le récap dès qu'il y a du contenu, avec ou sans Z.
>
> **Relue le 2026-10-18 par un agent Fable** (exactitude face au code) : ses corrections sont
> intégrées (récap accroché au filet J, marqueur par `update()`, statuts exacts, remboursements,
> tests existants impactés).
>
> **Pré-requis :** aucun.
> **Consigne : pas de sur-ingénierie, conformité `djc`.**

---

## 1. Pourquoi

Aujourd'hui, un admin apprend l'activité de son lieu événement par événement (mails en temps réel),
ou en ouvrant l'admin. Rien ne lui dit, le matin : « hier, il s'est passé ça ». Le ticket Z
journalier, lui, part dans un mail séparé, à 4h du matin (fermeture 2h + 2h), et seulement aux
adresses de `rapport_emails`.

**Objectif :** chaque matin, un mail par lieu, aux admins, qui fait le point sur la veille :
adhésions, demandes d'adhésion en attente, réservations d'événements, réservations de ressources…
avec le ou les tickets Z de la veille en pièce jointe. **Si rien ne s'est passé, rien ne part.**

---

## 2. Ce qui existe déjà (lu le 2026-10-18)

| Brique | Où | Ce qu'on en fait |
|---|---|---|
| Celery beat, un passage par lieu | `TiBillet/celery.py`, `comptabilite/tasks.py` `generer_les_clotures_automatiques` | Le récap s'accroche à la fin de la sous-tâche horaire de chaque lieu, après le filet J (§4.1) |
| Heure du lieu | `Configuration.get_tzinfo()` | « La veille » et « 7h » se calculent dans le fuseau du lieu |
| Seuil du Z automatique | `comptabilite/tasks.py` `_seuil_courant_du_filet`, `_seuil_du_filet_d_un_jour` | Savoir si le Z de la veille est passé, et borner les Z à joindre |
| PDF d'une clôture | `comptabilite/pdf.py` `generer_pdf_cloture(cloture)` | Pièce jointe |
| Mail du Z actuel | `comptabilite/tasks.py` `_envoyer_l_email_de_la_cloture`, `demander_l_email_automatique_si_configure` | Le niveau J ne passe plus par là (§5) |
| Admins du lieu | `TibilletUser.objects.filter(client_admin=tenant)`, secours `config.email` | Déjà le calcul de `send_membership_pending_admin` (`BaseBillet/tasks.py:437`) |
| Envoi | `CeleryMailerClass` (liste d'adresses + `attached_files`) | Tel quel |
| Mise en service | `comptabilite/tasks.py` `mise_en_service_du_lieu()` | Pas de Z repris dans le récap (même règle que le mail actuel) |

---

## 3. Le contenu du récap

### 3.1 « La veille »

L'**activité** se compte sur le **jour calendaire de la veille, dans le fuseau du lieu** :
`[veille 00:00 heure du lieu, aujourd'hui 00:00 heure du lieu[`, converti en UTC pour les requêtes.

Les **tickets Z** suivent la journée de **service**, pas le jour calendaire : on joint les clôtures
**J** dont `datetime_fin` est dans `]seuil de la veille, seuil d'aujourd'hui]` (seuil = fermeture
+ 2 h, calculé par `_seuil_du_filet_d_un_jour`). Il y a donc :
- le Z fait à la main en fin de service, la veille au soir ;
- le Z automatique (le filet) s'il est passé ;
- éventuellement plusieurs Z (un par point de vente, ou plusieurs dans la soirée) : on les joint tous.

Un Z fait à la main ce matin à 10h appartient au service d'aujourd'hui : il sera dans le récap de
demain. Rien n'est perdu, rien n'est envoyé deux fois.

### 3.2 Les rubriques (v1)

> **Remplacé par le chantier 02** ([CHANTIER-02-recap-allege.md](CHANTIER-02-recap-allege.md), 2026-10-22) : plus de stocks, rubriques regroupées.

Une rubrique n'apparaît que si elle a au moins une ligne.

| Rubrique | Modèle | Filtre | Date |
|---|---|---|---|
| Nouvelles adhésions | `Membership` (champ **`status`**, pas `state`) | sauf `WAITING_PAYMENT` (paiement abandonné), `CANCELED`, `ADMIN_CANCELED`, et `ADMIN_WAITING` (déjà dans la rubrique suivante, pas de doublon) | `date_added` ✅ |
| Demandes d'adhésion en attente | `Membership` | `status=ADMIN_WAITING` — **tout le stock**, avec « dont N nouvelles hier » | `date_added` ✅ |
| Nouvelles réservations d'événements | `Reservation` | sauf `CREATED`, `UNPAID`, `CANCELED` | ⚠️ voir §3.3 |
| Nouvelles réservations de ressources | `booking.Booking` | sauf `WAITING_PAYMENT`, `ADMIN_WAITING` (déjà dans la rubrique suivante), `ADMIN_CANCELED`, `USER_CANCELED` (la docstring du modèle, « annulation = suppression », est périmée) | `booked_at` ✅ |
| Demandes de réservation en attente | `booking.Booking` | `status=ADMIN_WAITING` — **tout le stock**, avec « dont N nouvelles hier » ; le lien filtre la liste sur ce statut (voir `TECH_DOC/SESSIONS/BOOKING/SPEC.md` §5.10) | `booked_at` ✅ |
| Nouvelles inscriptions bénévoles | `InscriptionBenevole` | — (un retrait supprime la ligne : une inscription d'hier retirée avant le récap n'y est pas) | `created_at` ✅ |
| Nouveaux événements | `Event` | **tous** (créés par l'équipe ou proposés par le public), chaque ligne avec son état : « publié », « brouillon », « proposition en attente » (`is_proposal=True, published=False`). Filtrer sur `is_proposal=True` raterait une proposition créée et validée le même jour : la validation (`Administration/admin_tenant.py`, action d'approbation) remet `is_proposal=False` | ⚠️ voir §3.3 |
| Propositions d'événements en attente | `Event` | `is_proposal=True, published=False` — **tout le stock**, avec « dont N nouvelles hier » (même filtre que l'admin et `Administration/admin/dashboard.py`) | ⚠️ voir §3.3 |
| Nouveaux projets (financement participatif) | `crowds.Initiative` | — | `created_at` ✅ |
| Nouvelles lignes de budget | `crowds.BudgetItem` | — (proposées aussi par le public) | `created_at` ✅ |
| Lignes de budget en attente | `crowds.BudgetItem` | `state=BudgetItem.State.REQUESTED` — **tout le stock**, avec « dont N nouvelles hier » | `created_at` ✅ |
| Contributions payées hier | `crowds.Contribution` (champ **`payment_status`**) | `PaymentStatus.PAID` ou `PAID_ADMIN` | **`paid_at`** ✅ — posé par les deux seuls chemins de paiement (Stripe, « indiquée comme payée ») ; une contribution créée avant-hier et payée hier est « d'hier » ; une `PENDING` a `paid_at=NULL` |
| Nouveaux votes | `crowds.Vote` | — | `created_at` ✅ |
| Nouvelles demandes de participation | `crowds.Participation` | — | `created_at` ✅ |
| Demandes de participation en attente | `crowds.Participation` | `state=Participation.State.REQUESTED` — **tout le stock**, avec « dont N nouvelles hier » | `created_at` ✅ |
| Remboursements et avoirs | `LigneArticle` | lignes `REFUNDED` / `CREDIT_NOTE` créées hier | `datetime` (`auto_now_add`) ✅ |
| Annulations | `Reservation`, `Booking`, `Membership` | annulées par une personne (pas l'expiration d'un paiement) | **`annulee_le`**, nouveau champ — voir §3.4 |
| Ventes de la caisse | `ClotureCaisse` niveau J | §3.1 | chiffre d'affaires TTC (`total_general`) + nombre de ventes dans le corps, PDF en pièce jointe |

Chaque ligne montre son **statut**. Les statuts intermédiaires restent comptés (« on veut tout
savoir ») : adhésion `ADMIN_VALID` (confirmée, pas encore payée), `PAYMENT_PENDING` (SEPA en
cours), `IMPORT` (un import CSV d'hier apparaît donc comme N nouvelles adhésions) ; réservation
`FREERES` (gratuite, e-mail pas encore vérifié) ; booking `FREERES`.

Chaque rubrique montre un **compte** et une **liste courte** (10 lignes au plus, puis « et N autres »),
avec un bouton vers la liste de l'admin correspondante. Exception : `Contribution`, `Vote`,
`BudgetItem` et `Participation` n'ont pas de liste dans l'admin (ce sont des inlines de
l'`Initiative`) ; le bouton pointe sur la fiche de l'initiative concernée, ou sur la liste des
initiatives.

**Remboursements :** un remboursement ne change jamais le statut d'une ligne existante. Il écrit une
**vente AVOIR** avec un nouvel article, miroir négatif de la ligne d'origine (`BaseBillet/services_vente.py`,
`ajouter_l_article_d_avoir`), qui passe `CREDIT_NOTE` (admin, caisse) ou `REFUNDED` (Stripe,
`PaiementStripe/utils.py`). Ce sont les seules écritures de ces statuts. L'article garde ses FK
(`reservation`, `membership`, `booking`, `credit_note_for`) : le récap nomme l'objet remboursé.
Montant rendu : `-ligne.total_ttc`, l'argent effectivement rendu (c'est ce que lit `cancel_and_refund_resa`). `-qty × amount` donnerait le prix catalogue, sans la part offerte ni la part en jetons.

Les rubriques d'un module désactivé (`module_booking`, `module_crowdfunding`, caisse…)
n'apparaissent simplement pas : elles sont vides.

**La règle : on veut être au courant de TOUT ce qui s'est passé la veille.** Une source sans date
de création fiable est un trou à combler (§3.3), pas une raison d'écarter la rubrique.

### 3.3 Le piège des dates en `auto_now`

`Reservation.datetime` et `Event.created` sont en **`auto_now`** : c'est la date de **dernière
modification**, pas de création. Filtrer « créés hier » dessus ramènerait les anciens objets
modifiés hier (validation, annulation de billet, renvoi du mail, édition d'un événement…).

**Décision :** ajouter deux champs `created_at = DateTimeField(auto_now_add=True, null=True)`, sur
`Reservation` et sur `Event`. On ne touche pas à `Event.created` (nom trompeur, mais lu ailleurs).
- Une migration sur `BaseBillet` (TENANT_APP, 500 lieux) : des colonnes nullables, sans réécriture
  des tables. Les anciens objets restent à `NULL` : ils ne sont jamais « d'hier ».
- Alternatives écartées pour les réservations : `Commande.created_at` (seulement les achats passés
  par le panier) ; la date des `LigneArticle` (les réservations gratuites n'en ont pas toujours).

### 3.4 Le trou des annulations sans argent

Une annulation **sans remboursement** ne laisse aucune trace datée :
- `Reservation` annulée (gratuite, ou payée hors Stripe) : `status=CANCELED` + billets `CANCELED`,
  sans avoir ; pas de champ `canceled_at` ; et `save(update_fields=["status"])` ne touche même pas
  `datetime`.
- `Booking.USER_CANCELED` : pas d'avoir pour les lignes hors Stripe, pas de date.
- `Membership.ADMIN_CANCELED` : avoir seulement s'il y a de l'argent à rendre ; pas de date.
  (`Membership.CANCELED` est l'arrêt du renouvellement, pas une annulation.)
- Faux positif à écarter : `BaseBillet/signals.py` pose `Reservation.CANCELED` à l'expiration d'un
  paiement en cours — ce n'est pas une annulation par une personne.

**Décision (mainteneur, 2026-10-18) :** un champ `annulee_le = DateTimeField(null=True, blank=True)`
sur `Reservation`, `Booking` et `Membership`, posé à `timezone.now()` à chaque endroit qui annule.
Trois colonnes nullables dans la même migration. Rubrique **« Annulations »** : les objets dont
`annulee_le` est dans la fenêtre, avec leur statut, et « remboursé » si un avoir les vise.

Les endroits qui annulent (relevé du 2026-10-18, à recontrôler au plan par
`rg -n "status\s*=\s*(Reservation|Booking|Membership)\.(CANCELED|ADMIN_CANCELED|USER_CANCELED)"`) :

| Endroit | Pose `annulee_le` ? |
|---|---|
| `BaseBillet/models.py` — les deux méthodes d'annulation de `Reservation` (`self.status = Reservation.CANCELED`) | **Oui** (penser à `update_fields`) |
| `booking/models.py` — annulation par l'usager (`Booking.USER_CANCELED`) | **Oui** |
| `BaseBillet/views.py` — annulation d'une adhésion par un admin (`Membership.ADMIN_CANCELED`) | **Oui** |
| `BaseBillet/signals.py` — `Reservation.CANCELED` à l'expiration d'un paiement en cours | **Non** : ce n'est pas une annulation par une personne |
| `ApiBillet/views.py` — `Membership.CANCELED` (arrêt du renouvellement) | **Non** : pas une annulation |

Le statut à la main dans l'admin (vérifié le 2026-10-18) :
- `ReservationAdmin` : `status` en lecture seule sur la page de modification → rien à faire ;
- `MembershipAdmin` : `MembershipChangeForm` n'expose pas `status` → rien à faire ;
- **`BookingAdmin`** (`Administration/admin/resources.py`) : `status` **est modifiable** (seuls
  `commande` et `custom_form` sont exclus) → `save_model` pose `annulee_le` quand le statut passe
  à `ADMIN_CANCELED` ou `USER_CANCELED`.

`annulee_le` est en `editable=False` sur les trois modèles : aucun formulaire de l'admin ne
l'affiche ni ne l'écrit.

### 3.5 Pas de mail pour rien

> **Remplacé par le chantier 02** ([CHANTIER-02-recap-allege.md](CHANTIER-02-recap-allege.md), 2026-10-22) : plus de stocks, rubriques regroupées.

Le récap part si **au moins une** de ces conditions est vraie :
- une rubrique « nouveau » a au moins une ligne (toutes les rubriques du §3.2 sauf les stocks) ;
- au moins un ticket Z est à joindre.

**Un stock « en attente » ne déclenche pas le mail à lui seul** (adhésions, propositions
d'événements, lignes de budget, demandes de participation) : sinon une demande oubliée ferait partir un mail chaque
matin, pour rien de neuf. Le stock est montré quand le mail part. (Validé par le mainteneur.)

---

## 4. Quand et à qui

### 4.1 L'heure

**Pas de nouvelle tâche Celery beat.** Le récap d'un lieu est appelé **à la fin de
`generer_les_clotures_automatiques_du_lieu`** (`comptabilite/tasks.py`), après le filet J, dans la
même sous-tâche horaire. C'est la seule façon d'être sûr que le Z automatique est fait : la tâche
horaire des clôtures ne fait que `.delay()` une sous-tâche par lieu, rien ne garantit qu'elle a
tourné à une minute donnée. Un récap passé avant le filet perdrait la J du filet (elle finit pile
au seuil d'aujourd'hui, hors de la fenêtre du lendemain). Les lieux `public` et `WAITING_CONFIG`
sont déjà exclus par cette boucle.

Le récap part si :

1. il est **7h passées**, heure du lieu ;
2. le **seuil du Z d'aujourd'hui est passé** : `timezone.now() >= _seuil_du_filet_d_un_jour(aujourd'hui
   heure du lieu, fuseau, heure_de_fermeture)` — fermeture à 2h : seuil à 4h, sans effet ;
   fermeture à 6h : seuil à 8h, le récap part au passage de 8h ;
3. il n'a **pas déjà été traité aujourd'hui**.

`comptabilite/tasks.py` calcule les deux seuils (veille, aujourd'hui) et les **passe en paramètres**
au récap : le module du récap n'importe pas les fonctions privées de `comptabilite`.

Pour le point 3 : un champ `Configuration.recap_quotidien_traite_le = DateField(null=True)`, posé à
la date du jour **même quand rien n'est envoyé** (on ne recalcule pas toutes les heures).
- **Jamais par `configuration.save()`** : `Configuration.save()` appelle Stripe
  (`check_stripe_sepa_capability`) pour un lieu qui accepte le SEPA, et peut lever une
  `ValidationError`. On écrit `Configuration.objects.filter(pk=…).update(recap_quotidien_traite_le=…)`
  puis `Configuration.clear_cache()` (`update()` ne touche pas le cache django-solo, piège 13.5).
- Le marqueur est **lu par une requête**, pas par `get_solo()` (cache de 300 s).
- Il est posé **avant** l'envoi : si la tâche plante après l'envoi, un mail perdu (visible dans
  Sentry) vaut mieux qu'un doublon chaque heure.

Une erreur est journalisée (`logger.exception`, Sentry) et remontée, comme pour les clôtures : la
sous-tâche du lieu est notée en échec, les autres lieux ne sont pas touchés. Le récap est retenté
au passage suivant (le marqueur n'est pas posé si le calcul plante). Pas de `try/except` qui étouffe
l'erreur.

Toutes les heures se lisent par `timezone.now()` (jamais `datetime.now()` ni `date.today()`) :
« aujourd'hui » = `timezone.localtime(timezone.now(), fuseau).date()`. Les tests patchent
`django.utils.timezone.now`.

**Limite acceptée :** si Celery est arrêté une journée entière, l'activité de ce jour-là n'est dans
aucun récap (la fenêtre est toujours « hier »). Les Z, eux, ne sont pas perdus : le filet suivant
couvre la plage, et ils partent dans le récap suivant.

### 4.2 Les destinataires

- les admins du lieu : `TibilletUser.objects.filter(client_admin=tenant)` ; s'il n'y en a aucun,
  `config.email` (même règle que `send_membership_pending_admin` : pas de filtre `is_active`, un
  compte admin jamais activé reçoit aussi le mail) ;
- **plus**, si `BaseBillet.Configuration.rapport_periodicite == PERIODICITE_JOURNALIER`, les
  adresses de `BaseBillet.Configuration.rapport_emails` (texte à virgules, même lecture que
  `_envoyer_l_email_de_la_cloture`). C'est la fusion : le ou la comptable qui recevait le Z le
  reçoit maintenant dans le récap. **Ces adresses reçoivent le même récap que les admins, dès qu'il
  y a du contenu, avec ou sans Z** (décision du mainteneur : « dès qu'il se passe un truc, on le
  fait »). (Les champs homonymes de `LaboutikConfiguration` ne servent pas.)
- sans doublon (adresses comparées en minuscules, sans espaces).

Un seul mail, toutes les adresses en destinataires (comme `send_membership_pending_admin`).

Le mail est rendu dans la langue du lieu : `translation.override(config.language)` autour du rendu
(`CeleryMailerClass` n'active aucune langue, piège P.ONBOARD.5).

---

## 5. La fusion avec le mail du ticket Z

| Niveau | Avant | Après |
|---|---|---|
| **J** (journalier) | un mail par Z à `rapport_emails` si `rapport_periodicite == J` | **plus de mail séparé** : le Z part dans le récap du matin |
| H, M, A | un mail par clôture si la périodicité correspond | **inchangé** |
| Bouton « Envoyer par e-mail » de la caisse (`envoyer_email_cloture_demande`) | envoi immédiat | **inchangé** |

Le changement de fond : `demander_l_email_automatique_si_configure` ne demande plus le mail pour
une clôture **J**. Ses appelants : `generer_cloture_pour_tenant`, le filet J, les H/M/A, et
**`CaisseViewSet.cloturer`** (`laboutik/views.py`) — le Z manuel à la caisse n'envoie donc plus de
mail immédiat, c'est voulu. Le bouton « Envoyer par e-mail » (`envoyer_email_cloture_demande`) ne
passe pas par là.

Textes devenus faux, à mettre à jour : l'en-tête de `comptabilite/tasks.py`, les docstrings de
`demander_l_email_automatique_si_configure` et `envoyer_email_cloture`, `comptabilite/pdf.py`
(en-tête), le commentaire « L'e-mail automatique de la J… » dans `laboutik/views.py`
(`CaisseViewSet.cloturer`), le `help_text` de `rapport_emails` et le libellé `_("Daily")` de
`rapport_periodicite` (« je reçois le Z chaque jour, dans le récap du matin »).

Tests existants à adapter :

| Test | Pourquoi |
|---|---|
| `test_cloture_caisse.py` `test_bouton_lieu_en_periodicite_j_un_seul_email_pour_cette_j` | Attend la demande de mail J après « Clôturer » : à inverser |
| `test_cloture_caisse.py` `test_bouton_broker_en_panne…` | Attend deux appels au broker (impression + mail) en périodicité J : n'en verra plus qu'un |
| `test_reprise_clotures.py` `test_j_reprise_n_envoie_aucun_mail` | Sa « preuve par la J suivante » attend un mail J : passer en H, ou prouver par le récap |
| `test_comptabilite_celery.py` `test_envoyer_email_cloture_envoie_si_config_ok` ; `test_comptabilite_exports.py` `test_email_de_cloture_montre_le_chiffre_d_affaires_ttc`, `test_email_de_cloture_en_heure_du_lieu` | Ne cassent pas mais testent un chemin devenu mort pour J : basculer sur `envoyer_email_cloture_demande` ou sur H (le gabarit reste utilisé par le bouton de la caisse) |

---

## 6. Ce qui ne change pas

- Tous les mails en temps réel : `send_membership_pending_admin`, `send_payment_success_admin`,
  les mails `crowds`, le désistement bénévole, etc.
- Les clôtures elles-mêmes (création, numérotation, chaînage) : le récap **lit** les `ClotureCaisse`,
  il n'y écrit rien.
- `cron_morning`.

---

## 7. Fichiers concernés (prévision)

| Fichier | Changement |
|---|---|
| `Administration/recap_quotidien.py` (nouveau) | Le calcul (la fenêtre, les rubriques, les Z à joindre, « y a-t-il du contenu ? ») et l'envoi. Reçoit les deux seuils en paramètres. Fonctions testables sans mail |
| `comptabilite/tasks.py` | Appel du récap à la fin de `generer_les_clotures_automatiques_du_lieu` (import local) ; plus de mail J dans `demander_l_email_automatique_si_configure` ; docstrings (§5) |
| `comptabilite/pdf.py`, `laboutik/views.py` | Commentaires devenus faux (§5) |
| `BaseBillet/templates/emails/recap_quotidien.html` (nouveau) | Le mail : `{% extends 'emails/base.html' %}`, comme `emails/email_generique.html` (même dossier) |
| `Administration/admin/resources.py` | `BookingAdmin.save_model` pose `annulee_le` (§3.4) |
| `BaseBillet/models.py` | `Reservation.created_at`, `Event.created_at`, `Configuration.recap_quotidien_traite_le`, `Reservation.annulee_le`, `Membership.annulee_le` ; les méthodes d'annulation de `Reservation` posent `annulee_le` |
| `BaseBillet/migrations/02xx_…` | Les cinq champs de `BaseBillet` |
| `booking/models.py` + `booking/migrations/00xx_…` | `Booking.annulee_le`, posé par l'annulation |
| `BaseBillet/views.py` | L'annulation d'adhésion par un admin pose `annulee_le` |
| `tests/pytest/test_recap_quotidien.py` (nouveau) | §9 |
| `Administration/management/commands/_demo_data_v2_recap.py` (nouveau), `demo_data_v2.py` | Démo du flush : l'activité d'hier de 4 personnes (adhésions, ventes, ressources, bénévolat) et le récap envoyé à l'admin à la fin du flush (PLAN tâche 8) |
| `CHANGELOG/2026-xx-xx-recap-quotidien-admins.md` | Fiche |

Chaînes traduisibles en français (`_()`), workflow i18n **au mainteneur**.

---

## 8. Décisions du mainteneur (2026-10-18)

1. **Stock en attente** : ne déclenche pas le mail seul (§3.5) — **oui**.
2. **`Reservation.created_at`** (§3.3) — **oui** ; même traitement pour `Event.created_at`.
3. **Désactiver le récap** : pas de réglage on/off en v1 — **plus tard**. Un admin de 5 lieux
   recevra jusqu'à 5 mails.
4. **Financement participatif et propositions d'événements** : **dans la v1**. « On veut être au
   courant de TOUT ce qui s'est passé la veille. »

5. **Annulations sans argent** (§3.4) : `annulee_le` sur `Reservation`, `Booking`, `Membership`
   — **oui, dans la v1**.
6. **`rapport_emails`** (§4.2) : **reçoit le récap dès qu'il y a du contenu**, avec ou sans Z
   (« dès qu'il se passe un truc, on le fait »).

---

## 9. Tests (pytest)

- La fenêtre : « la veille » dans le fuseau du lieu (un lieu en Europe/Paris, un en
  America/Martinique), y compris une nuit de changement d'heure.
- Chaque rubrique : une ligne d'hier compte, une d'avant-hier et une d'aujourd'hui non ; les statuts
  exclus ne comptent pas ; une réservation ou un événement **ancien modifié hier** ne compte pas
  (§3.3) ; une contribution `PENDING` ne compte pas, une contribution créée avant-hier et payée
  hier compte ; une proposition créée et validée hier est dans « Nouveaux événements » ; un
  remboursement d'hier nomme l'objet remboursé et son montant.
- Les Z : un Z manuel d'hier soir et le filet de ce matin sont joints ; un Z de ce matin 10h ne
  l'est pas ; une clôture dont `datetime_fin <= mise en service` ne l'est pas (même règle que
  `demander_l_email_automatique_si_configure`).
- Le récap passe **après** le filet dans la même sous-tâche : la J du filet de ce matin est jointe.
- Le marqueur est posé par `update()`, sans appel à `Configuration.save()`.
- Le mail est dans la langue du lieu (un lieu en anglais).
- **Pas de contenu → pas de mail**, et `recap_quotidien_traite_le` est quand même posé.
- Stock en attente seul → pas de mail.
- L'heure : à 6h rien ; à 7h envoi ; un second passage à 8h n'envoie rien ; fermeture à 6h →
  rien à 7h, envoi à 8h.
- Les destinataires : admins ; secours `config.email` ; `rapport_emails` ajoutés si périodicité J,
  **même un jour sans Z** ; sans doublon.
- Les annulations : chaque endroit du §3.4 marqué « Oui » pose `annulee_le` ; l'expiration d'un
  paiement et l'arrêt du renouvellement ne le posent pas ; une annulation d'hier est dans la
  rubrique, une remboursée y est marquée « remboursé ».
- La fusion : une clôture J ne déclenche plus de mail séparé ; H/M/A et le bouton de la caisse,
  inchangés.
- Chaque test vu **échouer** sur une mutation volontaire avant d'être livré.

Pièges à relire avant d'écrire ces tests (`tests/PIEGES.md`) : 9.1 (`tenant_context`, jamais
`schema_context`), 13.4 (intercepter les `.delay()`), 13.5 (cache django-solo qui survit au
rollback), 9.63 (`generer_cloture_pour_tenant` pour fabriquer des J), P.ONBOARD.5 (langue), 9.50 /
12.13 (redémarrer `lespass_celery` pour une vérification passant par Celery).
