# Récap du matin allégé, compteurs H/M et réglages des envois / Lighter morning recap, H/M counters and mail settings

**Date :** 2026-10-22
**Migration :** Oui — `comptabilite 0006_reglages_des_envois` (nouveau modèle), `comptabilite 0007_reglages_des_envois_depuis_la_configuration` (données), puis `BaseBillet 0238_retrait_des_champs_rapport` (supprime `Configuration.rapport_emails` et `rapport_periodicite`).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas` (prod : surveiller la sortie, la migration de données écrit `ADRESSE PERDUE` pour chaque e-mail de `rapport_emails` sans user du lieu).

## Resume / Summary
**Quoi / What :**
- FR : Le récap du matin ne montre plus que des objets nés la veille, même en attente. Les rubriques
  « en attente » en doublon (propositions, lignes de budget, participations) disparaissent. Nouvelle
  ligne « Tombés en rupture hier » (inventaire). Le financement participatif tient en une rubrique,
  une ligne par projet avec des compteurs. Annulations et remboursements sont réunis, une ligne par
  objet. 5 lignes par rubrique, plus de bouton par rubrique (le titre est le lien), le statut n'est
  écrit que s'il informe, et ce qui est à valider passe en tête. Les mails de clôture hebdomadaire et
  mensuelle portent les compteurs de l'activité de leur période ; tout le mail de clôture est rendu
  dans la langue du lieu.
- EN: The morning recap only shows objects born yesterday, even pending ones. Duplicate pending
  sections are gone. New "ran out of stock yesterday" line. Crowdfunding is one section, one line per
  project with counters. Cancellations and refunds are merged, one line per object. 5 lines per
  section, no more per-section button, status written only when informative, action items first.
  Weekly and monthly closure mails carry the period's activity counters; the closure mail is
  rendered in the venue's language.
- FR : **Réglages des envois** (`comptabilite.ConfigurationDesRapports`, admin « Envoi des
  rapports », menu Ventes & comptabilité + bouton sur la liste des clôtures) : une case par envoi
  (récap du matin, rapports hebdomadaire, mensuel, annuel), tout coché par défaut, et une liste de
  destinataires choisis parmi les personnes du lieu. **Seule la liste reçoit** : plus d'admins
  d'office. **La liste est vide après la migration** : les lieux existants ne reçoivent plus rien
  tant qu'un admin ne s'inscrit pas (sauf les personnes reprises de `rapport_emails`). L'onboarding
  inscrit le premier admin d'un nouveau lieu. Lien « se désabonner » en pied des mails.
- EN: **Mail settings** singleton: one tick per mail, all ticked by default, and a recipient list
  of venue people. Only the list receives mails. **The list is empty after the migration.** The
  onboarding subscribes a new venue's first admin. Unsubscribe link in the mails' footer.

**Pourquoi / Why :**
- FR : le récap était trop verbeux : les vieilles demandes revenaient chaque matin, 17 rubriques
  possibles, 17 gros boutons, un vote par ligne, un remboursement en double.
- EN: the recap was too verbose: old requests came back every morning, up to 17 sections and
  buttons, one line per vote, refunds listed twice.

Spécification : `TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/CHANTIER-02-recap-allege.md` (§2, §3).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/recap_quotidien.py` | Sources filtrées partagées (récap + compteurs), nouvelles rubriques (ruptures, financement, annulations et remboursements), fin des stocks, statut « s'il informe », 5 lignes, `compteurs_de_la_periode` |
| `BaseBillet/templates/emails/recap_quotidien.html` | Plus de « dont N nouvelles hier » ni de bouton par rubrique ; le titre est le lien |
| `comptabilite/tasks.py` | `_envoyer_l_email_de_la_cloture` : rendu dans `translation.override(config.language)`, compteurs pour H et M |
| `comptabilite/templates/comptabilite/email/cloture_rapport_email.html` | Bloc « L'activité de la période » |
| `tests/pytest/test_recap_quotidien.py` | Tests réécrits (fin des stocks, rubriques regroupées, 5 lignes, statut) + ruptures, compteurs, mail H |
| `tests/pytest/test_demo_recap_de_la_veille.py` | Clé `annulations_et_remboursements` ; l'admin de démo est inscrit aux envois |
| `comptabilite/models.py` | `ConfigurationDesRapports` (singleton : 4 booléens + M2M `HumanUser`) |
| `comptabilite/migrations/0006_*`, `0007_*` | Création du modèle ; reprise de `rapport_periodicite` / `rapport_emails` |
| `BaseBillet/migrations/0238_retrait_des_champs_rapport.py` | Suppression des deux anciens champs |
| `BaseBillet/models.py` | Suppression de `rapport_emails`, `rapport_periodicite`, `PERIODICITE_*` |
| `comptabilite/admin.py` | `ConfigurationDesRapportsAdmin` (autocomplétion des destinataires) ; URL des réglages dans le bandeau des clôtures |
| `comptabilite/templates/comptabilite/admin/changelist_before.html` | Carte « Envoi des rapports » |
| `Administration/admin/dashboard.py` | Entrée « Envoi des rapports » dans Ventes & comptabilité |
| `BaseBillet/validators.py` | L'onboarding inscrit le premier admin aux envois |
| `Administration/management/commands/demo_data_v2.py` | La démo inscrit l'admin de chaque lieu |
| `Administration/recap_quotidien.py`, `comptabilite/tasks.py` | Destinataires = la liste ; cases J, H, M, A ; lien de désabonnement |
| `tests/pytest/fabriques_vente.py` | `abonner_aux_envois_des_rapports` |
| 22 autres fichiers `tests/pytest/` | Retrait des lignes `rapport_emails = ""` / `PERIODICITE_NONE` devenues inutiles |

