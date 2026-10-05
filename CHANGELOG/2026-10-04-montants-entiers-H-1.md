# Une ligne par article (chantier 05, fiche H, session H-1) / One line per item (worksite 05, sheet H, session H-1)

**Date :** 2026-10-04
**Migration :** Oui — `BaseBillet/migrations/0234_vente_raison.py` (H-1a : champ `Vente.raison`) ; `BaseBillet/migrations/0235_lignearticle_part_en_jetons.py` (H-1b-1 : champ `LigneArticle.part_en_jetons` et sa contrainte).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary
**Quoi / What :** la session H-1 écrit une ligne par article (un article payé avec deux moyens = une ligne et deux règlements). Elle se fait en étapes : H-1a, H-1b-1, H-1b-2, H-1c, H-1d. /
Session H-1 writes one line per item, in steps H-1a to H-1d.

**Pourquoi / Why :** fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md` §2 et §2.1 ; tronc `CHANTIER-05-montants-entiers.md` D14, D27 ; décisions Q-H1 à Q-H4 et Q-H6 (SUIVI §5).

## H-1a — Les lecteurs du moyen passent sur les règlements

### Resume / Summary
**Quoi / What :** tout code qui décide quelque chose en lisant le moyen d'une ligne (`LigneArticle.payment_method`) lit désormais les **règlements nets** de la vente et de ses ventes CORRECTION. Il marche sur les deux formes : les parts d'aujourd'hui, et la ligne unique de demain (moyen vide, plusieurs règlements). /
Every reader that decides on the line's method now reads the net payments of the sale and of its CORRECTION sales; it works on today's parts and on tomorrow's single line.

**Pourquoi / Why :** après la fusion (H-1b-2), une ligne n'aura plus UN moyen, et son moyen restera vide (Q-H2). H-1a prépare la fusion sans la faire. /
After the merge a line has no single method; H-1a prepares the merge without doing it.

- **Correction de moyen (D14)** : la route `corriger_moyen_paiement` ne modifie **plus aucune ligne**. Elle écrit une vente CORRECTION qui déplace le net du moyen corrigé (règlements −ancien / +nouveau, même montant), et une trace `CorrectionPaiement` par article de la vente.
  - Nouveau contrat : `ligne_uuid` sert seulement à retrouver la vente ; `ancien_moyen` est LE moyen corrigé.
  - Le bouton « Corriger » du détail est proposé par moyen corrigeable au net non nul. Il transmet `ligne_uuid` et `ancien_moyen`. Sa zone a l'id `correction-zone-<uuid de la vente>-<code du moyen>`, et les refus de la route y sont rendus (`HX-Retarget`).
  - Le formulaire affiche le net du moyen.
  - Une seule fonction des refus, `raison_du_refus_de_correction(vente, moyen)`. Elle reprend les refus existants : cashless, hors argent, moyen hors liste, vente pas réglée, vente hors caisse, vente couverte par une J. Elle ajoute « net du moyen nul », qui sert aussi de garde anti double envoi.
  - Deux corrections successives restent permises.
  - Nouveau `montant_net_du_moyen_dans_la_vente`. La règle du net est extraite dans `reglements_nets_de_la_vente` (`laboutik/affichage_des_ventes.py`), que lisent aussi `noms_des_moyens_nets_de_la_vente` et le « Remboursé par ».
  - `lignes_que_la_correction_deplace` est retirée. /
  The correction changes no line; a CORRECTION sale moves the corrected method's net; one button per correctable method with a non-zero net; one refusal function; the net rule is extracted.
- **Raison de la correction (Q-H6)** : nouveau champ `Vente.raison` (texte, vide par défaut). La route y écrit la raison du caissier avant l'encaissement. La fiche « Vente » de l'admin le montre seulement s'il n'est pas vide. Le champ n'entre ni dans l'empreinte ni dans l'archive. /
  New `Vente.raison`, set by the route, shown on the admin "Sale" page when not empty; not in the fingerprint nor the archive.
- **« Remboursé par » pré-rempli** : on prend le seul moyen d'argent des règlements nets non nuls (vente + corrections), sans l'offert ni les jetons cadeau, et seulement s'il est dans la liste du champ. Sinon, le champ est vide et obligatoire. Le cashless compte comme un moyen. Une ligne sans vente garde son moyen historique.
  - Fonctions : `moyen_d_argent_unique_de_la_vente`, `moyen_d_origine_de_la_ligne` (`Administration/admin_tenant.py`).
  - Écrans : avoir d'une ligne, « Avoir total » (qui oubliait les corrections), annulation des réservations et des billets dans l'admin, annulation d'adhésion. /
  Pre-filled with the single net money method, on the four screens.
- **Admin des lignes (« Entries », Q-H2)** : la fiche ne montre plus les champs moyen, monnaie, carte ni portefeuille de la ligne. L'export perd les colonnes « Carte cashless » et « Wallet from ». La colonne « Moyen de paiement » de la liste, lue sur la vente, reste. /
  The line page and the export drop the line's payment fields.
- **Menu** : l'entrée « Ancien rapport caisse » est retirée de « Ventes & comptabilité ». Ses adresses restent jusqu'à H-2. /
  The old POS report leaves the menu.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `montant_net_du_moyen_dans_la_vente`, `raison_du_refus_de_correction(vente, moyen)`, `_identifiant_de_la_zone_de_correction`, `_refus_de_correction`, `_contexte_du_detail_d_une_vente` (boutons par moyen), `detail_vente` (préchargement), `formulaire_correction`, `corriger_moyen_paiement` ; `lignes_que_la_correction_deplace` retirée |
| `laboutik/affichage_des_ventes.py` | `reglements_nets_de_la_vente` (règle du net extraite) |
| `laboutik/serializers.py` | Commentaire de `ancien_moyen` |
| `laboutik/templates/laboutik/partial/hx_detail_vente.html` | Bouton et zone par moyen |
| `laboutik/templates/laboutik/partial/hx_corriger_moyen_paiement.html` | `ancien_moyen` posté = le moyen corrigé |
| `BaseBillet/models_vente.py`, `BaseBillet/migrations/0234_vente_raison.py` | Champ `Vente.raison` |
| `Administration/admin_tenant.py` | Pré-remplissages, `VenteAdmin.get_fieldsets` (raison), `LigneArticleAdmin.exclude` |
| `Administration/importers/lignearticle_exporter.py` | Colonnes carte et wallet retirées |
| `Administration/admin/dashboard.py` | Entrée « Ancien rapport caisse » retirée |
| `BaseBillet/views.py` | Pré-remplissage de l'annulation d'adhésion |
| `comptabilite/rapport.py` | Docstring de `_parts_deplacees_par_les_corrections` |
| `tests/pytest/test_une_ligne_par_article_lecteurs.py` | Nouveau : 13 tests |
| `tests/pytest/test_caisse_ecrit_la_vente.py`, `test_menu_ventes.py`, `test_corrections_fond_sortie.py`, `test_menu_rapports.py`, `test_lecteurs_montants_entiers.py` | Adaptés au nouveau contrat (la ligne ne change plus, `ancien_moyen` = le moyen corrigé, zone par moyen, nouveau message, menu) |

### Chaînes i18n ajoutées / Added i18n strings
- « Il ne reste rien à corriger pour le moyen « %(moyen)s » sur cette vente : elle vient peut-être d'être corrigée. Rouvrez la vente pour voir ses règlements. » (texte de H-1a-bis)
- « Raison » (verbose_name de `Vente.raison`)
- « Raison écrite par le caissier lors d'une correction de moyen de paiement. »

Ne sont plus utilisées par le code : « Ancien rapport caisse », « Ce paiement vient d'être corrigé (moyen actuel : %(moyen)s). Rouvrez la vente pour le corriger à nouveau. », « Rien à corriger : le montant est nul. ». Workflow i18n à lancer par le mainteneur.

### Tests
- Rouge avant le code : `13 failed`.
- Vert après le code : `test_une_ligne_par_article_lecteurs.py` 13 passed ; voisins verts (`test_menu_ventes`, `test_caisse_ecrit_la_vente`, `test_menu_rapports`, `test_corrections_fond_sortie`, `test_admin_vente`, `test_avoirs_ecrivent_la_vente`, `test_hors_argent_offerts`, `test_vente_en_points`, `test_lecteurs_montants_entiers`, `test_rapport_unique*`, `test_archive_lne_ventes`) ; les 24 tests de caractérisation passent sans modification. `test_admin_tableau_de_bord.py` a 2 échecs sans lien avec cette session : `/admin/` redirige vers la page de connexion pour l'admin du lieu de la base de dev.

## H-1a-bis — Corrections de la relecture de H-1a

### Resume / Summary
- **Natures corrigeables** : seules une vente (`VENTE`) et un avoir de caisse (`AVOIR`, ex. retour de consigne rendu en espèces) se corrigent. Un vidage de carte (`VIDAGE_CARTE`) ou une correction sont refusés : aucun bouton « Corriger », POST refusé (`NATURES_DE_VENTE_CORRIGEABLES`, `laboutik/views.py`). /
  Only a sale or a register credit note can be corrected; a card emptying cannot.
- **`ancien_moyen` validé** : `ChoiceField` sur les moyens de paiement connus (un code inventé est refusé par le formulaire, avant toute règle métier). Un refus n'a de cible (`HX-Retarget`) que pour un moyen corrigeable. /
  `ancien_moyen` must be a known method; a refusal is retargeted only for a correctable method.
- **Message** du net nul : « Il ne reste rien à corriger pour le moyen « … » sur cette vente… ».
- **Lisibilité** : docstring et copie explicite dans `VenteAdmin.get_fieldsets`, TODO de retrait de `CorrectionPaiement` (H-2), commentaires de l'export et du CSS de la zone de correction.
- **Helpers du « Remboursé par » dans le service** : `moyen_d_argent_unique_de_la_vente`, `moyen_d_origine_de_la_ligne` et `MOYENS_IGNORES_POUR_LE_REMBOURSE_PAR` passent dans `BaseBillet/services_vente.py`. L'admin et `BaseBillet/views.py` les importent en tête de module. La règle du net (`reglements_nets_de_la_vente`) est importée localement dans `moyen_d_argent_unique_de_la_vente` : un import en tête ferait un cycle (`services_vente` → `laboutik.affichage_des_ventes` → `comptabilite.rapport` / `laboutik.plan_comptable` → `services_vente`). /
  The pre-fill helpers move to the sale service; the net rule is imported locally to avoid an import cycle.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `NATURES_DE_VENTE_CORRIGEABLES`, règle de nature dans `raison_du_refus_de_correction`, nouveau message, `_refus_de_correction` (cible seulement pour un moyen corrigeable), TODO H-2 |
| `laboutik/serializers.py` | `ancien_moyen` en `ChoiceField` (`PaymentMethod.choices`) |
| `Administration/admin_tenant.py` | `VenteAdmin.get_fieldsets` : docstring, copie explicite du dictionnaire ; helpers du « Remboursé par » importés du service |
| `BaseBillet/services_vente.py` | `MOYENS_IGNORES_POUR_LE_REMBOURSE_PAR`, `moyen_d_argent_unique_de_la_vente`, `moyen_d_origine_de_la_ligne` |
| `BaseBillet/views.py` | `moyen_d_origine_de_la_ligne` importé en tête depuis le service |
| `Administration/importers/lignearticle_exporter.py` | Commentaire au présent |
| `laboutik/static/css/ventes.css` | Commentaire : identifiant de la zone par moyen |
| `tests/pytest/test_une_ligne_par_article_lecteurs.py` | Tests 14 à 17, test 11 renforcé (champs exportés) |
| `tests/pytest/test_menu_ventes.py`, `tests/pytest/test_caisse_ecrit_la_vente.py` | Nouveau texte du message |

### Chaînes i18n ajoutées / Added i18n strings
- « Seule une vente ou un avoir peut être corrigé. »
- « Moyen de paiement à corriger inconnu : rouvrez la vente. »
- Le message du net nul change de texte (voir H-1a). Workflow i18n à lancer par le mainteneur.

## H-1b-1 — Le champ « part payée en jetons » et tous ses lecteurs

### Resume / Summary
**Quoi / What :** nouveau champ entier `LigneArticle.part_en_jetons` (centimes du net payés en jetons cadeau, LG). La formule unique (`calculer_montants_article`) met la part en jetons hors TVA : HT = jetons + arrondi_demi_haut((net − jetons) × 100 / (100 + taux)), TVA = net − HT. Tous les lecteurs passent sur ce champ, plus aucun ne reconnaît les jetons par `ligne.payment_method == LG`. Pas encore de fusion : la caisse et la tireuse écrivent toujours une ligne par moyen, et leur part LG porte `part_en_jetons` = son argent. /
New `LigneArticle.part_en_jetons` field; the single formula takes the token part out of VAT; every reader reads the field, never the line's LG method; the register and the tap set it on their LG parts (no merge yet).

**Pourquoi / Why :** décision Q-H1 (2026-10-04) : un article payé en partie en jetons et en partie en argent deviendra UNE ligne (H-1b-2). D8 bis inchangée : un jeton dépensé est une vente, dans le CA, hors TVA, au 707900 ; ce n'est pas de l'offert. /
Q-H1: a mixed item becomes one line; D8 bis unchanged.

- **Base** : contrainte `lignearticle_part_en_jetons_entre_zero_et_le_net` (entre 0 et le net, même signe ; 0 hors chiffre d'affaires) ; le champ entre dans la garde d'immutabilité d'une ligne réglée.
- **Service** : `calculer_montants_article` et `ajouter_article` reçoivent `part_en_jetons` (entier ; hors bornes, `float`, ou article hors chiffre d'affaires → `ValueError`).
- **Empreinte de la vente** (`calculer_hmac_vente`) : le champ entre dans le message de chaque article, au format 1, sans nouveau numéro de format. **La base de dev est à régénérer : les ventes déjà scellées ne se vérifient plus.** Archive : colonne `part_en_jetons` dans `articles.csv`, README de l'empreinte à jour.
- **TVA de la caisse** (`_taux_tva_de_la_ligne_de_caisse`) : la règle « LG → 0 » est retirée. Une part LG garde le taux du produit, et sa part en jetons lui donne une TVA nulle. Seuls la caisse en cascade et la tireuse produisent des lignes LG du chiffre d'affaires ; les écrans de l'admin ne proposent pas LG (`PaymentMethod.classic()`).
- **Rapport** : CA par taux, la part en jetons va au taux « 0.00 » (HT = TTC, TVA 0), le reste à son taux ; un taux qui ne gardait que des jetons disparaît ; total inchangé.
- **Plan comptable / FEC** : règle « 0 ter » retirée, `compte_pour_article` rend le compte du reste. Nouveau `compte_des_ventes_reglees_en_jetons` (707900). La ventilation écrit la part en jetons au 707900, le HT du reste au compte de l'article, la TVA au compte du taux ; une ligne entièrement en jetons n'écrit rien au compte de l'article. « Plan complet ? » : la section 1 ne lit plus le moyen (DISTINCT sur produit + monnaie), ignore les lignes entièrement en jetons, et exige le 707900 dès qu'un article a une part en jetons.
- **Ticket client** : TVA par taux, la part en jetons dans la ligne du taux 0.
- **Avoirs** :
  - `_montants_imposes_d_un_avoir` (ancien `_catalogue_impose_et_part_offerte_d_un_avoir`) recopie la part en jetons en miroir. Il refuse l'avoir d'une partie de la quantité d'une ligne en partie en jetons (« rembourser l'article entier »). Une ligne entièrement en jetons accepte un avoir partiel, lui aussi entièrement en jetons.
  - `ajouter_les_reglements_d_un_avoir` écrit un règlement LG négatif pour la part en jetons, avec la monnaie et la carte du règlement LG de la vente d'origine. Si cette vente a plusieurs couples (monnaie, carte) en LG, ou aucun, l'avoir est refusé. Le reste est rendu en argent (Stripe ou « Remboursé par »). Une ligne sans vente garde la lecture par son moyen LG.
  - `ligne_payee_en_jetons` devient `ligne_entierement_payee_en_jetons` : part en jetons = net, non nul. Une ligne mixte a donc de l'argent à rendre.
  - « Avoir total » (`_sommes_rendues_par_l_avoir_total`) coupe jetons et argent par le champ. /
  Database constraint and guard, service parameter, fingerprint and archive, register VAT, report, FEC and "Complete plan?", receipt, credit notes.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py`, `BaseBillet/migrations/0235_lignearticle_part_en_jetons.py` | Champ, contrainte, garde d'immutabilité ; commentaire de `part_offerte` |
