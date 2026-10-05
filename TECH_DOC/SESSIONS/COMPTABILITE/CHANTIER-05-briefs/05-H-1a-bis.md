# Brief — 05-H-1a-bis : corrections de la relecture Opus de H-1a

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive (`checkout --`,
`restore`, `stash`, `reset`, `clean`). Lecture seule autorisée (`git status`,
`git diff`). Tu t'arrêtes à la fin de ce brief et tu rapportes : le mainteneur commite.
Pas de `ruff format` ni de `ruff check --fix` sur un fichier existant. `poetry`,
`pytest`, `manage.py` **toujours** dans le conteneur `lespass_django`. Jamais deux
pytest en parallèle. Pas de `makemessages` / `compilemessages`. Pas de `runserver`.
Tests par `make test ARGS="tests/pytest/<fichier>.py"`. Outil Edit / Write seulement.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skill `djc` chargé et `GUIDELINES.md` lu avant toute ligne : FALC, noms verbeux,
commentaires FR puis EN au présent adressés au prochain lecteur (pas de récit de
session, pas de renvoi « jusqu'à la fiche … » hors d'un TODO), `_()` en français.

## Ce que tu corriges (décisions de l'orchestrateur, 2026-10-05)
1. **Vidage de carte corrigeable (I-1)** — `raison_du_refus_de_correction`
   (`laboutik/views.py` ~l.4866) : nouvelle règle, seules les ventes de nature **VENTE**
   et **AVOIR** se corrigent (l'avoir de caisse payé en espèces, ex. retour de consigne,
   reste corrigeable : décision G-2a). Une vente `VIDAGE_CARTE` (ou `CORRECTION`) est
   refusée, comme avant H-1a. Message en français par `_()`.
2. **Refus « hors argent » prouvés par la règle du net (I-2)** : un POST forgé
   `ancien_moyen=CA` sur une vente entièrement offerte, et sur une vente en points, est
   refusé (400, aucune vente CORRECTION). Test seulement si le code tient déjà ; sinon
   le corriger.
3. **`ancien_moyen` validé (M-1)** — `laboutik/serializers.py`
   `CorrectionPaiementSerializer` : `ChoiceField` sur `PaymentMethod.choices` ; et
   `_refus_de_correction` ne pose `HX-Retarget` que si le code est dans
   `MOYENS_CORRIGEABLES_A_LA_CAISSE` (sinon pas de zone : message sans cible).
4. **Message (M-2)** : « Il ne reste rien à corriger pour le moyen « %(moyen)s » sur
   cette vente : elle vient peut-être d'être corrigée. Rouvrez la vente pour voir ses
   règlements. » (adapter les tests qui le lisent).