**i18n :** nouvelles chaînes traduisibles (titres, compteurs `ngettext`, « remboursé %(montant)s »,
« dont %(nombre)s à valider », « L'activité de la période ») — **workflow i18n à lancer par le mainteneur**.

---

## Comment tester (a la main) / Manual test

### Test 1 — le récap de démo
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py demo_data_v2` (ou le flush habituel), qui envoie le récap de démo.
2. Ouvrir le mail dans la boîte de dev.
3. Attendu : en tête « Demandes d'adhésion en attente » ; titres de rubriques cliquables, **aucun**
   bouton bleu par rubrique ; au plus 5 lignes par rubrique ; une rubrique « Annulations et
   remboursements » (une ligne par objet, « remboursé X € » s'il y a un avoir) ; aucune phrase
   « dont N nouvelles hier ».

### Test 2 — une vieille demande ne revient plus
1. Dans le shell, reculer la `date_added` d'une adhésion `AW` à il y a 3 jours.
2. Relancer le récap (`envoyer_le_recap` via la commande de démo, ou `preparer_le_recap_du_lieu`).
3. Attendu : elle n'apparaît plus dans « Demandes d'adhésion en attente ».

### Test 3 — rupture de stock
1. Module inventaire actif : un article POS avec un stock de 1, en vendre 1 à la caisse.
2. Le lendemain (ou en reculant `cree_le` du `MouvementStock` à hier), préparer le récap.
3. Attendu : « Tombés en rupture hier (1) » avec le nom de l'article. Un ajustement d'inventaire à 0
   ne produit rien.

### Test 4 — compteurs du mail hebdomadaire
1. Un lieu avec des ventes la semaine passée, `rapport_emails` rempli et `rapport_periodicite = "H"`.
2. Laisser passer la clôture hebdomadaire (ou `generer_cloture_pour_tenant(..., niveau="H")`), puis
   `envoyer_email_cloture`.
3. Attendu : un bloc « L'activité de la période » (« 12 nouvelles adhésions · 3 votes · … ») ; aucun
   bloc si rien ne s'est passé ; un lieu en anglais reçoit tout le mail en anglais.

### Test 5 — réglages des envois
1. Admin du lieu → menu « Ventes & comptabilité » → « Envoi des rapports » (ou bouton « Régler les
   envois » sur la liste des clôtures).
2. Chercher une personne dans « Destinataires » : seules les personnes du lieu sont proposées.
   Enregistrer.
3. Décocher « Récap du matin » : le lendemain, aucun récap (et rien n'est envoyé aux admins non inscrits).
4. Ouvrir un mail reçu : le pied porte « Vous pouvez vous désabonner de cette lettre d'information :
   réglages des envois », qui ouvre cette page.

### Test 6 — onboarding (pas de test automatique)
1. Créer un nouveau lieu par l'onboarding.
2. Attendu : « Envoi des rapports » du nouveau lieu, tout coché, avec le premier admin dans la liste.

### Verifs automatiques
- Les 27 fichiers de tests touchés + `test_admin_verbose_name`, `test_noms_de_routes_admin_uniques`,
  `test_admin_configuration_onglets`, `test_menu_rapports`, `test_onboard_laboutik_verrou_v1_v2` :
  708 passed (2026-10-22, après `migrate_schemas`).
- Vérification par mutation : 7 mutations sur le récap/les compteurs, 6 sur les réglages des
  envois, toutes vues en échec.