| `BaseBillet/services_vente.py` | Formule, `ajouter_article`, avoirs (`_montants_imposes_d_un_avoir`, `apercu_des_montants_d_un_avoir`, `ajouter_l_article_d_avoir`, `_monnaie_et_carte_des_jetons_de_la_vente`, `ajouter_les_reglements_d_un_avoir`), `ligne_entierement_payee_en_jetons`, `ligne_sans_argent_a_rendre` |
| `laboutik/integrity.py` | Champ dans le message de l'empreinte |
| `laboutik/archivage.py` | Colonne `part_en_jetons`, README |
| `laboutik/views.py` | `_taux_tva_de_la_ligne_de_caisse` (LG retiré), `_creer_lignes_articles_cascade` (part LG) |
| `controlvanne/billing.py` | `facturer_tirage` (part LG) |
| `comptabilite/rapport.py` | `_chiffre_affaires_par_taux` |
| `comptabilite/ventilation.py` | `_ecrire_l_article_du_chiffre_d_affaires` |
| `laboutik/plan_comptable.py` | Règle 0 ter retirée, `compte_des_ventes_reglees_en_jetons`, « Plan complet ? » section 1 et 1 bis |
| `laboutik/printing/formatters.py` | TVA par taux du ticket |
| `Administration/admin_tenant.py` | `_sommes_rendues_par_l_avoir_total` |
| `tests/pytest/test_part_en_jetons.py` | Nouveau : 14 tests |
| `tests/pytest/test_caisse_ecrit_la_vente.py`, `test_tireuse_ecrit_la_vente.py` | La part LG a le taux du produit et `part_en_jetons` = son argent (TVA 0 par le champ, plus par le taux) |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py`, `test_fec_equilibre.py`, `test_plan_comptable_unique.py` | États de départ LG : `part_en_jetons` posé, comme la caisse l'écrit ; le 707900 lu par `compte_des_ventes_reglees_en_jetons`, `compte_pour_article` = compte du reste |
| `tests/pytest/test_archive_lne_ventes.py`, `test_vente_service.py` | Colonne et message de l'empreinte avec `part_en_jetons` |

### Chaînes i18n ajoutées / Added i18n strings
- « Part payée en jetons (centimes) » (verbose_name)
- « Centimes du net vendu payés en jetons cadeau. Cette part est vendue hors TVA ; la TVA de l'article porte sur le reste. » (help_text)
Workflow i18n à lancer par le mainteneur. Les messages des `ValueError` du service ne sont pas traduits, comme les autres messages du service.

### Tests
- Rouge avant le code : `14 failed` (TypeError `part_en_jetons`).
- Vert après le code : `test_part_en_jetons.py` 14 passed. Voisins verts : service, modèles, montants, caisse, tireuse, avoirs, rapport, FEC, plan comptable, archive, ticket, clôtures, vidage, menu ventes, lecteurs H-1a, admin vente. Les tests de caractérisation (`test_caracterisation_*.py`) passent sans modification. `manage.py check` et `makemigrations --check` passent.

## H-1b-1-bis — Corrections de la relecture de H-1b-1

### Resume / Summary
**Quoi / What :** l'ancien rapport de la caisse n'est plus joignable ; l'avoir de jetons payés par plusieurs cartes ; refus des jetons sur une vente en points ; corrections mineures (rapport, « Plan complet ? », ticket, textes, tests). /
The old register report is unreachable; tokens paid with several cards; no tokens on a points sale; minor fixes.

**Pourquoi / Why :** relecture Opus de H-1b-1, décisions du 2026-10-05. L'ancien moteur (`laboutik/reports.py`) recalcule la TVA depuis le taux de la ligne : faux sur une part en jetons. On coupe son accès au lieu de le corriger (retrait du moteur en H-2). /
The old engine recomputes VAT from the rate: its access is cut (removed in H-2).

- **Ancien rapport de la caisse (B1)** : route `CaisseViewSet.rapport_temps_reel` (`/laboutik/caisse/rapport-temps-reel/`) retirée, avec son gabarit `Administration/templates/admin/cloture/rapport_temps_reel.html` (plus aucun usage : le rapport temps réel est celui de l'admin de la comptabilité). L'admin de l'ancienne clôture de la caisse (`laboutik.ClotureCaisse`) n'est plus enregistré ; la classe, ses exports et le modèle restent jusqu'à H-2 (TODO). Entrées orphelines du tableau de bord retirées. Les branches `HX-Current-URL` des exports de la caisse portent un TODO H-2.
- **Avoir de jetons payés par plusieurs cartes (I1)** : `monnaie_et_carte_des_jetons_de_la_vente` (ancien `_monnaie_et_carte_des_jetons_de_la_vente`, public) refuse seulement plusieurs **monnaies**. Une monnaie et plusieurs cartes donnent un règlement LG sans carte, une seule carte le garde. Les jetons rendus forment UN règlement LG par vente d'origine (et non plus un par article ; le total et le compte ne changent pas), dont la monnaie et la carte sont lues une fois (M5). L'écran « Avoir total » fait la même lecture : des jetons de plusieurs monnaies sont refusés dès l'écran.
- **Vente en points (I2)** : `ajouter_article` refuse une part en jetons non nulle sur une vente qui n'est pas en euros.
- **Mineurs** :
  - M1 : commentaires de `LigneArticleAdmin.emettre_avoir` (« entièrement » en jetons, « montant de la ligne »).
  - M2 : la TVA par taux du ticket passe par une fonction de module, `_ajouter_a_la_ligne_de_tva`, au lieu d'une fonction imbriquée.
  - M3 : un taux n'est retiré du CA par taux que si toutes ses lignes sont entièrement en jetons ; docstring du module du rapport à jour.
  - M4 : la section 4 de « Plan complet ? » n'exige pas de compte de TVA pour une ligne dont la TVA vaut 0.
  - M6 : `test_compte_pour_article_jeton_depense_au_707900` renommé `test_jetons_au_707900_et_compte_pour_article_rend_le_compte_du_reste` ; les états de départ « comme la caisse l'écrit » passent au taux du produit (résultats inchangés). /
  Old report cut; one LG payment without card for several cards; tokens refused on points sales; minor fixes.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Route `rapport_temps_reel` retirée, import `RapportComptableService` retiré, TODO H-2 sur les branches `HX-Current-URL` |
| `Administration/admin/laboutik.py` | `ClotureCaisseAdmin` plus enregistré (TODO H-2), URL du rapport temps réel retirée du contexte |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` | Supprimé (plus aucun usage) |
| `Administration/admin/dashboard.py` | Entrées `laboutik.cloturecaisse` retirées, commentaire du menu |
| `BaseBillet/services_vente.py` | `monnaie_et_carte_des_jetons_de_la_vente`, `ajouter_les_reglements_d_un_avoir` (un règlement LG par vente d'origine), refus des jetons sur une vente en points |
| `Administration/admin_tenant.py` | `_sommes_rendues_par_l_avoir_total` lit la monnaie des jetons (refus dès l'écran), commentaires M1 |
| `laboutik/printing/formatters.py` | `_ajouter_a_la_ligne_de_tva` |
| `comptabilite/rapport.py` | `_chiffre_affaires_par_taux` (M3), docstring du module |
| `laboutik/plan_comptable.py` | « Plan complet ? » section 4 (M4) |
| `tests/pytest/test_part_en_jetons.py` | Tests 15 à 22 |
| `tests/pytest/test_rapport_unique.py`, `test_comptabilite_exports.py` | Adhésion en points, points par monnaie et offerts sur le rapport unique et son export CSV (remplacent les tests de l'ancien admin) |
| `tests/pytest/test_menu_rapports.py`, `test_une_ligne_par_article_lecteurs.py` | Absence de l'ancienne clôture vérifiée par son adresse écrite en clair (plus par `reverse`) |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py`, `test_fec_equilibre.py`, `test_plan_comptable_unique.py` | Taux du produit sur les états de départ en jetons ; renommage M6 |

### Tests retirés / Removed tests
| Test retiré | Raison | Couvert par (rapport des ventes unique) |
|---|---|---|
| `tests/pytest/test_caisse_anciens_rapports.py` (fichier, 4 tests) | Ne teste que l'ancien moteur, qui n'a plus d'écran | Les ventes de caisse dans le rapport unique : `test_rapport_unique.py`, `test_caisse_ecrit_la_vente.py`, `test_part_en_jetons.py` (jetons au taux 0) |
| `test_rapport_temps_reel.py::TestRapportTempsReel::test_rapport_temps_reel_status_200` | N'ouvre que la route retirée | `test_comptabilite_admin.py` (rapport temps réel de l'admin de la comptabilité) ; `test_part_en_jetons.py::test_ancien_rapport_caisse_n_est_plus_joignable` |
| `test_vente_en_points.py::test_le_rapport_de_cloture_de_l_admin_montre_les_ventes_en_points` | Ouvre `/admin/laboutik/cloturecaisse/<pk>/change/` | `test_vente_en_points.py::test_l_ecran_de_cloture_montre_les_ventes_en_points` (écran du Z, rapport unique) ; `test_rapport_unique.py::test_points_par_monnaie_hors_ca_et_hors_argent` |
| `test_vente_en_points.py::test_le_rapport_en_temps_reel_montre_les_ventes_en_points` | Ouvre la route retirée | `test_vente_en_points.py::test_l_ecran_du_ticket_x_montre_les_ventes_en_points` (récapitulatif en cours, rapport unique) |
| `test_vente_en_points.py::test_la_section_adhesions_de_l_admin_ecrit_l_adhesion_en_points` | Ouvre `/admin/laboutik/cloturecaisse/<pk>/change/` | `test_rapport_unique.py::test_adhesion_payee_en_points_ecrite_en_points_jamais_en_euros` (nouveau) |
| `test_vente_en_points.py::test_l_export_csv_de_l_admin_liste_les_points_et_l_adhesion` | Ouvre l'export CSV de l'ancienne clôture | `test_comptabilite_exports.py::test_csv_points_par_monnaie_et_adhesion_en_points_absente_des_euros` (nouveau) |
| `test_vente_en_points.py::test_l_export_csv_de_l_admin_liste_les_offerts` | Ouvre l'export CSV de l'ancienne clôture | `test_comptabilite_exports.py::test_csv_liste_les_offerts_avec_leurs_valeurs` (nouveau) |

À noter : l'ancien rapport nommait chaque vente en points ; le nouveau donne le total par monnaie (fiche F §8).

### Chaînes i18n / i18n strings
Aucune chaîne ajoutée. Les chaînes du gabarit supprimé ne sont plus utilisées (workflow i18n à lancer par le mainteneur).

## H-1b-2 — La caisse écrit une ligne par article

**Migration :** Non.

### Resume / Summary
**Quoi / What :** la caisse n'écrit plus de « parts » : un article du panier est UNE ligne, quelle que soit la façon de payer (carte puis CB ou espèces, jetons cadeau puis monnaie locale, deux cartes, table en NFC). /
The register no longer writes "parts": one cart item is ONE line, whatever the payment.

**Pourquoi / Why :** fiche H §2 et §2.1 ; tronc D12, D13, D15 ; décisions Q-H1, Q-H2, Q-H4 (SUIVI §5) ; refus de la pesée en quantité > 1 (orchestrateur, 2026-10-05). /
Sheet H §2; D12, D13, D15; Q-H1, Q-H2, Q-H4.

- **Une ligne par article** (`_creer_lignes_articles_cascade`) : les débits d'un même article sont additionnés. La ligne porte la vraie quantité, le prix unitaire, le total de la formule du service (plus de `total_catalogue_impose`, plus de `quantite_pour_cout`) et `part_en_jetons` = la somme de ses débits LG. Garde : l'argent débité pour l'article vaut son total catalogue, sinon `EgaliteDeVenteRompue` (rien n'est écrit). `_calculer_qty_partielles` n'est plus appelée par la caisse (la tireuse et le QR l'appellent encore : H-1c).
- **Colonnes vides (Q-H2)** : une ligne écrite par la caisse dans une vente (chemin à un moyen, cascade, recharges, retour de consigne, table) ne porte plus `payment_method`, `asset`, `carte`, `wallet`. Elle garde `uuid_transaction` et `point_de_vente`. La branche « vente absente » de `_creer_lignes_articles` ne change pas (H-3). Les paramètres `carte`, `carte_complement`, `wallet` de `_creer_lignes_articles_cascade` sont retirés.
- **Poids et volume (D15, Q-H4)** : `qty` = la quantité réelle en kg (stock en grammes ou sans stock, 3 décimales) ou en litres (stock en centilitres, 2 décimales), `amount` = le prix du kg / du litre. `_montant_poids_mesure_en_centimes` calcule ce que la caisse encaisse par la formule du service, sur cette même quantité et ce même prix : le total de la ligne vaut toujours l'argent encaissé. `weight_quantity` reste (le stock le lit). Une pesée avec une quantité de panier autre que 1 (envoi forgé, impossible depuis l'écran) est refusée : 400, rien n'est écrit, message « Une pesée se vend une seule fois par ligne… ».
- **Lecteurs de la quantité** : le détail d'une vente et le ticket montrent « 0,350 kg » et « 12,90 €/kg » (`quantite_au_poids_a_la_francaise`, `unite_d_une_vente_au_poids`) ; la tireuse garde son affichage « 50cl » jusqu'à H-1c (TODO). Le nombre d'articles de la liste des ventes et la marge « articles au coût inconnu » comptent une pesée pour UN article. Le rapport (détail des ventes par produit, offerts par produit) donne la quantité en kg / L avec son unité (`unite`). L'export des lignes garde 3 décimales pour une pesée.
- **Retour de consigne (D13)** : la ligne a une quantité négative, le prix positif du gobelet, un prix d'achat positif (le coût devient négatif par la quantité). Le rapport compte les gobelets rendus par −Σ quantités (TODO retiré). L'écran du panier (prix négatif) ne change pas.
- **Vidage de carte (D12)** : `WalletService.rembourser_en_especes` n'écrit plus les lignes « Refund » ; la vente `VIDAGE_CARTE` reste la seule trace. Ses paramètres `total_tlf_ancien_fedow_centimes`, `total_fed_ancien_fedow_centimes`, `uuid_fed_ancien_fedow` et la clé `lignes_articles` du résultat sont retirés (ils ne servaient qu'à ces lignes). Lecteurs de ces lignes : l'ancien moteur seulement (`laboutik/reports.py`, admin de l'ancienne clôture désenregistré).
/ One line per item; empty method/currency/card/wallet columns; weight and volume in kg / L; deposit return with negative quantity; no more "Refund" lines.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_creer_lignes_articles` (colonnes vides, quantité et prix de la ligne, consigne D13), `_creer_lignes_articles_cascade` (une ligne par article, garde, part en jetons), `_quantite_et_prix_unitaire_de_la_ligne`, `_quantite_reelle_d_une_pesee`, `_prix_de_reference_en_centimes`, `_montant_poids_mesure_en_centimes` (formule du service), refus de la pesée en quantité > 1, nombre d'articles de la liste des ventes, appel du vidage |
| `fedow_core/services.py` | `rembourser_en_especes` : plus de lignes « Refund » |
| `laboutik/affichage_des_ventes.py` | Quantité avec son unité, prix au kg / L lu sur la ligne, branche de la tireuse (TODO H-1c) |
| `laboutik/templates/laboutik/partial/hx_detail_vente.html` | La cellule « Qté » lit `quantite_lisible` |
| `laboutik/printing/formatters.py` | Ticket : quantité avec son unité sous l'article et dans `qty` |
| `comptabilite/rapport.py` | `unite_d_une_vente_au_poids`, unité des produits au poids (détail, offerts), une pesée = un article (marge, total des offerts), retours de consigne |
| `comptabilite/presentation.py` | `quantite_au_poids_a_la_francaise`, cellule de quantité avec unité |
| `Administration/importers/lignearticle_exporter.py` | Quantité d'une pesée à 3 décimales |
| `tests/pytest/test_caisse_une_ligne_par_article.py` | Nouveau : 13 tests (28 cas) |

### Tests existants réécrits ou supprimés / Rewritten or removed tests
| Test | Changement | Raison |
|---|---|---|
| `test_caisse_ecrit_la_vente.py` : `test_vente_especes_trois_jus_une_vente_un_reglement`, `test_paiement_table_especes_vente_liee_a_la_commande`, `test_paiement_table_cb_vente_liee_a_la_commande`, les 7 tests de correction (`test_correction_*`) | Le moyen de la ligne est vide | Q-H2 |
| `test_caisse_ecrit_la_vente.py` : `test_retour_consigne_reprend_prix_et_tva_du_gobelet`, `test_retour_consigne_especes_vente_avoir`, `test_retour_consigne_cout_d_achat_du_gobelet_en_negatif` | Quantité négative, prix positif | D13 |
| `test_caisse_ecrit_la_vente.py` : `test_vente_au_poids_cout_sur_le_poids_reel`, `test_vente_au_poids_par_la_cascade_cout_sur_le_poids_reel`, `test_vente_au_poids_payee_avec_deux_monnaies_cout_sur_le_poids_reel` | 0,350 kg au prix du kilo ; une ligne (part en jetons 420) au lieu de deux parts | D15, une ligne par article |
| `test_caisse_ecrit_la_vente.py` : `test_jetons_et_monnaie_locale_sur_un_article_parts_entieres` → `…_une_ligne`, `test_jetons_vente_ordinaire_tva_zero`, `test_nfc_trois_jus_500_le_550_cb_parts_entieres` → `…_une_ligne`, `test_jetons_benevoles_puis_cb_part_en_jetons_vendue_hors_tva`, `test_complement_legacy_partiel_…`, `test_deuxieme_carte_chaque_reglement_porte_sa_carte`, `test_deuxieme_carte_legacy_…`, `test_archive_lne_part_en_jetons_tva_zero` | Une ligne par article (part en jetons), sans carte | Une ligne par article, Q-H2 |
| `test_caisse_ecrit_la_vente.py::test_archive_lne_part_au_centime_tva_stockee` | Supprimé | Testait une part à quantité fractionnaire (1,428571) : la caisse n'en écrit plus ; l'archive d'une ligne mixte est couverte par `test_archive_lne_part_en_jetons_tva_zero` |
| `test_caisse_ecrit_la_vente.py` : assistant `articles_de_la_vente_par_moyen` | Supprimé | Rangeait les parts par moyen de la ligne |
| `test_part_en_jetons.py::test_caisse_part_lg_porte_sa_part_en_jetons` → `test_caisse_ligne_porte_sa_part_en_jetons` | Une ligne, HT 467 | Une ligne par article |
| `test_caisse_vider_carte_deux_fedow.py` : `test_vider_carte_jetons_cadeau_locaux_…`, `test_vider_carte_lignes_refund_comptent_les_deux_fedow` → `test_vider_carte_deux_fedow_aucune_ligne_refund`, `test_vider_carte_fed_seulement_sur_l_ancien_fedow_ligne_fed_avec_uuid_distant` → `…_reglement_sf_distant` | Aucune ligne « Refund » ; le règlement espèces / SF de la vente porte les montants | D12 |
| `test_card_refund_service.py` (3 tests), `test_pos_vider_carte.py::test_vider_carte_execute_remboursement_complet` | Aucune ligne ; le règlement espèces de la vente | D12 |
| `test_remboursement_especes_trace_comptable.py` : `test_rembourser_les_deux_monnaies_…`, `test_chaque_monnaie_rendue_laisse_sa_transaction`, `test_vider_une_carte_depuis_la_caisse_ecrit_les_deux_lignes` → `…_ecrit_la_vente_du_vidage` | La trace est la vente VIDAGE_CARTE | D12 |
| `test_remboursement_especes_trace_comptable.py` : `test_le_solde_federe_rembourse_est_encaisse_par_le_lieu`, `test_les_lignes_portent_une_trace_comptable_complete`, `test_la_ligne_de_remboursement_porte_l_origine_caisse`, `test_le_remboursement_apparait_dans_les_totaux_du_rapport`, `test_le_remboursement_diminue_le_solde_de_caisse_du_rapport` | Supprimés | Testaient les lignes « Refund » et leur lecture par l'ancien moteur ; couverts par `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_tlf_et_fed_deux_reglements` et `test_rapport_unique.py` (cartes vidées) |
| `test_pos_retour_consigne.py` (6 tests) | Total négatif, quantité négative, prix positif ; moyen, carte, monnaie lus sur le règlement | D13, Q-H2 |
| `test_paiement_complementaire.py` (5 tests) | Les moyens sont lus sur les règlements ; la clôture lit le rapport unique | Q-H2 ; l'ancien moteur lit le moyen de la ligne |
| `test_rapport_unique_comparaison.py` (3 tests) | Seuls les totaux TTC / HT / TVA se comparent encore ; les règlements et le tiroir sont vérifiés sur le rapport unique seul | L'ancien moteur lit le moyen de la ligne, vide (Q-H2) |
| `test_rapport_unique.py` : `test_consigne_dans_ca_retour_en_avoir`, `test_bouton_offrir_quantite_valeur_catalogue_et_cout`, `test_detail_billets_adhesions_produits` | Retour en quantité négative ; clé `unite` | D13, Q-H4 |
| `test_ticket_client_imprime.py` : assistant `_vente_payee_par` (lit `Vente.carte`), `test_les_parts_d_un_article_forment_un_seul_article` → `test_un_article_paye_par_deux_monnaies_est_un_seul_article`, `test_une_part_inferieure_…` → `test_un_article_paye_en_partie_en_jetons_garde_sa_quantite` | La ligne n'a plus de carte ; plus de parts | Q-H2, une ligne par article |
| `test_total_ht_ligne.py::test_le_ht_des_parts_d_un_paiement_en_cascade` → `test_le_ht_d_un_paiement_en_cascade` | Une ligne, HT 933 | Une ligne par article |
| `test_lecteurs_montants_entiers.py::test_facture_adhesion_multi_moyens_35_euros` | Une ligne de 3500 | Une ligne par article |
| `test_menu_ventes.py::test_detail_vente_vrac_poids_et_prix_au_kilo` | Ligne D15, « 0,350 kg » | D15, Q-H4 |
| `test_une_ligne_par_article_lecteurs.py::test_correction_ne_modifie_plus_la_ligne` | Moyen de la ligne vide, règlement espèces | Q-H2 |
| `test_caisse_effets_adhesion.py` (3 tests) | Une ligne et deux règlements (au lieu de deux lignes) prouvent la cascade | Une ligne par article |
| `test_vente_en_points.py` : `test_un_pins_paye_en_points_cree_une_ligne_non_monetaire`, `test_une_adhesion_payee_en_points_ne_debite_pas_d_euros`, `test_une_biere_payee_en_temps`, `test_l_archive_fiscale_garde_la_vente_en_points_sans_tva`, assistant `_ticket_de_la_vente` (4 tests du ticket) | Le moyen NM et la monnaie sont lus sur le règlement | Q-H2 |
| `test_vente_en_points.py` : `test_la_cloture_separe_les_points_de_l_argent`, `test_l_ecriture_comptable_ignore_les_points`, `test_le_pdf_de_cloture_montre_les_ventes_en_points` (et 2 assistants) | Supprimés | Lisaient l'ancien moteur (clôture, FEC, PDF), qui lit le moyen de la ligne ; couverts par le rapport unique (`test_rapport_unique.py::test_points_par_monnaie_hors_ca_et_hors_argent`, écran et ticket du Z de ce fichier) et `test_fec_equilibre.py` |
| `test_hors_argent_offerts.py` : `test_le_gerant_offre_un_panier_payant`, `test_une_ligne_offerte_ne_peut_pas_etre_corrigee_en_especes` | La ligne offerte est trouvée par `source_offert` ; le règlement FREE | Q-H2 |
| `test_hors_argent_offerts.py` : `test_le_total_du_rapport_ignore_les_offerts`, `test_l_ecriture_comptable_reste_equilibree`, `test_une_recharge_cadeau_sort_du_total_des_recharges`, `test_une_recharge_cadeau_ne_gonfle_pas_le_panier_moyen` | Supprimés | Lisaient l'ancien moteur sur des ventes de la route ; couverts par `test_rapport_unique.py` (CA par moyen, cadeau émis, habitus) et `test_fec_equilibre.py` |
| `test_paiement_especes_cb.py` (2 tests), `test_pos_paiement_cheque.py::test_une_vente_payee_par_cheque_est_encaissee_comme_telle`, `test_billetterie_pos.py::test_payer_gift_panier_gratuit_cree_billet_offert` | Le moyen est lu sur le règlement (ou vide pour une vente gratuite) | Q-H2 |
| `test_ventes_remontent_au_ticket_z.py` : 5 tests (espèces, CB, total général, solde du tiroir, vente annulée) | Lus sur le rapport unique au lieu de l'ancien moteur | L'ancien moteur lit le moyen de la ligne |
| `test_ventes_remontent_au_ticket_z.py::test_un_moyen_de_paiement_non_ventile_manque_au_total_general` | Supprimé | Décrivait un défaut de l'ancien moteur (cinq postes lus sur le moyen de la ligne) |

### Chaînes i18n ajoutées / Added i18n strings
1 chaîne : « Une pesée se vend une seule fois par ligne : quantité %(quantite)s refusée pour « %(nom)s ». » (`laboutik/views.py`). Le workflow i18n est à lancer par le mainteneur.

### À savoir : API v2 / Note: API v2
`/api/v2/sales/` lit les lignes : pour une vente de la caisse, il ne publie plus de `payment_method` (la ligne n'en porte plus, Q-H2) ; un retour de consigne sort à prix positif et quantité −1 ; une pesée sort en kg (ou en litres) au prix du kg (du litre). La revue du contrat de l'API (publier les règlements) est prévue après la production (Q-H8). /
`/api/v2/sales/` no longer publishes `payment_method` for register sales; a deposit return has a positive price and quantity −1; a weighing is in kg at the price per kg. Contract review after production (Q-H8).

## H-1b-2-bis — Corrections de la relecture de H-1b-2

**Migration :** Non.

### Resume / Summary
**Quoi / What :** deux pesées restent deux articles au ticket et au détail ; la quantité d'une pesée porte son unité dans l'admin et dans l'export tableur ; un produit vendu au poids et à la pièce donne deux lignes au détail du rapport ; l'article « Jetons cadeau repris au vidage » n'a plus de moyen ; une commande de table refuse un tarif au poids, au volume ou à prix libre ; l'imprimante Sunmi intégrée imprime le détail du poids ; `reset_carte` délie la carte sans supprimer son portefeuille. /
Two weighings stay two items; weighing quantities carry their unit in the admin and spreadsheet; one report row per unit; no method on the "tokens taken back" item; table orders refuse weight / free prices; Sunmi prints the weight detail; reset_carte unlinks without deleting.

**Pourquoi / Why :** relecture Opus de H-1b-2, décisions de l'orchestrateur du 2026-10-05 (I2, I3, Q-H4, M1 à M8). /
Opus review of H-1b-2.

- **I2** : `articles_de_la_vente_pour_l_affichage` met la ligne d'une pesée de la caisse dans la clé de regroupement : deux pesées = deux articles « 0,350 kg x 12,90 €/kg 4,52 ». Les parts d'un ancien tirage de la tireuse se regroupent toujours (TODO H-1c).
- **I3 (Q-H4)** : fiche « Vente » de l'admin (`ArticlesDeLaVenteInline`) et onglet des lignes de l'adhésion (`LigneArticleInline`) : « 0,355 kg » et « 12,90 €/kg » pour une pesée (`_unite_d_une_pesee`, `_quantite_d_une_ligne`, `_prix_unitaire_d_une_ligne`). Export tableur : la cellule de quantité d'une pesée a le format `0.000 "kg"` (ou `0.00 "L"`) ; la cellule du rapport garde son unité (`unite`).
- **Q-H4, deux unités** : détail des ventes et offerts du rapport groupés par produit ET par unité ; une ligne au poids a la clé « uuid--kg » (`_cle_et_unite_d_une_ligne_par_produit`).
- **M1** : commentaires périmés (retour de consigne, « parts » de la cascade, facture d'adhésion).
- **M2** : l'article « Jetons cadeau repris au vidage » n'a plus de `payment_method` ; le plan comptable et le rapport le reconnaissent par son produit.
- **M3** : une seule règle « une pesée = un article » : `quantite_en_nombre_d_articles(prefixe_du_chemin)` (`comptabilite/rapport.py`), lue aussi par la liste des ventes de la caisse (« articles__ »).
- **M6** : `ouvrir_commande` et `ajouter_articles` refusent un tarif au poids, au volume ou à prix libre (400, rien n'est écrit).
- **M7** : `sunmi_inner.py` imprime `weight_detail` sous l'article, sans la quantité sur la ligne (même règle que l'ESC/POS).
- **M8** : `reset_carte` (outil de test, DEBUG) délie le portefeuille éphémère sans le supprimer ni toucher à ses jetons, transactions, ventes et règlements (`Reglement.wallet` est protégé).
/ See above.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/affichage_des_ventes.py` | Clé de regroupement : la ligne d'une pesée |
| `Administration/admin_tenant.py` | Quantité et prix unitaire d'une pesée dans les deux inlines |
| `comptabilite/presentation.py` | La cellule de quantité garde son unité |
| `comptabilite/excel_export.py` | Format de nombre d'une quantité au poids ou au volume |
| `comptabilite/rapport.py` | `quantite_en_nombre_d_articles` (publique), lignes par produit et par unité |
| `laboutik/views.py` | Jetons repris sans moyen, refus des tarifs au poids / prix libre en commande, liste des ventes par la règle du rapport, commentaires |
| `laboutik/printing/sunmi_inner.py` | Détail du poids imprimé |
| `laboutik/utils/test_helpers.py` | `reset_carte` délie sans supprimer |
| `BaseBillet/tasks.py` | Commentaire de la facture d'adhésion |
| `tests/pytest/test_caisse_une_ligne_par_article.py` | Tests 13 à 23 (14 cas), plus `test_ajout_a_une_commande_ouverte_refuse_un_tarif_au_poids` (refus de `ajouter_articles`, au poids et prix libre, 2 cas) |
| `tests/pytest/test_caisse_vider_carte_deux_fedow.py` | Assistant `verifier_les_articles_des_jetons_repris` : la ligne des jetons repris n'a plus de moyen (4 tests qui l'appellent) — M2, Q-H2 |