5. **Helpers à leur place** : `moyen_d_argent_unique_de_la_vente`,
   `moyen_d_origine_de_la_ligne` et `MOYENS_IGNORES_POUR_LE_REMBOURSE_PAR` vont de
   `Administration/admin_tenant.py` vers `BaseBillet/services_vente.py` (avec
   `MOYENS_DU_CHAMP_REMBOURSE_PAR` s'il y est déjà, sinon importé). `BaseBillet/views.py`
   les importe en tête depuis `services_vente` (plus d'import de l'admin). Vérifier
   qu'aucun cycle d'import n'apparaît (`manage.py check`). Attention : `services_vente`
   ne doit pas importer `laboutik.affichage_des_ventes` si cela crée un cycle ; si c'est
   le cas, STOP et rapporter.
6. **Export : test sur les champs (mutation survivante)** — `test_fiche_d_une_ligne_sans_champs_de_paiement`
   vérifie que les **champs exportés** (`attribute` des champs de
   `LigneArticleExportResource().get_export_fields()`, et noms de colonnes) ne
   contiennent ni `carte`, ni `wallet`, ni `asset`, ni le moyen de la ligne, quel que
   soit le titre de la colonne. Mutation à tuer : `'carte'` ajouté à `Meta.fields`
   (colonne au titre « carte »).
7. **djc et docs** :
   - `VenteAdmin.get_fieldsets` (~l.3007) : docstring avec LOCALISATION ; copie
     explicite du dict (`options_du_bloc_avec_la_raison = dict(options_du_bloc)` puis
     clé `fields`), sans `{**…}` ;
   - route ~l.13706 : le renvoi « jusqu'a la fiche H-2 » devient
     `TODO : retirer CorrectionPaiement avec la fiche H-2` ;
   - `Administration/importers/lignearticle_exporter.py` ~l.37 : commentaire au présent
     (« ne disent pas comment la ligne est payée »), sans « plus » ;
   - `laboutik/static/css/ventes.css` ~l.363 : commentaire avec le nouvel identifiant
     `correction-zone-<uuid de la vente>-<code du moyen>` ;
   - CHANGELOG section H-1a : retirer le récit (« rapport de l'ouvrier », « rejoué par
     l'orchestrateur ») ; test manuel « deux envois » par deux onglets sur le même
     formulaire.

Hors session (accepté) : N+1 de l'écran d'annulation admin (peu de lignes), clôture lue
3 fois par le détail, erreurs du serializer sans `HX-Retarget` (comportement ancien).

## Périmètre
`laboutik/views.py`, `laboutik/serializers.py`, `laboutik/static/css/ventes.css`,
`BaseBillet/services_vente.py`, `BaseBillet/views.py`, `Administration/admin_tenant.py`,
`Administration/importers/lignearticle_exporter.py`,
`tests/pytest/test_une_ligne_par_article_lecteurs.py`, les tests existants qui lisent
le message de refus (les lister), `CHANGELOG/2026-10-04-montants-entiers-H-1.md`.
Tout autre fichier : STOP et rapporter.

## Tests (dans `tests/pytest/test_une_ligne_par_article_lecteurs.py`, à écrire en premier)
| # | Test | Attendu |
|---|---|---|
| 14 | `test_vidage_de_carte_jamais_corrigeable` | vidage qui rend de l'argent en espèces ET reprend des jetons cadeau (route réelle de la caisse) : aucun bouton « Corriger » au détail ; POST forgé espèces → CB : 400, aucune vente CORRECTION |
| 15 | `test_retour_de_consigne_en_especes_reste_corrigeable` | AVOIR de caisse (retour de consigne) rendu en espèces : un bouton « Corriger » ; la correction passe |
| 16 | `test_post_force_sur_une_vente_offerte_ou_en_points_refuse` | `ancien_moyen=CA` forgé sur une vente entièrement offerte, puis sur une vente en points : 400, aucune CORRECTION |
| 17 | `test_ancien_moyen_inconnu_refuse_sans_cible` | `ancien_moyen=ZZ` → 400 du serializer ; `ancien_moyen=LE` → refus sans `HX-Retarget` |
| 11 (renforcé) | `test_fiche_d_une_ligne_sans_champs_de_paiement` | champs exportés sans `carte` / `wallet` / `asset` / moyen de la ligne, quel que soit le titre |

Vus rouges attendus : 14, 17, et 11 contre la mutation « `'carte'` dans `Meta.fields` »
(le dire). 15 et 16 peuvent être verts (garde-fous de non-régression) : donner la
mutation qui les fait tomber.

## Étapes
1. Écrire les tests ; les lancer ; coller la sortie ; STOP (l'orchestrateur prouve le
   rouge).
2. (après feu vert) Le code ; tests de la session et voisins (`test_menu_ventes.py`,
   `test_caisse_ecrit_la_vente.py`, `test_corrections_fond_sortie.py`,
   `test_hors_argent_offerts.py`, `test_vente_en_points.py`, `test_lecteurs_montants_entiers.py`,
   `test_avoirs_ecrivent_la_vente.py`, `test_admin_vente.py`, `test_menu_rapports.py`),
   `manage.py check`, caractérisation verte sans modification.
3. Mutations (fichier:ligne exacts) : nature VIDAGE acceptée ; `ancien_moyen` en
   `CharField` ; `HX-Retarget` posé pour tout code ; helpers lus depuis l'admin (import
   remis) ; `'carte'` dans `Meta.fields` de l'export.
4. CHANGELOG section H-1a-bis.

## Rapport final attendu
Fichiers ; sorties (rouge, vert) ; mutations ; constats ; auto-contrôle djc ; message de
commit (sans Co-Authored-By).
