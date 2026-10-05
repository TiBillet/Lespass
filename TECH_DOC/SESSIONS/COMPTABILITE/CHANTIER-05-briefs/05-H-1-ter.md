# Brief — 05-H-1-ter : corrections de la relecture Fable finale de H-1

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive. Lecture seule autorisée
(`git status`, `git diff`, `git log`). Pas de `ruff format` ni de `ruff check --fix` sur un
fichier existant. `poetry`, `pytest`, `manage.py` **toujours** dans le conteneur
`lespass_django`. Jamais deux pytest en parallèle. Pas de `makemessages` /
`compilemessages`. Pas de `runserver`. Tests par `make test ARGS="tests/pytest/<fichier>.py"`,
après 3 réponses 200 du serveur. Outils Edit / Write seulement. **Ne modifie jamais le
code de production pendant l'étape « tests », même pour une mutation.** Tu ne joues
aucune mutation : tu les listes, c'est l'orchestrateur qui les joue. Une série de
modifications liées se termine vite, suivie de `manage.py check`.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skill `djc` chargé (`unfold` pour l'admin), `GUIDELINES.md` lu : FALC, noms verbeux,
commentaires FR puis EN au présent adressés au prochain lecteur (jamais « chantier 05,
session … », jamais « ne … plus » qui raconte un avant), `_()` en français.

## Contexte
H-1 est commitée (`ecbf8146`). La relecture Fable de tout H-1 a donné 0 bloquant,
3 importants, 9 mineurs : aucun montant faux, aucune décision contredite. Décisions de
l'orchestrateur ci-dessous (aucune question métier ouverte).

## Ce que tu corriges
1. **I-1 — Poids forgé sur un tarif à la pièce** (`laboutik/views.py` ~l.6053,
   `_extraire_articles_du_panier`) : un POST qui envoie un poids (`weight-<produit>`)
   pour un tarif qui n'est pas `poids_mesure` est **refusé**, comme la pesée en
   quantité > 1 (même forme de refus, même code HTTP que ce refus existant). Sans ça,
   `weight_quantity` est posé et la ligne passe pour une pesée (liste « 1 article »,
   « kg » au ticket et à l'admin, avoir partiel refusé).
2. **I-2 — Garde n° 10** (`tests/pytest/test_garde_aucun_amount_fois_qty.py`) : ajouter
   le motif `prix_centimes … * … quantite` (et l'inverse). Les 7 occurrences de
   `laboutik/views.py` (~l.2993, 6072, 9824, 9885, 10185, 11461, 12218) vont dans une
   exception nommée et fermée « débit du panier de la caisse : entiers × entiers, la
   ligne passe par `calculer_montants_article` et l'égalité de la vente refuse toute
   divergence », chaque extrait listé (pas le fichier entier). Docstring de la garde
   mise à jour. Aucun code de production ne change pour ce point.
3. **I-3 — Écran « Avoir sur un article »** (`Administration/admin_tenant.py`) :
   - `_raison_du_refus_de_l_avoir_sur_un_article` (~l.2706) refuse aussi une vente qui
     porte un écart d'encaissement (`vente_porte_un_ecart_d_encaissement`, même message
     que le service) : le bouton est caché, le GET redirige avec le message ;
   - la liste des articles proposés n'offre pas les lignes hors chiffre d'affaires
     (recharge, article d'écart) : filtre dans l'écran « Avoir sur un article »
     seulement, sans changer ce que lit « Avoir total » (vérifie qui appelle
     `_lignes_de_la_vente_avec_un_reste_a_rendre` avant d'y toucher ; si « Avoir total »
     l'appelle, filtre à part dans l'action).
4. **M-1 — Un seul arrondi du prix au litre** (`controlvanne/billing.py` ~l.317) :
   `calculer_volume_autorise_ml` lit le prix par `calculer_prix_au_litre_en_centimes`
   (demi-haut), comme la ligne.
5. **M-2 — Métadonnées en texte vide** (`BaseBillet/services_vente.py` ~l.856) : un texte
   vide ou blanc donne un dictionnaire vide, sans `json.loads`.
6. **M-3 — Enquête seulement, aucun code** : `ApiBillet/serializers.py` ~l.1051 envoie à
   l'ancien LaBoutik le moyen du PREMIER règlement d'argent de la vente. Trouve si une
   ligne de vente qui a **deux règlements d'argent ou plus** (caisse : monnaie locale +
   CB ; QR : deux monnaies) peut atteindre `send_sale_to_laboutik` /
   `send_refund_to_laboutik` (triggers A et B de `BaseBillet/triggers.py`, appelants
   dans `admin_tenant.py`, `launch_payment.py`, les signaux). Réponds avec les chemins
   exacts et un oui / non argumenté. Ne corrige rien.
7. **M-8 — djc** : `BaseBillet/services_vente.py` ~l.503 « (retiré en fiche H) » → « retiré
   en H-2 » ; commentaires « n'est plus » au présent : `Administration/admin/dashboard.py`
   ~l.832, `Administration/admin/laboutik.py` ~l.1268-1274, `laboutik/views.py` ~l.3854,
   ~l.3911 (TODO en double : un seul suffit, l'autre renvoie au premier), ~l.13644.
   Garde les TODO H-2 utiles.

8. **Clé d'empreinte du lieu toujours en base (décision du mainteneur, 2026-10-05)** —
   piège 9.86 et risque en production : `LaboutikConfiguration` (django-solo, mise en
   cache dans memcached, `SOLO_CACHE = 'default'`, 5 min) n'est créée qu'au premier
   `get_solo()`. Si cette première création a lieu dans une transaction qui échoue, le
   cache garde un objet (avec ou sans clé) que la base n'a pas : ventes chaînées avec une
   clé jamais écrite (empreinte cassée à l'expiration du cache), ou `DatabaseError` sur
   `save(update_fields=['hmac_key'])`. Correction complète :
   - **migration de données** `laboutik/migrations/0016_…` (RunPython, laboutik est une
     app de lieu : elle tourne dans chaque schéma existant ET à la création d'un lieu) :
     crée la ligne du singleton si elle manque, et sa clé si elle est vide (même
     génération et même chiffrement que `get_or_create_hmac_key`) ; inverse = rien ;
   - **la clé se lit en base, jamais dans le cache** : `get_hmac_key` et
     `get_or_create_hmac_key` relisent `hmac_key` en base (pas l'attribut de l'objet
     venu du cache) ; si la ligne ou la clé manque, `get_or_create_hmac_key` l'écrit en
     base sous verrou (`select_for_update` / `update_or_create`, jamais
     `save(update_fields=…)` sur un objet qui peut ne pas exister), puis vide le cache du
     singleton (`clear_cache`). Les appelants ne changent pas ;
   - `tests/PIEGES.md` 9.86 : mettre à jour (cause réelle : cache + rollback ; correction
     faite dans le modèle).

## Ce que tu ne fais pas
M-6 (préchargement dans `LigneArticleInline`) et M-7 (`plan_comptable.py`, virement
reçu) : rien, ils sont notés pour H-2. Le filtre `afficher_poids` : rien (noté pour H-2).

## Périmètre
`laboutik/views.py`, `Administration/admin_tenant.py`, `Administration/admin/dashboard.py`,
`Administration/admin/laboutik.py`, `controlvanne/billing.py`,
`BaseBillet/services_vente.py`, `tests/pytest/test_garde_aucun_amount_fois_qty.py`,
`tests/pytest/test_caisse_une_ligne_par_article.py`, `tests/pytest/test_admin_avoir_sur_un_article.py`,
`tests/pytest/test_tireuse_et_qr_une_ligne.py`, `tests/pytest/test_part_en_jetons.py`,
`tests/pytest/test_une_ligne_par_article_lecteurs.py`,
`laboutik/models.py`, `laboutik/migrations/0016_*.py` (neuf), `tests/pytest/test_cle_d_empreinte_du_lieu.py` (neuf), `tests/PIEGES.md` (9.86),
`CHANGELOG/2026-10-04-montants-entiers-H-1.md` (section H-1-ter). Lecture seule pour
l'enquête M-3. Tout autre fichier : STOP.

## Tests (à écrire en premier)
| # | Fichier | Test | Attendu |
|---|---|---|---|
| 1 | `test_caisse_une_ligne_par_article.py` | `test_poids_forge_sur_un_tarif_a_la_piece_refuse` | POST `repid-<jus>=3` + `weight-<jus>=350` sur un tarif à la pièce → refusé, aucune vente, aucune ligne |
| 2 | `test_garde_aucun_amount_fois_qty.py` | (la garde) | une occurrence `article["prix_centimes"] * article["quantite"]` hors des 7 extraits listés la fait échouer (vert après l'exception : le dire, avec la mutation) |
| 3 | `test_admin_avoir_sur_un_article.py` | `test_bouton_cache_et_ecran_refuse_sur_une_vente_avec_ecart` | vente en ligne 2 billets + écart : l'action n'est pas dans les actions de la fiche ; GET → redirection + message de l'écart |
| 4 | `test_admin_avoir_sur_un_article.py` | `test_liste_des_articles_sans_recharge_ni_ecart` | vente avec un billet et un article d'écart « reçu en plus » : la liste ne propose que le billet |
| 5 | `test_tireuse_et_qr_une_ligne.py` | `test_volume_autorise_meme_arrondi_que_le_prix_de_la_ligne` | prix 3,505 €/L : `calculer_volume_autorise_ml` utilise 351 c/L (demi-haut), pas 350 |
| 6 | `test_tireuse_et_qr_une_ligne.py` | `test_avoir_d_une_ligne_aux_metadonnees_texte_vide` | ligne payée avec `metadata=""` → avoir écrit, métadonnées `{"original_lignearticle_uuid": …}` |
| 7 | `test_part_en_jetons.py` | `test_jetons_sur_un_produit_a_0_pourcent_une_ligne_au_z_et_au_ticket` (M-4) | bière à 0 % payée 300 jetons + 200 LE : une seule ligne « 0.00 » TTC 500, HT 500, TVA 0 au CA par taux du rapport et au ticket |
| 8 | `test_admin_avoir_sur_un_article.py` | `test_avoir_sur_un_article_d_une_ligne_mixte_jetons_et_especes` (M-5) | ligne 300 jetons + 200 espèces, POST de tout le reste par l'écran : « Remboursé par » demandé ; règlements LG −300 (monnaie et carte du LG d'origine) + espèces −200 |
| 10 | `test_cle_d_empreinte_du_lieu.py` | `test_cle_lue_en_base_quand_le_cache_garde_un_objet_sans_ligne` | ligne du singleton supprimée en base, objet sans clé laissé dans le cache : `get_or_create_hmac_key()` ne lève rien, la clé est écrite en base et relue identique |
| 11 | `test_cle_d_empreinte_du_lieu.py` | `test_cle_de_la_base_gagne_sur_celle_du_cache` | cache qui porte une clé K1, base qui porte K2 : `get_hmac_key()` et `get_or_create_hmac_key()` rendent K2 |
| 12 | `test_cle_d_empreinte_du_lieu.py` | `test_migration_cree_la_configuration_et_sa_cle` | la fonction de la migration 0016, appelée sur un lieu sans ligne (puis sur une ligne sans clé), crée la ligne et une clé ; rappelée, elle ne change pas une clé existante |
| 9 | `test_une_ligne_par_article_lecteurs.py` | (M-9) | `test_ancien_moyen_inconnu_refuse_sans_cible` et `test_post_force_sur_une_vente_offerte_ou_en_points_refuse` : + aucune vente CORRECTION ni `CorrectionPaiement` écrite |

Vus rouges attendus : 1, 3, 4, 5, 6, 10, 11, 12 (12 : import de la migration absente) (et 2 si la garde est écrite avant l'exception).
7, 8, 9 : verts par construction (tests manquants, comportement déjà juste) : le dire,
avec la mutation qui les ferait tomber.

## Étapes
1. Tests ; **ne lance pas pytest** (une suite complète tourne) ; STOP. L'orchestrateur
   prouve le rouge.
2. (après feu vert) Le code ; tests de la session ; voisins (`test_caisse_ecrit_la_vente.py`,
   `test_admin_vente.py`, `test_tireuse_*.py`, `test_qrcode*.py`,
   `test_controlvanne_billing.py`, `test_avoirs_ecrivent_la_vente.py`) ; `manage.py check` ;
   caractérisation verte sans modification.
3. Mutations LISTÉES (fichier:ligne exacts, 5 à 8).
4. CHANGELOG section H-1-ter ; réponse à l'enquête M-3.

## Rapport final attendu
Fichiers ; sorties ; mutations ; réponse M-3 ; constats ; auto-contrôle djc ; message de
commit (sans Co-Authored-By).
