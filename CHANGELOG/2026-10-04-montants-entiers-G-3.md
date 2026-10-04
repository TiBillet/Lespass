# Totaux client, ancien LaBoutik et fiche « Vente » de l'admin (chantier 05, fiche G, session G-3) / Customer totals, legacy LaBoutik and admin "Sale" page (worksite 05, sheet G, session G-3)

**Date :** 2026-10-04
**Migration :** Non

## Resume / Summary
**Quoi / What :** voir chaque partie ci-dessous (G-3a, puis G-3b, G-3c-1, G-3c-2). /
See each part below.

**Pourquoi / Why :** fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md` §4, brief `CHANTIER-05-briefs/05-G-3.md`, décisions Q-G5 et réponses de l'orchestrateur aux constats de G-3a (SUIVI §4).

## G-3a — Totaux côté client sur `total_ttc`

### Resume / Summary
Tout montant d'argent montré au client, à l'admin ou dans un fichier se lit dans les montants entiers écrits à la vente (`total_ttc`, `total_ht`, `total_tva`), jamais par `amount × qty` (prix unitaire × quantité : faux d'un centime sur un article payé avec deux moyens, et part offerte comptée). /
Every money amount shown is read from the whole-cent amounts written at sale time, never from unit price × quantity.

- `Reservation.total_paid`, `Reservation._montant_paye_par_stripe`, les messages d'annulation de l'utilisateur (`ligne.total_ttc > 0`) : Σ `total_ttc`. Les gabarits « mes réservations » et le mail d'achat lisent `total_paid` : ils suivent. Un billet entièrement offert a un `total_paid` de 0.
- `Paiement_stripe.total()` et `.articles()` : Σ `total_ttc` des lignes du paiement (remboursements compris). Ils sont lus par `is_fully_refunded`, les mails d'échec et de refus de paiement et la facture. Le cas « transfert Stripe » ne change pas.
- `Booking.to_pay`, `Booking.total_paid`, `Booking._lignes_hors_stripe` (`total_ttc > 0`), mail d'annulation d'un booking (`booking/tasks.py`) : Σ `total_ttc`.
- `TicketCreator` (choix Stripe ou gratuit, `BaseBillet/validators.py`) : Σ `total_ttc`, même décision.
- `LigneArticle.total_decimal()` : le net vendu (`total_ttc`). Lu par la facture, le formulaire d'annulation d'adhésion et l'onglet des ventes de la fiche adhésion.
- `LigneArticle.moyens_de_paiement_de_sa_vente()` (nouveau) : les moyens des règlements de la vente de la ligne, en clair, pour l'affichage.
- Admin (`Administration/admin_tenant.py`) :
  - fiche utilisateur : montant payé = Σ `total_ttc`, moyens lus dans les règlements (préchargés, nombre de requêtes constant) ;
  - liste des ventes (`LigneArticleAdmin`) : colonne « Total » = `total_ttc`, et colonne « Moyen de paiement » lue dans les règlements à la place de `payment_method` ;
  - onglet des ventes de la fiche adhésion (`LigneArticleInline`) : même chose ;
  - écran « Émettre un avoir » : le montant rappelé est le net vendu de la ligne.
- Export des lignes (`lignearticle_exporter.py`) : la colonne « Montant » garde son nom et lit `total_ttc`. Nouvelles colonnes « Total HT », « Total TVA », « N° de vente ». « Payment method » est lue dans les règlements de la vente.
- Facture d'adhésion (`BaseBillet/tasks.py` `create_membership_invoice_pdf`, `invoice.html`), une facture par paiement (le dernier : l'achat ou le dernier renouvellement) :
  - hors Stripe : la facture porte les parts de l'adhésion de sa DERNIÈRE vente (lignes de cette vente au même tarif que la dernière ligne de l'adhésion), sans les autres articles de la vente ni les ventes plus anciennes ;
  - son total est la somme de leurs `total_ttc`, et non plus `contribution_value` ; une adhésion sans ligne payée a un total de 0 (accepté) ;
  - une adhésion de 35 € payée 10 € par carte + 25 € par CB fait 35 € ; avant, la facture n'affichait qu'une seule part (10 €) ;
  - payée par Stripe : rien ne change, la facture porte tout le paiement Stripe (un billet du même panier compris), ses montants sur `total_ttc`.

Laissés pour la fiche H :
- le contrôle du solde d'un paiement QR (`BaseBillet/validators.py` `validate`, `self.ligne_article.amount`) ;
- les lecteurs de `ligne.payment_method` qui DÉCIDENT (complétés en G-3a-bis : voir plus bas) :
  - le pré-remplissage « Remboursé par » d'`emettre_avoir` (`admin_tenant.py`) et du formulaire d'annulation d'adhésion (`BaseBillet/views.py`) ;
  - les moyens d'origine de l'annulation admin (`admin_tenant.py`) ;
  - le repli du moyen du règlement d'un remboursement Stripe (`PaiementStripe/utils.py`) et de l'avoir (`services_vente.py` `ecrire_la_vente_d_avoir_d_une_ligne`) ;
  - le moyen recopié sur l'article d'avoir (`ajouter_l_article_d_avoir`) ;
  - `ligne_entierement_offerte`, `ligne_payee_en_jetons`, `ligne_payee_en_points` ;
  - la TVA par défaut d'une ligne offerte ou en points (`LigneArticle._compute_default_vat`).

`LigneArticle.total()` (prix × quantité arrondi) n'a plus de lecteur en production ; il reste jusqu'à la fiche **H** (des tests le lisent encore : `test_admin_reservation_add.py`, `test_paiement_complementaire.py`, `test_pos_retour_consigne.py`). La garde `rg` du test 19 (G-3c-2, « aucun lecteur ne multiplie `amount × qty` ») doit l'exclure explicitement.

Nouvelle chaîne i18n : « N° de vente ». Le workflow i18n est à lancer par le mainteneur.

### Tests réécrits / Rewritten tests
| Test | Raison / Reason |
|---|---|
| `tests/pytest/test_mail_annulation_booking.py` | Lignes écrites à la main sans `total_ttc` (Q-G5) : le booking est payé et remboursé par les vrais gestes (formulaire, retour Stripe, `cancel_and_refund_booking`), en `django_db`, sans suppression à la main. Même intention : le mail annonce 15 €. |
| `tests/pytest/test_stripe_refund.py` `test_lignes_hors_stripe_ne_renvoie_que_les_lignes_de_la_reservation` | La ligne « sans réservation » est écrite par le service de vente (Q-G5). |
| `tests/pytest/test_stripe_refund.py` `test_annuler_une_reservation_admin_especes_cree_son_avoir` | La recopie de la formule de l'admin (`amount × qty`) est remplacée par la lecture du montant que la vraie fiche utilisateur affiche. |
| `tests/pytest/fabriques_reservation.py` `reservation_payee` | Le montant payé chez Stripe se lit sur `total_ttc`. |

### Tests ajoutés / Added tests
`tests/pytest/test_lecteurs_montants_entiers.py` (base partagée) : tests de fiche 11, 11b, 12 et 17 ; facture sans les autres articles de la vente ; facture d'une adhésion renouvelée (le renouvellement seul) ; `Paiement_stripe.total` et `.articles` ; `Booking.total_paid`, `.to_pay` et mail d'annulation ; fiche utilisateur ; colonnes « Total » de la liste des ventes et de l'onglet de l'adhésion ; écran d'avoir ; formulaire d'annulation d'adhésion ; moyens affichés lus dans les règlements (liste des ventes, onglet de l'adhésion, export, fiche utilisateur). `tests/pytest/fabriques_ecran.py` : lecteur `tableaux_de_la_page`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Reservation.total_paid`, `_montant_paye_par_stripe`, messages d'annulation ; `Paiement_stripe.total`, `.articles` ; `LigneArticle.total_decimal`, `moyens_de_paiement_de_sa_vente` |
| `BaseBillet/validators.py` | `TicketCreator` : choix Stripe ou gratuit sur `total_ttc` |
| `BaseBillet/tasks.py` | Facture d'adhésion : parts de l'adhésion, total = Σ `total_ttc` |
| `BaseBillet/templates/invoice/invoice.html` | Total hors Stripe = somme des parts |
| `booking/models.py`, `booking/tasks.py` | `to_pay`, `total_paid`, `_lignes_hors_stripe`, mail d'annulation |
| `Administration/admin_tenant.py` | Fiche utilisateur, `LigneArticleInline`, `LigneArticleAdmin`, `emettre_avoir` |
| `Administration/importers/lignearticle_exporter.py` | « Montant » = `total_ttc`, colonnes HT, TVA, n° de vente ; moyens lus dans les règlements |