### Chaînes i18n ajoutées / Added i18n strings
1 chaîne : « Un tarif au poids, au volume ou à prix libre ne passe pas par une commande de table : encaissez-le au comptoir. » (`laboutik/views.py`, deux emplois). Le workflow i18n est à lancer par le mainteneur.

## H-1c — La tireuse et le paiement QR / NFC écrivent une ligne, les écarts deviennent des articles

**Migration :** Non.

### Resume / Summary
**Quoi / What :** plus aucun code n'écrit de « parts ». Un tirage de la tireuse est UNE ligne en litres au prix du litre ; un paiement QR / NFC est UNE ligne au montant demandé. Quand l'argent réellement débité diffère du prix, la différence devient un article « Écart d'encaissement » (reçu en moins ou reçu en plus), comme pour Stripe. `_calculer_qty_partielles` et le paramètre `quantite_pour_cout` sont supprimés. /
No code writes "parts" any more: a pour is ONE line in litres at the price per litre, a QR / NFC payment is ONE line at the requested amount; a different debit becomes a "collection gap" item. `_calculer_qty_partielles` and `quantite_pour_cout` are removed.

**Pourquoi / Why :** fiche H §2 et §2.1 (D15 tireuse, D26) ; fiche C §1 et §1 bis ; décisions Q-H2, Q-H3, Q-H4 (SUIVI §5) ; décisions de l'orchestrateur du 2026-10-05 sur les constats de l'étape 1 (mails, réponses, solde nul, affichage, `quantite_pour_cout`). /
Sheet H §2, §2.1; D15, D26; Q-H2, Q-H3, Q-H4; orchestrator decisions of 2026-10-05.

- **Tireuse (D15)** (`facturer_tirage`) : une ligne, `qty` = les litres servis arrondis à 3 décimales (`calculer_litres_servis`), `amount` = le prix au litre en centimes (`calculer_prix_au_litre_en_centimes`), total par la formule du service, coût d'achat sur ces litres, `part_en_jetons` = la somme des débits LG. Ni moyen, ni monnaie, ni carte, ni portefeuille sur la ligne (Q-H2) ; `weight_quantity` (cl, le stock) et `uuid_transaction` restent. Un règlement par transaction (locale ou ancien Fedow), inchangé.
- **Même centime partout** : `calculer_montant_centimes` (écran de la tireuse, facture) arrondit la quantité d'abord, puis calcule une fois le prix au litre × litres : l'écran, la facture et la ligne donnent le même centime. Changement visible : 333,7 ml à 7,50 €/L valent 251 c (0,334 L × 750 = 250,5), au lieu de 250 c (calcul sur le volume exact).
- **Tireuse, solde insuffisant** : la ligne garde le prix des litres servis (le volume n'est jamais réduit) ; ce qui manque devient l'article « Écart d'encaissement — reçu en moins ». La réponse au Raspberry Pi et l'écran de fin annoncent toujours l'argent débité. L'avertissement « non facturé » reste. Solde nul : toujours aucune vente.
- **QR / NFC** (`_ecrire_la_vente_payee`) : une ligne, `qty` 1, `amount` = le montant demandé, le tarif vendu et l'uuid de la demande (`check_payment`), les métadonnées recopiées, le taux de TVA du produit (ou du lieu) ; ni moyen, ni monnaie, ni portefeuille (Q-H2). Un règlement par transaction de l'ancien Fedow, inchangé. Fedow débite un autre montant : article d'écart « reçu en moins » ou « reçu en plus » au lieu de ramener la vente au montant débité ; le journal d'erreur reste. La ligne de demande (sans vente) ne change pas.
- **Mails du QR / NFC** : les deux mails portent l'argent réellement débité sur les DEUX chemins. Changement assumé pour `valid_payment` (il envoyait le montant demandé) : fiche H §2.1, D26. Les réponses (`amount_paid`, `balance`, solde affiché) gardent le montant débité.
- **Affichage (Q-H4)** : la branche « tirage de l'ancienne forme » (`laboutik/affichage_des_ventes.py`) est retirée : un tirage s'affiche comme une pesée, « 0,50 L » et « 6,00 €/L », un tirage = un article. `unite_d_une_vente_au_poids` rend « L » pour un fût (`Product.FUT`), avec ou sans stock ; le rapport (détail des ventes, offerts) lit le type du produit.
- **Plus de parts** : `_calculer_qty_partielles` (et sa constante `SIX_DECIMALES`) est supprimée de `laboutik/views.py`. `total_catalogue_impose` n'est plus passé par aucun producteur : le paramètre reste pour l'avoir « miroir » d'une ligne historique en parts (Q-R10), docstring au présent. `quantite_pour_cout` est retiré de `calculer_montants_article` et `ajouter_article` (plus aucun appelant).
- **Docstrings** : `ajouter_l_article_d_ecart_d_encaissement` (APPELÉE PAR : Stripe, tireuse, QR), `vente_porte_un_ecart_d_encaissement`, CA par moyen du rapport (un écart n'est plus seulement Stripe). Le TODO de la réconciliation (`section_reconciliation`) est réécrit au présent : un écart de la tireuse ou du QR est payé en cashless, il fausse deux termes de la phrase (la somme tient) — règle à décider.
/ See above.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `calculer_litres_servis`, `calculer_prix_au_litre_en_centimes`, `calculer_montant_centimes` (quantité d'abord), `facturer_tirage` (une ligne, part en jetons, écart « reçu en moins », montant débité rendu) |
| `BaseBillet/views.py` | `_ecrire_la_vente_payee` (une ligne, écart), `process_with_nfc` et `valid_payment` (plus de parts, montant débité pour les mails et les réponses) |
| `laboutik/views.py` | `_calculer_qty_partielles` et `SIX_DECIMALES` supprimées |
| `BaseBillet/services_vente.py` | `quantite_pour_cout` retiré ; docstrings de `total_catalogue_impose`, de l'écart d'encaissement |
| `comptabilite/rapport.py` | `unite_d_une_vente_au_poids` (fût → L), type du produit lu par le détail et les offerts, docstring du CA par moyen, TODO de la réconciliation |
| `laboutik/affichage_des_ventes.py` | Branche « tirage de l'ancienne forme » retirée, unité par le type du produit |
| `tests/pytest/test_tireuse_et_qr_une_ligne.py` | Nouveau : 11 tests (12 cas) |

### Tests existants réécrits ou supprimés / Rewritten or removed tests
| Test | Changement | Raison |
|---|---|---|
| `test_caracterisation_qr.py::test_qr_deux_monnaies_aucun_envoi_laboutik_et_deux_mails` | UNE ligne recréée au lieu de deux ; rien d'autre ne change | Q-H3 (liste fermée A′ §4) |
| `test_c2_legacy_repartition.py` : `test_qty_somme_exacte_sur_un_tiers`, `…_trois_vins_tlf_espece`, `…_sur_un_septieme`, `…_article_au_poids`, `test_qty_une_seule_ligne_prend_toute_la_quantite` (et 2 assistants) | Supprimés | Ne testaient que `_calculer_qty_partielles`, supprimée ; les 4 tests de `_repartir_legacy_sur_articles` / `_decouper_lignes_complement` restent |
| `test_montants_article.py::test_quantite_pour_cout_en_float_refusee` | Supprimé | Paramètre `quantite_pour_cout` retiré |
| `test_montants_article.py::test_cout_achat_sur_la_quantite_reelle` | Ligne D15 (0,350 kg à 12,90 €/kg), coût 280 | `quantite_pour_cout` retiré, même sens |
| `test_rapport_unique.py` (marge brute, fromage) ; `test_avoirs_ecrivent_la_vente.py` : `test_cout_de_l_avoir_partiel_au_prorata_arrondi_demi_haut` (coût imposé 75), `test_cout_de_l_avoir_article_au_poids_reprend_le_poids_servi` (ligne D15, article entier rendu) | Sans `quantite_pour_cout` | Paramètre retiré, même sens |
| `test_tireuse_ecrit_la_vente.py` : `test_tirage_50cl_une_vente_un_reglement`, `test_tirage_jetons_et_monnaie_locale_parts_entieres` → `…_une_ligne`, `test_tireuse_jetons_vente_ordinaire_tva_zero`, `test_tirage_88_centimes_30_plus_58`, `test_total_tirage_arrondi_demi_haut`, `test_tirage_solde_insuffisant_total_egal_debit_reel`, `test_tirage_cout_sur_les_litres_reels`, `test_tirage_egalite_rompue_remonte_et_n_ecrit_rien` | Une ligne en litres au prix du litre, part en jetons, écart « reçu en moins », colonnes vides | D15, D26, Q-H2 |
| `test_tireuse_ancien_fedow.py` : `test_tirage_locales_puis_ancien_fedow_une_vente`, `test_tirage_paye_entierement_par_l_ancien_fedow`, `test_fin_de_service_ancien_fedow_en_echec_facture_les_locales` | Une ligne ; écart −300 quand l'ancien Fedow échoue | D15, D26 |
| `test_controlvanne_billing.py::test_08_pour_end_reparti_sur_deux_monnaies_enregistre_le_montant_entier`, `test_controlvanne_review_fixes.py::test_deux_pour_end_concurrents_facturent_une_seule_fois` | Une ligne ; lignes retrouvées par `vente__carte` | D15, Q-H2 (la ligne n'a plus de carte) |
| `test_part_en_jetons.py::test_tireuse_part_lg_porte_sa_part_en_jetons` | Une ligne, HT 350, TVA 50 | Une ligne par article |
| `test_qrcode_ecrit_la_vente.py` : `test_qr_paye_tlf_et_fed_deux_reglements_exacts`, `test_nfc_ma_une_vente_origine_nfc`, `test_qr_tva_taux_du_lieu` (HT 1042, TVA 208 sur la ligne), `test_qr_debit_partiel_vente_du_montant_debite` (ligne 1250 + écart −50) | Une ligne au montant demandé, colonnes vides, écart | D26, Q-H2 |
| `test_qrcodescanpay_flux_complet.py` : `test_un_paiement_en_monnaie_federee_est_marque_comme_tel`, `…_locale_…`, `test_un_paiement_reparti_sur_deux_monnaies_donne_deux_lignes` → `…_donne_une_ligne_et_deux_reglements`, `test_un_debit_partiel_enregistre_ce_qui_a_ete_paye`, `test_un_paiement_reparti_en_trois_parts_garde_toute_la_quantite` → `…_garde_tout_le_montant`, `test_les_deux_seules_categories_acceptees_produisent_une_vente`, `test_un_paiement_par_carte_enregistre_la_vente`, `test_un_paiement_par_carte_reparti_enregistre_le_montant_entier` ; assistant `_verifier_les_parts_d_un_paiement` → `_verifier_une_ligne_et_ses_reglements` | Moyen lu sur le règlement ; une ligne, un règlement par monnaie ; écart | D26, Q-H2 |
| `test_parcours_vente_fed_et_remise_en_banque.py::test_une_vente_federee_puis_sa_remise_en_banque` | Moyen lu sur le règlement | Q-H2 |
| `test_menu_ventes.py::test_detail_d_un_tirage_paye_avec_deux_moyens_montre_un_article` | Ligne D15, « 0,50 L » au lieu de « 50cl » | D15, Q-H4 (branche de l'ancienne forme retirée) |

### Chaînes i18n ajoutées / Added i18n strings
Aucune.

## H-1d — « Avoir sur un article » et la garde « pas de amount × qty »

**Migration :** Non.

### Resume / Summary
**Quoi / What :** la fiche « Vente » de l'admin a une nouvelle action, « Avoir sur un article ». Elle rend une quantité d'un seul article, par exemple 1 jus sur 3 : une vente AVOIR liée, au même prix unitaire, avec une quantité négative. Le service de l'avoir d'une ligne refuse désormais lui-même les cas impossibles, quel que soit l'appelant. Un test de garde lit le code et échoue s'il trouve un montant recalculé par « prix × quantité ». /
The admin "Sale" page gets a "Credit note on one item" action (e.g. 1 juice of 3: a linked AVOIR sale, same unit price, negative quantity). The line credit note service now refuses impossible cases itself, for every caller. A guard test reads the code and fails on any "price × quantity" recomputation.

**Pourquoi / Why :** fiche H §2 (« Avoir sur un article », reporté de G), §2.1, §5 tests 5c et 10 ; tronc §2 (« Interdit après le chantier »), D13, D27 ; Q-H5 (poids et tireuse : article entier) ; décisions de l'orchestrateur du 2026-10-05 sur les constats de l'étape 1. /
Sheet H §2, §2.1, §5; trunk §2, D13, D27; Q-H5; orchestrator decisions of 2026-10-05.

- **L'action** (`VenteAdmin.avoir_sur_un_article`, `/admin/BaseBillet/vente/<uuid>/avoir_sur_un_article/`) a deux écrans. Le premier liste les articles qui ont encore un reste à rendre. Le second (`?ligne=<pk>`) est celui de l'article choisi : la « Quantité rendue », pré-remplie avec le reste et en lecture seule pour une pesée ou un tirage, puis « Remboursé par », seulement pour de l'argent rendu à la main (D27), pré-rempli par le moyen d'origine. Le POST appelle `ecrire_la_vente_d_avoir_d_une_ligne` (origine ADMIN). Un refus du service devient un message d'erreur, et rien n'est écrit. Un article payé par Stripe donne un règlement négatif au moyen Stripe, sans référence, avec le rappel « Remboursez cette somme depuis votre tableau de bord Stripe ». Le bouton n'apparaît que sur une vente réglée, de nature « Vente », en euros, qui a encore quelque chose à rendre.
- **Refus ajoutés au service** (`ecrire_la_vente_d_avoir_d_une_ligne`, donc aussi pour le bouton « Avoir » de « Entries », les annulations de l'admin et l'annulation d'adhésion) :
  - toute vente qui porte un écart d'encaissement : aucun avoir sur ses articles (Q-H13) ;
  - une recharge (ligne hors chiffre d'affaires). Une recharge en points garde le refus « points », plus précis ;
  - une partie d'une pesée ou d'un tirage (Q-H5) : la quantité doit valoir le reste (`article_vendu_au_poids_ou_a_la_tireuse`, nouvelle fonction) ;
  - une partie non entière d'un article à la pièce. Tout ce qui reste passe toujours, même une quantité non entière : une pesée, ou une « part » de l'historique.
- **Garde** (`test_garde_aucun_amount_fois_qty.py`) : lit le Python, les gabarits et le JavaScript de production, hors migrations et tests. La liste d'exceptions est fermée : les fichiers retirés en H-2 (`laboutik/reports.py`, `comptabilite/services.py`), plus UN extrait de `laboutik/views.py`, le HT de la branche « vente absente » de `_creer_lignes_articles`, retiré en H-3. Les cas connus qu'elle ne voit pas sont écrits dans sa docstring.
- **Occurrences corrigées** :
  - `BaseBillet/services_panier.py` (`calcul_total_centimes`) : le prix unitaire est arrondi au centime (demi-haut), puis le total passe par `calculer_montants_article`. Avant, le total était tronqué par `int(...)`. Aucun changement pour un prix à deux décimales ;
  - `crowds/views.py` : le bloc commenté mort du financement global (`F("pricesold__prix") * F("qty")`) est supprimé.
/ See above.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | Action `avoir_sur_un_article` (fiche « Vente »), `AvoirSurUnArticleForm`, `_raison_du_refus_de_l_avoir_sur_un_article`, `_quantite_restante_affichee` ; `_lignes_de_la_vente_avec_un_reste_a_rendre` garde le reste sur chaque ligne (`quantite_restante`) ; bouton montré seulement quand il a un sens |
| `Administration/templates/admin/vente/avoir_sur_un_article.html` | Nouveau : liste des articles, écran de l'article |
| `BaseBillet/services_vente.py` | `article_vendu_au_poids_ou_a_la_tireuse` (nouvelle) ; refus de `ecrire_la_vente_d_avoir_d_une_ligne` (écart, recharge, partie d'une pesée, partie non entière) ; docstrings |
| `BaseBillet/services_panier.py` | `calcul_total_centimes` par la formule du service |
| `crowds/views.py` | Bloc commenté mort du financement global supprimé, et la clé commentée `summary_funding_to_allocate` qui y renvoyait |
| `tests/pytest/test_admin_avoir_sur_un_article.py` | Nouveau : 14 tests (17 cas) |
| `tests/pytest/test_garde_aucun_amount_fois_qty.py` | Nouveau : la garde n° 10 |

### Tests existants réécrits ou supprimés / Rewritten or removed tests
| Test | Changement | Raison |
|---|---|---|
| `test_rapport_unique.py::TestRapportDesVentes::test_rapport_serialisable_en_json` | Le billet avec un écart de 3 reste (annexe « Écarts d'encaissement ») ; l'avoir admin porte sur un second billet Stripe sans écart. Aucune assertion changée | Q-H13 : une vente qui porte un écart d'encaissement ne reçoit aucun avoir |

### Chaînes i18n ajoutées / Added i18n strings
Python (`admin_tenant.py`) : « Avoir sur un article », « Avoir sur un article de la vente n° %(numero)s », « Quantité rendue », « Au plus la quantité qui reste à rendre. », « Seule une vente de nature « Vente » reçoit un avoir sur un article. », « Cette vente n'est pas en euros (points ou temps) : l'avoir n'est pas possible. », « Cet article n'est pas dans cette vente, ou il est déjà rendu en totalité. ».
Gabarit : « Choisissez l'article à rembourser. », « Articles qui ont encore un reste à rendre », « Article », « Prix unitaire », « Reste à rendre », « Action », « Rembourser %(article)s », « Rembourser », « Retour à la vente », « prix unitaire », « reste à rendre », « Article vendu au poids ou à la tireuse : seul l'article entier se rembourse. ».
Les refus du service sont des textes français non traduits, comme ceux des autres refus du service. Le workflow i18n est à lancer par le mainteneur.

## H-1c-bis — Corrections de la relecture de H-1c : volume autorisé, lecteurs des écarts

**Migration :** Non.

### Resume / Summary
**Quoi / What :** la tireuse facture le volume autorisé au badge (le débordement n'est pas facturé, le stock baisse du volume servi) ; la réconciliation ne compte que les écarts en argent ; un écart n'est pas un article dans la liste des ventes ; l'admin affiche un tirage en litres ; un tirage de moins de 5 ml reste une vente au volume ; la page du payeur QR affiche l'argent débité ; l'avoir d'une ligne QR s'écrit (métadonnées en dictionnaire). /
The tap bills the volume authorised at the badge (overflow not billed, stock down by the served volume); reconciliation counts only money gaps; a gap is not an item in the sales list; the admin shows a pour in litres; a pour under 5 ml stays a volume sale; the QR payer page shows the money debited; a QR line's credit note is written.

**Pourquoi / Why :** relecture Opus de H-1c ; décision du mainteneur Q-H13 (remplace Q-H11) ; Q-H12 abandonnée. /
Opus review of H-1c; maintainer decision Q-H13.

- **Volume autorisé (Q-H13)** (`facturer_tirage`) : la ligne porte `min(volume servi, volume autorisé)`. Le volume autorisé est `session.allowed_ml_session`, calculé au badge par `calculer_volume_autorise_ml`, arrondi VERS LE BAS au millilitre : le montant ne dépasse jamais le solde lu au badge (200 c à 6 €/L : 333 ml, 199,8 → 200 c). Le débordement n'est pas facturé (une ligne d'information au journal). `weight_quantity` et le décrément du stock gardent le volume réellement servi. L'article d'écart « reçu en moins » reste le filet : il n'apparaît que si l'argent débité ne couvre pas la ligne (ancien Fedow en échec, solde baissé depuis le badge). L'avertissement dit « non encaissé, écart reçu en moins ». La réponse au Pi et l'écran annoncent toujours l'argent débité. `calculer_litres_servis` devient `calculer_litres_du_volume`.
- **Avoir d'une vente avec écart** : refusé par le service (H-1d). « Avoir total » de l'admin le respecte : `_raison_du_refus_de_l_avoir_total` refuse avant l'écran (GET et POST), et le service refuse aussi (`test_admin_vente.py::test_avoir_total_refuse_une_vente_avec_un_ecart_d_encaissement`, inchangé).
- **Métadonnées QR** : la ligne payée reçoit ses métadonnées en DICTIONNAIRE (aller-retour par `DjangoJSONEncoder`), plus jamais en texte JSON ; `ajouter_l_article_d_avoir` relit aussi l'ancien texte JSON (lignes historiques, reprise R) ; `valid_payment` lit les deux formes (un rejeu sur une ligne payée répond « déjà traité », pas une page 500). La ligne de demande (sans vente) garde son texte JSON.
- **Réconciliation (I1)** : « écarts d'encaissement » et « ventes payées en argent » ne comptent que les écarts EN ARGENT (ventes sans règlement cashless) ; l'annexe garde le total des écarts, avec la ligne « dont payés en cashless » (`dont_payes_en_cashless_en_centimes`). Une vente qui mêle argent, cashless et écart n'existe pas. TODO retiré.
- **Liste des ventes (I2)** : `quantite_en_nombre_d_articles` compte 0 pour un article d'écart : un tirage avec écart affiche « 1 article ».
- **Admin (I3)** : `_unite_d_une_pesee` lit aussi les lignes de la tireuse, et passe le type du produit : un fût sans stock s'affiche « 0,50 L », « 6,00 €/L ».
- **Tirage de moins de 5 ml (M3)** : `quantite_en_nombre_d_articles` et `_ligne_au_poids_ou_au_volume` reconnaissent aussi une ligne de fût (`Product.FUT`) : 4 ml (poids 0 cl) restent « 0,004 L », un article.
- **Page du payeur QR (M1)** : la confirmation de `valid_payment` affiche l'argent débité.
- **Journaux (M2)** : tireuse « non encaissé, écart reçu en moins » ; QR « argent debite » au lieu de « parts debitees ».
- **CA par moyen (M4)** : inchangé (l'invariant tient) ; un écart d'un tirage payé en plusieurs monnaies est imputé à « plusieurs moyens ».
- **djc (M5-M7)** : renvois de session retirés des docstrings de tests ; « ne porte plus la carte » → « ne porte pas la carte : elle est sur la vente et ses règlements » ; docstring de `facturer_tirage` (ligne anglaise trop longue).
/ See above.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `calculer_volume_autorise_ml` (arrondi vers le bas au ml), `calculer_litres_du_volume`, `facturer_tirage` (volume facturé = min, stock au volume servi, écart en filet, journaux, docstring) |
| `BaseBillet/views.py` | Métadonnées de la ligne QR en dictionnaire ; `valid_payment` lit les deux formes ; page du payeur à l'argent débité ; journaux |
| `BaseBillet/services_vente.py` | `ajouter_l_article_d_avoir` relit les métadonnées en texte JSON |
| `comptabilite/rapport.py` | Réconciliation sur les écarts en argent, `_articles_d_ecart_payes_en_cashless`, annexe « dont payés en cashless », écart = 0 article, fût = vente au volume |
| `comptabilite/presentation.py` | Ligne « dont payés en cashless » de l'annexe (0 pour une clôture plus ancienne) |
| `Administration/admin_tenant.py` | `_unite_d_une_pesee` : tireuse comprise, type du produit |
| `laboutik/views.py` | Commentaire du nombre d'articles de la liste des ventes |
| `tests/pytest/test_tireuse_et_qr_une_ligne.py` | Tests 12, 12 bis, 13 (2 cas), 14 à 18 |

### Tests existants réécrits / Rewritten tests
| Test | Avant → après | Raison |
|---|---|---|
| `test_tireuse_et_qr_une_ligne.py::test_tireuse_solde_insuffisant_ecart_recu_en_moins` → `test_tireuse_solde_insuffisant_facture_le_volume_autorise` | ligne 300 + écart −100 → ligne 0,333 L = 200, aucun écart, aucun avertissement | Q-H13 |
| `test_tireuse_et_qr_une_ligne.py` : assistant `servir_un_tirage_avec_un_ecart` (tests 14, 15) | écart par débordement → écart par l'échec de l'ancien Fedow (filet) | Q-H13 |
| `test_tireuse_et_qr_une_ligne.py` : assistant `ventes_d_avoir_de` | Supprimé | Plus d'appelant |
| `test_tireuse_ecrit_la_vente.py::test_tirage_solde_insuffisant_total_egal_debit_reel` → `test_tirage_solde_insuffisant_facture_le_volume_autorise` | ligne 400 + écart −100 → ligne 0,375 L = 300, aucun écart | Q-H13 |
| `test_vente_en_points.py::TestVenteEnPoints::test_la_tireuse_facture_le_tarif_en_euros` | la `RfidSession` créée à la main reçoit `allowed_ml_session` = 1000 ml (aucune assertion changée) | Q-H13 : le volume autorisé, posé au badge, plafonne le volume facturé |
| Docstrings et commentaires : `test_caracterisation_qr.py` (commentaires seulement), `test_qrcodescanpay_flux_complet.py`, `test_tireuse_ecrit_la_vente.py`, `test_tireuse_ancien_fedow.py`, `test_controlvanne_billing.py`, `test_controlvanne_review_fixes.py`, `test_ticket_client_imprime.py` | Renvois de session retirés, règle au présent | djc |

### Chaînes i18n ajoutées / Added i18n strings
1 chaîne : « dont payés en cashless » (`comptabilite/presentation.py`). Le workflow i18n est à lancer par le mainteneur.

---

## Comment tester (à la main) / Manual test

### Test 1 — correction d'une vente en espèces
1. Caisse : vendre 3 jus en espèces.
2. Ventes → historique → déplier la vente : un bouton « Corriger : Espèces ».
3. Corriger en CB avec la raison « erreur de touche ».
4. Attendu : le détail montre « Corrigée par la vente n° X », et un seul bouton, « Corriger : Carte bancaire ». Dans l'admin, la fiche de la vente X montre la raison « erreur de touche ». Dans « Entries », la ligne n'a pas changé.

### Test 2 — vente payée par carte NFC + espèces
1. Payer 10,50 € avec une carte qui porte 5 € ; le reste en espèces.
2. Attendu : un seul bouton « Corriger : Espèces », et le formulaire affiche 5,50 €.

### Test 3 — double envoi
1. Ouvrir la même vente dans deux onglets, et dans chacun le formulaire « Corriger : Espèces ».
2. Valider dans le premier onglet (espèces → CB), puis dans le second.
3. Attendu : une seule vente CORRECTION. Le second onglet affiche « Il ne reste rien à corriger pour le moyen « Espèces »… » dans la zone du formulaire.

### Test 4 — « Remboursé par »
1. Admin → Ventes → la vente du test 1 → « Avoir total ».
2. Attendu : « Carte bancaire » est pré-rempli.
3. Avec la vente du test 2 : le champ est vide et obligatoire (deux moyens).

### Test 5 — admin
1. « Entries » → fiche d'une ligne : ni moyen, ni monnaie, ni carte, ni portefeuille.
2. Export : pas de colonne « Carte cashless » ni « Wallet from ».
3. Menu « Ventes & comptabilité » : plus d'« Ancien rapport caisse ».

### Test 6 — vidage et retour de consigne (H-1a-bis)
1. Caisse : vider une carte qui porte de la monnaie locale (espèces rendues).
2. Ventes → déplier la vente « Carte vidée » : aucun bouton « Corriger ».
3. Caisse : un retour de consigne rendu en espèces. Déplier la vente « Avoir » : un bouton « Corriger : Espèces », et la correction en CB passe.

### Test 7 — bière payée en jetons + monnaie locale (H-1b-1)
Avant : régénérer la base de dev (les ventes scellées avant H-1b-1 ne se vérifient plus).
1. Caisse : une carte avec 3 € de jetons cadeau et 2 € de monnaie locale ; vendre une bière à 5 € (TVA 20 %) par la carte.
2. Admin → « Entries » : deux lignes. La ligne LG a la TVA 20 %, une part payée en jetons de 3,00 €, un HT de 3,00 € et une TVA de 0. La ligne LE a un HT de 1,67 € et une TVA de 0,33 €.
3. Rapport temps réel : CA par taux « 0 % » 3,00 € et « 20 % » 2,00 € (HT 1,67, TVA 0,33).
4. Réimprimer le ticket : TVA 0 % 3,00 / 0,00 et TVA 20 % 1,67 / 0,33.
5. Admin → la vente → « Avoir total », remboursé en espèces : règlements jetons −3,00 € et espèces −2,00 €.

### Test 8 — une ligne par article (H-1b-2)
Avant : régénérer la base de dev (les lignes de l'historique gardent l'ancienne forme).
1. Caisse : 3 jus à 3,50 € avec une carte qui porte 5 € ; le reste en CB. Admin → « Entries » : UNE ligne, quantité 3, prix 3,50 €, ni moyen ni carte. La vente a deux règlements (monnaie locale 5,00 €, CB 5,50 €).
2. Caisse : 350 g de comté à 12,90 €/kg en espèces. Ventes → déplier la vente : « 0,350 kg », « 12,90 €/kg », 4,52 €. Réimprimer le ticket : « 0,350 kg x 12,90 €/kg ». La liste des ventes compte 1 article.
3. Caisse : un retour de gobelet en espèces. « Entries » : quantité −1, prix 1,00 €. Rapport temps réel → annexe : 1 retour de consigne.
4. Caisse : vider une carte. « Entries » : aucune ligne « Remboursement carte » ; la vente « Carte vidée » porte les règlements.

### Test 9 — tireuse et QR en une ligne (H-1c)
1. Tireuse : badger une carte avec 10 € de monnaie locale, servir 50 cl à 6 €/L. Ventes → déplier la vente : « 0,50 L », « 6,00 €/L », 3,00 €. Admin → « Entries » : UNE ligne, quantité 0,500, prix 6,00 €, ni moyen ni carte.
2. Tireuse : une carte avec 2 € seulement, servir 50 cl à 6 €/L (le Pi déborde). L'écran de fin annonce 2,00 € ; la vente a UNE ligne de 0,333 L à 6,00 €/L = 2,00 €, aucun écart, un règlement de 2,00 € ; le stock du fût baisse de 50 cl (H-1c-bis, Q-H13).
3. QR code : générer un QR de 12,50 €, le payer avec un portefeuille qui a de la monnaie locale et de la fédérée. Admin → la vente : UNE ligne de 12,50 €, deux règlements ; l'écran de l'encaisseur passe à « payé ».

### Test 10 — avoir sur un article (H-1d)
1. Caisse : vendre 3 jus à 3,50 € en espèces. Admin → Ventes → la vente → « Avoir sur un article ».
2. Attendu : la liste montre le jus, avec un reste de 3. Cliquer « Rembourser » : « Remboursé par » est pré-rempli « Espèces », et la quantité vaut 3. Mettre 1, puis valider.
3. Attendu : la fiche de la vente AVOIR, total −3,50 €, un article de quantité −1 à 3,50 €, un règlement espèces −3,50 €. Rouvrir l'action sur la vente d'origine : il reste 2 jus.
4. Mettre 1,5 : refus « … doit être un nombre entier d'articles ». Mettre 3 : refus (il n'en reste que 2).
5. Caisse : 350 g de comté. « Avoir sur un article » : la quantité 0,350 est en lecture seule ; valider rend 4,52 €.
6. Une vente en ligne payée par Stripe (2 billets) : pas de champ « Remboursé par » ; rendre 1 billet affiche le rappel Stripe.
7. Une vente avec un « Écart d'encaissement » : le POST est refusé, avec le message « Cette vente a un écart d'encaissement… ».

### Vérifs DB
`docker exec lespass_django poetry run python /DjangoFiles/manage.py shell` : `Vente.objects.filter(nature="CORRECTION").values("numero", "raison")` ; `LigneArticle.objects.exclude(part_en_jetons=0).values("vat", "total_ttc", "part_en_jetons", "total_ht", "total_tva")` ; `LigneArticle.objects.filter(sale_origin="LB", vente__isnull=False).exclude(payment_method=None).count()` (0 pour les ventes écrites après H-1b-2, hors l'article « Jetons cadeau repris au vidage »).