## G-3a-bis — Relecture de G-3a

### Resume / Summary
- **Moyens affichés** (fiche utilisateur, liste des ventes, onglet des ventes d'une adhésion, export) : le NET par moyen des règlements de la vente ET de ses ventes CORRECTION. Seuls les moyens à net non nul sont gardés, sans l'offert. Les libellés et l'ordre viennent de `laboutik/affichage_des_ventes.py`, nouvelle fonction `noms_des_moyens_nets_de_la_vente`, la seule règle. Une vente en espèces corrigée en CB dit « Carte bancaire ». Un règlement cashless s'écrit par le nom de son moyen dans les listes : les noms des monnaies demanderaient des requêtes par ligne. La facture, elle, écrit le nom de la monnaie.
- **Colonne d'export renommée** : « Payment method » devient « **Moyens de la vente** », parce que son sens a changé (moyens nets de la vente, et non plus le moyen de la ligne).
- **Facture d'adhésion** :
  - on part de la DERNIÈRE ligne payée de l'adhésion (par date). Si elle a un paiement Stripe, la facture porte CE paiement en entier. Sinon, elle porte les parts de l'adhésion de sa vente, limitées aux lignes de cette adhésion ou sans adhésion (jamais la part d'une autre adhésion du même panier) ;
  - les parts sont regroupées en UN article (`articles_de_la_vente_pour_l_affichage`), avec la part offerte montrée (« dont offert … ») ;
  - le pied « Mode de paiement » lit les moyens nets de la vente, et non plus `membership.payment_method_name`.
- **`Booking.total_paid`** compte aussi les avoirs (CREDIT_NOTE), comme `Reservation.total_paid`. Un booking entièrement remboursé par un avoir de l'admin vaut 0.
- **Nombre de requêtes constant** : la liste des ventes (N lignes) précharge produit, événement, réservation et client, la vente, ses règlements et ceux de ses corrections ; l'export passe par ce même queryset (`get_export_queryset`) ; la fiche utilisateur précharge les règlements des corrections. Ces trois points sont testés en comptant les requêtes (1 ligne contre 3).
- `LigneArticleAdmin.total_decimal` appelle `LigneArticle.total_decimal`. Les commentaires ont été corrigés (« — » quand il n'y a aucun moyen d'argent ; ligne payée en jetons dans `Booking._lignes_hors_stripe`).
- Le test `test_stripe_refund.py::…test_lignes_hors_stripe_ne_renvoie_que_les_lignes_de_la_reservation` est marqué `django_db` : la vente scellée qu'il écrit est annulée.

Nouvelles chaînes i18n : « Moyens de la vente », « dont offert ». Le workflow i18n est à lancer par le mainteneur.

Constats laissés pour la fiche H :
- montants en points (ventes en points ou en temps) dans l'export et la fiche utilisateur : ils s'affichent en euros ;
- lignes sans vente écrites par `fedow_core` (vidage de carte, paiement QR) : sans vente, elles n'ont ni moyen affiché ni numéro de vente ;
- total du panier en ligne lu sur `total_catalogue` (`services_commande.py`) : équivalent tant qu'aucun article en ligne n'a de part offerte ;
- les lecteurs de `ligne.payment_method` qui décident (liste de G-3a ci-dessus, complétée par la relecture Opus, SUIVI §4).

### Tests ajoutés / Added tests
`tests/pytest/test_lecteurs_montants_entiers.py` :
- moyens après une correction espèces → CB (colonne de la liste, export) ;
- moyens sans l'offert ;
- nombre de requêtes constant (liste des ventes, export par l'admin, fiche utilisateur) ;
- facture : achat Stripe puis renouvellement en espèces, part offerte montrée, sans la part d'une autre adhésion, article unique et mode de paiement (test 12) ;
- `Booking.total_paid` avec un avoir.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/affichage_des_ventes.py` | `noms_des_moyens_nets_de_la_vente` |
| `BaseBillet/models.py` | `LigneArticle.moyens_de_paiement_de_sa_vente` passe par la fonction commune |
| `BaseBillet/tasks.py`, `BaseBillet/templates/invoice/invoice.html` | Facture : dernière ligne payée, paiement Stripe entier ou parts regroupées, part offerte, mode de paiement lu dans les règlements |
| `Administration/admin_tenant.py` | Préchargements (liste, onglet, fiche utilisateur), moyens nets, `total_decimal` |
| `Administration/importers/lignearticle_exporter.py` | Colonne « Moyens de la vente » |
| `booking/models.py` | `total_paid` compte les avoirs ; docstring de `_lignes_hors_stripe` |
| `tests/pytest/test_stripe_refund.py` | Marque `django_db` sur le test qui écrit une vente |

## G-3b — Ancien LaBoutik (T3, T10)

### Resume / Summary
- Les envois ne changent pas de forme : un message par ligne (`send_sale_to_laboutik`, `send_refund_to_laboutik`), anti-doublon `sended_to_laboutik`, mêmes champs et **mêmes charges utiles** qu'avant. Les charges utiles sont figées par des tests de non-régression : vente Stripe à un règlement, panier « 2 billets + adhésion » (3 messages), remboursement Stripe, vente gratuite.
- `LigneArticleSerializer` (`ApiBillet/serializers.py`) : `payment_method`, `asset` et `wallet` se lisent dans **le règlement d'argent de la vente** (hors offert), par `moyen_monnaie_et_portefeuille_envoyes_a_l_ancien_laboutik` :
  - vente à plusieurs règlements : le règlement d'argent (hors FREE), le premier écrit ;
  - vente gratuite réglée sans règlement : moyen « NA », asset et wallet vides, comme avant ;
  - **ligne héritée sans vente** (écrite avant le chantier) : elle garde ses propres champs, comme avant. Ce cas est **retiré en fiche H**, avec ces champs de la ligne ;
  - moyen SEPA : la ligne et le règlement disent la même chose dans les flux d'aujourd'hui. Sans règle de repli, le règlement fait foi.
- `send_sale_to_laboutik` : si la vente de la ligne n'est pas encore réglée (encaissement en échec), **rien n'est posté**. La tâche se relance avec une attente croissante plafonnée (`min(3 ** essais, 1800)` s), dans sa limite d'essais (20). Ensuite, elle abandonne et écrit une erreur dans le journal.
- `send_sale_to_laboutik` : une vente ANNULÉE (Stripe a dit « non ») ne sera jamais réglée. La tâche abandonne tout de suite, sans relance, avec une ligne d'information au journal.
- `send_refund_to_laboutik` : même charge utile, lue dans le règlement de la vente d'avoir. Celle-ci est toujours réglée avant que la ligne passe « remboursée ».
- Retrait de l'import inutilisé de `send_sale_to_laboutik` dans `Administration/admin_tenant.py`. Les patchs des tests visent maintenant `BaseBillet.tasks.send_sale_to_laboutik.delay` (`fabriques_reservation.vente_admin_especes`, `test_admin_reservation_add.py`).

### Tests ajoutés / Added tests
`tests/pytest/test_lecteurs_montants_entiers.py`. La vraie tâche tourne ; le réseau est simulé.
- Fiche test 18 : vente à un règlement ; panier 2 billets + adhésion, 3 messages.
- T3 : remboursement.
- Anti-doublon (vente et remboursement).
- Vente annulée : abandon sans relance.
- Vente gratuite sans règlement.
- Ligne héritée sans vente.
- Moyen, asset et wallet lus dans le règlement ; vente à plusieurs règlements.
- Vente pas réglée : relance, attente plafonnée, abandon journalisé.
- Nombre de requêtes de l'onglet des ventes d'une adhésion (G-3a-bis).

### Tests réécrits / Rewritten tests
| Test | Raison / Reason |
|---|---|
| `tests/pytest/fabriques_reservation.py` `vente_admin_especes` | L'import patché a été retiré d'`admin_tenant.py` : le patch vise la tâche elle-même |
| `tests/pytest/test_admin_reservation_add.py` (5 patchs) | Même raison ; l'assertion « rien n'est envoyé » reste |

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/serializers.py` | `moyen_monnaie_et_portefeuille_envoyes_a_l_ancien_laboutik`, `LigneArticleSerializer` (3 champs lus dans le règlement) |
| `BaseBillet/tasks.py` | `send_sale_to_laboutik` : relance tant que la vente n'est pas réglée ; commentaire de `send_refund_to_laboutik` |
| `Administration/admin_tenant.py` | Import inutilisé retiré |

## G-3c-1 — Fiche « Vente » de l'admin (lecture seule) et export fiscal pour tous

### Resume / Summary
- **`VenteAdmin`** (`/admin/BaseBillet/vente/`). Il montre chaque vente du lieu, toutes origines, en **lecture seule** : ajout, modification et suppression sont refusés.
  - **Liste** : numéro, date (heure du lieu), origine, point de vente, client (e-mail, ou numéro de carte), total, moyens (badges avec les libellés et l'ordre de la caisse, sans l'offert), nature et statut (badges).
  - **Filtres** : « À vérifier » (ventes en attente depuis plus d'une heure, ventes avec un article « Écart d'encaissement »), moyen (au moins un règlement de ce moyen), origine, point de vente, nature, statut, date d'encaissement.
  - **Recherche** : numéro exact, e-mail du client, carte. Le nombre de requêtes reste constant (point de vente, client, carte, règlements et ventes dérivées préchargés).
  - **Fiche** : en-tête et totaux ; inline « Articles » (produit, tarif, quantité, prix unitaire, offert, total, TVA) ; inline « Règlements » (moyen, monnaie, montant, référence externe) ; lien vers la vente liée et vers les ventes dérivées ; badge **« Intégrité OK »**, ou **« Intégrité KO »** en rouge avec son explication, d'après l'empreinte recalculée par `calculer_hmac_vente`.
- **Menu « Ventes & comptabilité »** : « **Ventes** » en premier, puis le rapport des ventes (clôtures), puis le plan comptable.
- **Export fiscal pour tous les lieux.** L'archive couvre toutes les origines, donc le bouton de la liste des clôtures est proposé avec ou sans module caisse. Il pointe vers une route de l'admin de la comptabilité (`/admin/comptabilite/cloturecaisse/export-fiscal/`, `ClotureCaisseAdmin.export_fiscal`). La logique de l'envoi (période, archive, journal) est mise en commun, sans recopie : `laboutik/archivage.py` `reponse_de_l_export_fiscal`, appelée aussi par la route de la caisse. La constante des 365 jours passe dans `laboutik/archivage.py`.

Nouvelles chaînes i18n : « Ventes », « À vérifier », « Article(s) », « Règlement(s) », « Produit », « Tarif », « Prix unitaire », « Offert », « Monnaie », « N° », « Client », « Total catalogue », « Total offert », « Moyens », « Vente liée », « Ventes dérivées », « Intégrité », « Intégrité OK », « Intégrité KO », la phrase d'explication KO, « Pas encore scellée ». Le workflow i18n est à lancer par le mainteneur.

Constat pour H : dans la liste et la fiche, un règlement cashless s'écrit par le nom de son moyen, et une vente en points par un nom d'unité générique. Les vrais noms des monnaies demanderaient des requêtes par ligne.

### Tests ajoutés / Added tests
- `tests/pytest/test_admin_vente.py` (nouveau) : menu, colonnes, client par sa carte, recherche par numéro, filtres (moyen, origine, nature, statut, point de vente), « À vérifier » (fiche, test 16), nombre de requêtes constant, fiche avec articles, règlements et intégrité OK (fiche, test 14), intégrité KO, liens vente liée et ventes dérivées, permissions refusées.
- `tests/pytest/test_archive_lne_ventes.py` : export fiscal sans module caisse, avec le bouton, le formulaire et l'archive ZIP.

### Tests réécrits / Rewritten tests
| Test | Raison / Reason |
|---|---|
| `test_archive_lne_ventes.py` `test_bouton_export_fiscal_absent_sans_module_caisse` → `test_bouton_export_fiscal_present_sans_module_caisse` | Le bouton est maintenant proposé à tous les lieux (décision de G-3c-1) |

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `VenteAdmin`, ses deux inlines, les filtres « À vérifier » et « Moyen » |
| `Administration/admin/dashboard.py` | « Ventes » en tête du menu « Ventes & comptabilité » |
| `comptabilite/admin.py` | Route `export-fiscal/` de l'admin, bouton pour tous les lieux |
| `comptabilite/templates/comptabilite/admin/changelist_before.html` | Commentaire du bandeau |
| `laboutik/archivage.py` | `reponse_de_l_export_fiscal`, `NOMBRE_DE_JOURS_MAXIMUM_D_UN_EXPORT_FISCAL` |
| `laboutik/views.py` | La route de la caisse appelle la logique commune |

## G-3c-2 — Actions de la fiche « Vente »

### Resume / Summary
- **« Avoir total »** (action de la fiche, `/admin/BaseBillet/vente/<uuid>/avoir_total/`). C'est l'avoir de tout ce qui reste à rendre sur la vente : UNE vente AVOIR, liée et réglée.
  - Il passe par la nouvelle fonction de service `ecrire_la_vente_d_avoir_d_une_vente` (`BaseBillet/services_vente.py`) : chaque ligne est verrouillée et sa quantité restante relue, un article d'avoir est écrit par ligne par `ajouter_l_article_d_avoir`, puis les égalités sont vérifiées à l'encaissement.
  - Les règlements suivent la règle commune, désormais écrite une seule fois (`ajouter_les_reglements_d_un_avoir`, partagée avec l'avoir d'une ligne) :
    - jetons cadeau : un règlement « jetons » par article ;
    - Stripe (D27) : un règlement négatif au moyen Stripe d'origine, référence vide, aucun appel à Stripe, et un rappel de rembourser depuis le tableau de bord Stripe ;
    - tout autre argent : **un seul** « Remboursé par » (Q-G10) ;
    - la part offerte : un règlement « offert ».
  - Le champ « Remboursé par » n'apparaît que s'il reste de l'argent hors Stripe et hors jetons. L'écran est celui de l'avoir d'une ligne (`emettre_avoir.html`), avec le récapitulatif de la vente.
  - **Refus** (message d'erreur, rien n'est écrit) : nature autre que VENTE, vente pas réglée, vente déjà remboursée en totalité. Une vente remboursée **en partie** reçoit l'avoir de ce qui reste.
  - Une vente couverte par une clôture J n'est **pas** refusée : l'avoir est une nouvelle opération, comptée dans le service en cours, comme l'avoir d'une ligne.
- **« Rejouer l'encaissement »** (`…/rejouer_encaissement/`, écran de confirmation puis POST). Un appel à `encaisser_vente_stripe(paiement)`, **jamais** `paiement.save()`. Refusé, avec un message, pour :
  - une vente pas en attente ;
  - une vente sans paiement Stripe ;
  - un paiement pas encore payé ;
  - un refus du service.
- **Lien vers Stripe** dans les règlements de la fiche : un remboursement (`re_…`) pointe vers sa page dans le tableau de bord Stripe, un paiement vers la page de son PaymentIntent. Le lien vers la vente liée existe depuis G-3c-1.
- `ecrire_la_vente_d_avoir_d_une_ligne` est réécrite sur `ajouter_les_reglements_d_un_avoir`, sans changer son comportement : les tests des avoirs restent verts.
- **Test 19 de la fiche** : une garde vérifie qu'aucun lecteur des fichiers des §2 à §4 ne multiplie `amount × qty`. Les exceptions sont explicites, avec leur raison : `LigneArticle.total()` (retiré en H), la branche « ligne sans vente » du chaînage HMAC par ligne (retirée en H). Les anciens moteurs `laboutik/reports.py` et `comptabilite/services.py`, retirés entiers en H, sont hors de la liste.

Nouvelles chaînes i18n : « Avoir total », « Avoir émis. », « Rejouer l'encaissement », « Vente encaissée. », les messages de refus, « tout ce qui reste à rendre », « total de la vente », « Référence », « Voir sur Stripe », la phrase d'explication de l'écran de rejeu. Le workflow i18n est à lancer par le mainteneur.

### Tests ajoutés / Added tests
- `tests/pytest/test_admin_vente.py` :
  - avoir total en espèces (fiche, test 15) ;
  - deux moyens rendus par un seul moyen (Q-G10) ;
  - vente entièrement offerte, sans champ ;
  - vente Stripe (D27) ;
  - vente déjà remboursée en partie ;
  - sans « Remboursé par » ;
  - refus : pas réglée, déjà remboursée, nature AVOIR ou CORRECTION ;
  - rejouer l'encaissement (fiche, test 16b) et ses deux refus ;
  - lien vers le remboursement Stripe.
- `tests/pytest/test_lecteurs_montants_entiers.py` : avoir total permis après la J (schéma dédié) ; garde « aucun lecteur ne multiplie `amount × qty` » (fiche, test 19).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `ajouter_les_reglements_d_un_avoir` (règle commune), `ecrire_la_vente_d_avoir_d_une_vente` ; `ecrire_la_vente_d_avoir_d_une_ligne` réécrite sur la règle commune |
| `Administration/admin_tenant.py` | Actions `avoir_total` et `rejouer_encaissement` de `VenteAdmin` ; lien Stripe dans l'inline des règlements |
| `Administration/templates/admin/lignearticle/emettre_avoir.html` | Récapitulatif d'une vente entière |
| `Administration/templates/admin/vente/rejouer_encaissement.html` | Nouveau : écran de confirmation du rejeu |

---

## G-3-bis — Relecture de G-3b et G-3c

### Resume / Summary
- **Avoir total refusé** sur deux sortes de ventes. Le refus est fait deux fois : par l'écran de l'admin, avant l'affichage, et par le service `ecrire_la_vente_d_avoir_d_une_vente`.
  - Une vente qui porte un **écart d'encaissement** (reçu en plus ou en moins). Message : « Cette vente a un écart d'encaissement : l'avoir total n'est pas possible. Faites un avoir ligne par ligne. » L'avoir d'une ligne reste possible sur ces ventes : rien ne l'empêche.
  - Une vente qui contient une **recharge de carte**, c'est-à-dire un article hors chiffre d'affaires qui n'est pas un écart. L'avoir d'une ligne n'est pas touché.
  - Une vente qui n'est pas en euros (points, temps) est aussi refusée par l'écran.
- **L'écran de l'avoir total** :
  - il annonce ce qui sera rendu, par catégorie : au moyen choisi, depuis Stripe, en jetons, offert annulé. Ces montants sont calculés comme le service les calcule (`apercu_des_montants_d_un_avoir`, la règle commune `_catalogue_impose_et_part_offerte_d_un_avoir`) ;
  - le rappel Stripe dit la somme ;
  - le titre est « Avoir total de la vente n° N » ;
  - « Remboursé par » est pré-rempli quand la vente n'a qu'un moyen d'argent, et que ce moyen est dans la liste.
- **Filtre « À vérifier »** : une vente en attente depuis plus d'une heure n'y est que si un paiement Stripe est payé (ou validé), ou s'il n'y a aucun paiement Stripe. Un panier abandonné (session expirée) n'y est plus.
- **Rejouer l'encaissement** :
  - le paiement choisi est le plus récent parmi les paiements **payés** ;
  - après un rejeu réussi, les billets et adhésions de la vente partent à l'ancien LaBoutik (`send_sale_to_laboutik.delay`, après la validation en base).
- **Les deux actions** :
  - une égalité rompue ou une erreur de la base devient un message d'erreur, pas une page 500 ;
  - les refus métier sont écrits au journal en avertissement ;
  - leurs boutons ne sont montrés que quand l'action a un sens. Le masquage passe par `get_actions_detail`, et non par la permission par objet d'Unfold : cette permission sert aussi à l'appel de l'action, qui répondrait 403 au lieu du message de refus.
- **Liste** :
  - une vente pas encore réglée montre la somme de ses articles (sous-requête, nombre de requêtes inchangé) ;
  - un nombre trop grand pour la colonne (2^31 et plus) n'est plus cherché comme numéro ;
  - le préchargement des ventes dérivées est retiré.
- **Badge d'intégrité** :
  - la comparaison est faite à temps constant (`hmac.compare_digest`) ;
  - sans clé, le badge dit « Pas de clé d'intégrité pour ce lieu ».
- **Ancien LaBoutik** :
  - le moyen d'une ligne est lu une seule fois, et les règlements sont triés par date puis par clé ;
  - une ligne validée dans une vente annulée est écrite au journal en avertissement.

Nouvelles chaînes i18n :
- les deux messages de refus (écart, recharge) et celui de la vente qui n'est pas en euros ;
- « Ce qui sera rendu », « Rendu au moyen choisi ci-dessous : », « À rembourser depuis Stripe : », « Jetons cadeau rendus (dette, pas d'argent) : », « Offert annulé (aucun argent) : » ;
- « Avoir total de la vente n° %(numero)s », « Avoir total de la vente » ;
- « Le paiement Stripe de cette vente n'est pas payé : rien à rejouer. » ;
- « Pas de clé d'intégrité pour ce lieu ».

Le workflow i18n est à lancer par le mainteneur.

### Tests ajoutés / Added tests
- `tests/pytest/test_admin_vente.py` :
  - avoir total refusé, côté service et côté admin, pour un écart reçu en plus et pour un écart reçu en moins ;
  - avoir total refusé pour une recharge ;
  - filtre « À vérifier » : la session expirée en est absente, le paiement payé y est présent ;
  - le rejeu envoie le billet à l'ancien LaBoutik ;
  - l'écran annonce le reste à rendre, et son titre ;
  - le total d'une vente en attente dans la liste ;
  - le rejeu est refusé quand le paiement n'est pas payé, et il prend le paiement payé même s'il est plus ancien ;
  - une recherche de 12 chiffres ;
  - les boutons montrés seulement quand ils ont un sens ;
  - le pré-remplissage de « Remboursé par » ;
  - le badge sans clé ;
  - une erreur de la base, sur les deux actions : un message, pas de 500.
- Le test de la vente Stripe vérifie aussi la somme dans le rappel.
- `tests/pytest/test_lecteurs_montants_entiers.py` :
  - un seul calcul du moyen par ligne ;
  - l'abandon cite la vente ;
  - la vente annulée est écrite en avertissement.
- `tests/pytest/test_archive_lne_ventes.py` : la date de début de l'export est le jour du test moins 30 jours, dans le fuseau du lieu.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | Gardes « écart » et « recharge » de l'avoir total ; `apercu_des_montants_d_un_avoir` |
| `Administration/admin_tenant.py` | Refus, montants de l'écran, pré-remplissage, filtre, rejeu, exceptions, boutons, total de la liste, recherche, badge |
| `Administration/templates/admin/lignearticle/emettre_avoir.html` | Montants rendus par catégorie, titre, somme du rappel Stripe |
| `ApiBillet/serializers.py` | Un seul calcul du moyen par ligne, tri `datetime, pk` |
| `BaseBillet/tasks.py` | `Vente.Statut`, avertissement pour une vente annulée |

---

## Comment tester (a la main) / Manual test

### G-3a — Test 1 : adhésion payée avec deux moyens
1. À la caisse, vendre une adhésion à 35 € avec une carte NFC qui porte 10 € de monnaie locale, et régler le reste (25 €) par CB sur l'écran de complément.
2. Admin, fiche de l'adhésion, demander le reçu (ou ouvrir `/memberships/<uuid>/invoice/`).
3. Attendu : UN article (quantité 1, 35,00 €), un total de 35,00 €, et un mode de paiement qui cite la monnaie locale et la carte bancaire.

### G-3a — Test 2 : adhésion et bière dans le même panier
1. À la caisse, vendre une adhésion et une bière dans le même panier, en espèces.
2. Ouvrir la facture de l'adhésion : seule l'adhésion y figure, et le total est le prix de l'adhésion.

### G-3a — Test 2 bis : adhésion renouvelée
1. Admin, une adhésion payée en espèces, puis « Ajouter un paiement » (renouvellement) en espèces.
2. Ouvrir la facture : seul le renouvellement y figure, total = son montant.

### G-3a — Test 3 : liste des ventes et export
1. Admin, liste des ventes : sur une ligne en partie offerte, la colonne « Total » montre le net payé, et « Moyen de paiement » les moyens des règlements de la vente.
2. Exporter la sélection : les colonnes « Montant » (net), « Total HT », « Total TVA » et « N° de vente » sont remplies ; « Moyens de la vente » donne les moyens nets.
3. À la caisse, corriger en CB une vente payée en espèces : dans la liste des ventes de l'admin et dans l'export, son moyen devient « Carte bancaire ».

### G-3b — Test 5 : ancien LaBoutik
1. Avec un serveur de l'ancien LaBoutik configuré, acheter en ligne deux billets et une adhésion dans un même panier, payés par Stripe.
2. L'ancien LaBoutik reçoit trois ventes, au moyen « Stripe CB », comme avant.
3. Rembourser un billet depuis « Mon compte » : l'ancien LaBoutik reçoit un remboursement d'une unité.

### G-3c-1 — Test 6 : fiche « Vente »
1. Admin, menu « Ventes & comptabilité » : « Ventes » est en premier.
2. La liste montre les ventes de toutes les origines. Rechercher un e-mail de client, puis un numéro de vente. Filtrer par moyen « Carte bancaire ».
3. Filtre « À vérifier » : une vente en ligne restée en attente depuis plus d'une heure y figure.
4. Ouvrir une vente : ses articles, ses règlements, le badge vert « Intégrité OK ». Aucun bouton « Enregistrer » ni « Supprimer ».
5. Pour une vente corrigée à la caisse, les liens vers la correction et retour fonctionnent.

### G-3c-1 — Test 7 : export fiscal sans caisse
1. Sur un lieu sans module caisse, ouvrir « Rapport des ventes » : le bouton « Export fiscal » est présent.
2. Choisir une date de début, valider : une archive ZIP se télécharge.

### G-3c-2 — Test 8 : avoir total et rejeu
1. Fiche d'une vente de caisse payée en deux moyens : « Avoir total », choisir « Espèces », valider. Une vente AVOIR liée s'ouvre, avec un seul règlement espèces du total.
2. Refaire « Avoir total » sur la même vente : refusé (« déjà remboursée en totalité »).
3. Fiche d'une vente en ligne payée par Stripe : « Avoir total » sans champ, puis le rappel « Remboursez cette somme depuis votre tableau de bord Stripe ».
4. Filtre « À vérifier », une vente Stripe en attente : « Rejouer l'encaissement », valider. La vente passe « Réglée ».
5. Sur la fiche d'un avoir remboursé par Stripe, la référence `re_…` est un lien vers Stripe.

### G-3-bis — Test 9 : refus et écran de l'avoir total
1. Fiche d'une vente de caisse payée par CB seule : « Avoir total » montre « Rendu au moyen choisi ci-dessous : » avec le total, et « Carte bancaire » est déjà choisi.
2. Fiche d'une vente qui porte un écart d'encaissement (filtre « À vérifier ») : pas de bouton « Avoir total ».
3. Fiche d'une vente réglée : pas de bouton « Rejouer l'encaissement ».

### G-3a — Test 4 : fiche utilisateur
1. Admin, fiche d'un client qui a une réservation payée avec deux moyens à la caisse.
2. La colonne « Payé » montre le total juste (10,50 € pour 3 × 3,50 €, et non 10,49 €). La colonne « Paiement » montre les moyens des règlements.
