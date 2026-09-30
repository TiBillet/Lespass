# Caisse : effets d'adhésion communs, puis montants entiers / Register: shared membership effects, then integer amounts

**Date :** 2026-09-29
**Migration :** Oui (B-1) — `BaseBillet/migrations/0231_product_consigne_remboursee.py`, puis
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary

Fiche B du chantier 05 « montants entiers » (`TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md`,
écarts : `CHANTIER-05-SUIVI.md` §4). Une section par session.
/ Sheet B of the "integer amounts" work. One section per session.

### Session B-0 — effets d'adhésion communs / Shared membership effects

**Quoi / What :** une adhésion payée a les mêmes effets en ligne et en caisse, par le
même code. Deux fonctions dans `BaseBillet/triggers.py` :
`appliquer_les_effets_d_une_adhesion_payee` (écritures en base : échéance, rattachement
de l'adhérent au lieu, nom et prénom s'il n'en a pas) et
`demander_les_taches_d_une_adhesion_payee` (facture par mail, newsletter, récompense en
monnaie en `on_commit`). `trigger_A` appelle les deux à la suite, puis envoie la vente à
l'ancien LaBoutik : l'ordre des tâches en ligne ne change pas. La caisse appelle la
première dans la transaction du paiement, et la seconde en `transaction.on_commit` : la
tâche de facture relit l'adhésion en base, qui doit être validée. La caisse n'envoie
toujours rien à l'ancien LaBoutik. En cascade (plusieurs lignes pour une adhésion), les
effets s'appliquent une fois, avec la ligne qui porte l'adhésion. Une adhésion sans ligne
qui la porte : aucun effet, erreur journalisée. /
A paid membership has the same effects online and at the register, through the same
code: database writes inside the payment transaction, then Celery tasks (at the register,
after the commit). Online task order unchanged. Still nothing sent to legacy LaBoutik
from the register.

**Pourquoi / Why :** une adhésion vendue en caisse ne recevait ni facture par mail ni
récompense en monnaie, et l'adhérent identifié par sa carte n'était pas rattaché au lieu
(décision du mainteneur : « doivent fonctionner »). /
A membership sold at the register got neither invoice mail nor currency reward
(maintainer's decision).

**Changement de comportement voulu / Intended behaviour change :**
- caisse : facture par mail, récompense en monnaie, newsletter si acceptée, rattachement
  au lieu, nom et prénom complétés depuis l'adhésion ;
- caisse, adhésion payée en points (création) : un seul `webhook_membership` au lieu de
  deux (l'échéance est posée une fois, après la mise à jour du moyen de paiement) ;
- inchangé : deux `webhook_membership` sortants au renouvellement, en caisse comme en
  ligne (bug n°2 de `TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md`, corrigé après
  le chantier pour tous les canaux).

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/triggers.py` | nouvelles `appliquer_les_effets_d_une_adhesion_payee(adhesion)` et `demander_les_taches_d_une_adhesion_payee(adhesion, ligne_article)` (la ligne sert à la récompense) ; `trigger_A` les appelle, garde `update_membership_state_after_stripe_paiement` (avant) et l'envoi à l'ancien LaBoutik (après) |
| `laboutik/views.py` | `_creer_ou_renouveler_adhesion` ne pose plus l'échéance ; nouvelle `_appliquer_les_effets_d_une_adhesion_vendue_en_caisse` (garde « sans ligne », effets en base, tâches en `on_commit`), appelée aux 4 endroits où la caisse crée une adhésion (espèces / CB / chèque, NFC, complément, seconde carte) |
| `tests/pytest/test_caisse_effets_adhesion.py` | nouveau : 7 tests (espèces, NFC en cascade, complément en espèces, seconde carte, renouvellement, facture exécutée lue dans `mailoutbox`, aucune tâche avant la validation en base) |
| `tests/pytest/test_caracterisation_caisse.py` | `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` → `test_vente_caisse_adhesion_facture_et_recompense_sans_envoi_laboutik` (fiche A′ §4) : webhook, facture, récompense, dans cet ordre ; aucun envoi à l'ancien LaBoutik |

Chaînes i18n ajoutées : aucune (le seul message ajouté est un journal d'erreur, non
traduit). / No new translatable string.

#### Tests vus échouer / Tests seen failing

Rouge (étape 1, prouvé par l'orchestrateur, avant le code) :
```
test_adhesion_caisse_especes_demande_facture_et_recompense
E   AssertionError: assert [] == [('2ac34854-...',)]
test_adhesion_caisse_nfc_demande_facture_et_recompense_une_fois
E   AssertionError: assert [] == [('add9ff7f-...',)]
test_adhesion_caisse_renouvelee_echeance_posee_une_fois
E   assert [(3870,), (3870,)] == [(3870,)]
test_facture_de_l_adhesion_caisse_part_au_bon_destinataire
E   assert 0 == 1
test_adhesion_caisse_taches_demandees_apres_la_validation
E   AssertionError: assert 'send_membership_invoice_to_email' in ['webhook_membership']
test_vente_caisse_adhesion_facture_et_recompense_sans_envoi_laboutik
E   {'taches': ['webhook_membership']} != {'taches': ['webhook_membership', 'send_membership_invoice_to_email', 'refill_from_lespass_to_user_wallet_from_price_solded']}
6 failed, 3 passed
```
Le test de renouvellement a été adapté ensuite (décision du mainteneur : deux webhooks
figés, bug n°2 du TODO) : il vérifie aussi une facture, une récompense et l'échéance
prolongée, qui manquaient avant le code.

Vert : B-0 + caisse `9 passed` ; caractérisation (22, seul le test A′ prévu a changé),
fiche A, caisse et adhésions : `470 passed` ; suite complète (`tests/pytest/`,
`booking/tests/`) : `2172 passed`, 0 échec ; `manage.py check` : aucun problème ;
`makemigrations --check --dry-run` : « No changes detected ».

Compléments (demande de l'orchestrateur) : deux tests pour les chemins sans test,
`test_adhesion_caisse_complement_demande_facture_et_recompense` (complément en
espèces, `laboutik/views.py` appel l.9662) et
`test_adhesion_caisse_seconde_carte_demande_facture_et_recompense` (seconde carte,
appel l.10251) : ils passent par la vraie route (`payer` en NFC, écran de complément,
puis `payer_complementaire`), code déjà en place, force à prouver par mutation. Le
paramètre inutilisé `ligne_article` est retiré de
`appliquer_les_effets_d_une_adhesion_payee`. Relance : B-0 + caractérisation + points +
fusion wallet + webhook `139 passed` ; `manage.py check` : aucun problème.

#### Mutations

Jouées par l'orchestrateur.

| Session | Mutation | Test qui tombe |
|---|---|---|
| B-0 | `laboutik/views.py` : appel des effets retiré (espèces / CB / chèque) | `test_adhesion_caisse_especes_…`, renouvellement, facture, « après la validation », test A′ caisse |
| B-0 | `BaseBillet/triggers.py` `trigger_A` : les deux appels retirés | 4 tests A′ en ligne / admin (`test_adhesion_en_ligne_payee`, panier mixte, renouvellement, admin) |
| B-0 | `laboutik/views.py` : tâches de caisse demandées **avant** le COMMIT (sans `on_commit`) | `test_adhesion_caisse_taches_demandees_apres_la_validation`, test A′ caisse |
| B-0 | appel des effets retiré (NFC) | `test_adhesion_caisse_nfc_demande_facture_et_recompense_une_fois` |
| B-0 | appel des effets retiré (complément) | `test_adhesion_caisse_complement_demande_facture_et_recompense` |
| B-0 | appel des effets retiré (seconde carte) | `test_adhesion_caisse_seconde_carte_demande_facture_et_recompense` |
| B-0 | `triggers.py` : `client_achat` non posé | NFC, complément, seconde carte (adhérente identifiée par sa carte) |
| B-0 | `triggers.py` : nom et prénom non complétés | `test_adhesion_caisse_especes_…` |
| B-0 | `triggers.py` : `set_deadline()` retiré | renouvellement, test A′ caisse, 3 tests A′ en ligne |
| B-1 | retour de consigne au prix de son propre produit (panier, serveur) | tests 7, 8, retour sans consigne |
| B-1 | tuile du retour au prix de son propre produit | test 7 (`data-price`) |
| B-1 | retour avec la TVA de son propre produit | tests 7, 8 |
| B-1 | boucle HMAC qui recalcule le HT par `calculer_total_ht` | test 17 (+ 3 tests d'offert) |
| B-1 | `quantite_pour_cout` non passé (poids) | test 17b |
| B-1 | `idempotency_key` de la vente non posée | 10 tests (vente introuvable) |
| B-1 | TVA de recharge : défaut du produit | test 4 |
| B-1 | recharges écrites hors de la vente | tests 4, 5, 6, recharge cadeau par `payer` |
| B-1 | règlement FREE d'OFFRIR retiré | test 3 |
| B-1 | retour de consigne en espèces écrit en vente `VENTE` | test 8 |
| B-1 | retour de consigne par carte écrit en vente `VENTE` | test 7 |
| B-1 | règlement carte ≠ montant de la transaction de recrédit | test 7 |
| B-1 | refus du mélange recharge cadeau + autres articles retiré (`payer`) | test 6b (espèces, NFC) |
| B-1 | refus du mélange retiré (complément) | `test_complement_refuse_le_melange_recharge_cadeau` |
| B-1 | recharge cadeau comptée dans la somme encaissée | `test_recharge_cadeau_seule_par_la_route_payer_…` |
| B-1 | opérateur : utilisateur connecté ignoré | test 1 (`vente.operateur`) |
| B-1 | refus du retour sans consigne reliée retiré | `test_retour_consigne_sans_consigne_reliee_refuse` |

Empreintes `sha256` des fichiers mutés identiques avant et après. Non jouées en B-1 (doubles sécurités de la transition, documentées) : l'offert déclenché par `payment_method == FREE` (le service le fait aussi jusqu'à H) ; la recherche de la vente dans le rejeu (la recherche par les lignes le fait aussi jusqu'à H). Non jouée en B-0 : la garde
« adhésion sans ligne » (inatteignable par la vraie route, défensive, journalisée).

### Session B-1 — la caisse à un moyen écrit la Vente / One-method register writes the sale

**Quoi / What :** chaque encaissement à UN moyen de paiement (espèces, CB, chèque,
OFFRIR, recharge cadeau seule, retour de consigne en espèces ou par carte) écrit, dans la
même transaction que ses lignes, une `Vente` encaissée (numérotée, empreinte chaînée), ses
règlements (copiés de l'argent encaissé ou de la transaction de recrédit) et les montants
entiers de chaque article, par le service de vente (`ajouter_article`). Les lignes gardent
leurs champs d'aujourd'hui (`amount`, `qty`, moyen, statut, carte, `uuid_transaction`…).
La boucle d'empreinte des lignes reprend le HT du service (demi vers le haut) au lieu de le
recalculer par `calculer_total_ht` (arrondi au pair) et écrit par `.update()`. Les
recharges sont des articles de la même vente, hors chiffre d'affaires. La clé
d'idempotence du paiement devient `Vente.idempotency_key` ; un rejeu regarde les lignes OU
la vente. /
Each one-method collection writes, in the same transaction as its lines, a settled
`Vente`, its payments and the whole-cent amounts of each item, through the sale service.
Lines keep today's fields. The line HMAC loop keeps the service's HT.

**Pourquoi / Why :** chantier 05 « montants entiers », fiche B §1-§3, §6 (tronc §2, D8,
D10, D11, D14, §5). / Work 05, sheet B.

**Changements de comportement voulus / Intended behaviour changes :**
- **TVA d'une ligne de recharge en euros : 20 % → 0** (D10). Une recharge est une dette
  envers le porteur de la carte, pas une vente taxée. (La recharge cadeau était déjà à 0 :
  elle est offerte.) Seul changement de valeur pour les anciens lecteurs, sur ce chemin.
- **HT d'une ligne de caisse : arrondi demi vers le haut** (111 c à 20 % : 93, plus 92).
- **Consigne reliée (D11, précisée par le mainteneur)** : un « Retour de consigne » (`CR`)
  est relié au produit consigne qu'il rembourse (`Product.consigne_remboursee`). Le prix du
  gobelet est utilisé PARTOUT : tuile de la caisse, total, espèces rendues, recrédit de la
  carte ; l'article du retour prend aussi le taux de TVA du gobelet. Le prix et le taux
  propres du produit de retour ne sont plus lus. La ligne garde le tarif vendu du produit de
  retour, `amount` négatif et `qty` positive (jusqu'à la fiche H). La vente est un `AVOIR`
  sans vente liée, avec un règlement négatif (espèces, ou monnaie locale = la transaction de
  recrédit).
- **Retour de consigne sans consigne reliée : refusé** (400, rien n'est écrit) avec le
  message « Le retour « … » ne dit pas quelle consigne il rembourse. Prévenez le
  gestionnaire : il faut le relier au produit consigne dans l'administration. » (même refus
  si la consigne n'a pas de tarif en euros). Le refus tombe à la lecture du panier
  (`_extraire_articles_du_panier`) : paiement, écran des moyens de paiement, complément.
- **Recharge cadeau mêlée à d'autres articles : refusée** (décision du mainteneur,
  2026-09-29), par le serveur, avant toute écriture et tout débit de carte, quel que soit le
  moyen : « La recharge cadeau se fait à part : retirez les autres articles. » Aujourd'hui la
  caisse faisait payer le cadeau au client (le total additionne tous les articles). La
  recharge cadeau seule ne change pas (crédit sans paiement à l'identification de la carte) ;
  elle écrit maintenant sa vente (article offert en totalité, règlement FREE), sans clé
  d'idempotence (ce parcours n'en a pas).
- Admin des produits de caisse : champ « Rembourse la consigne » (visible seulement pour la
  méthode « Retour de consigne » ; liste limitée aux articles de méthode « Vente »).

**Transition (TODO B-2, B-3)** : `_creer_lignes_articles` et `_executer_recharges`
gardent l'écriture d'avant quand aucune vente n'est donnée : paiement NFC en cascade,
complément, seconde carte (fiche B-2) et commande de table (fiche B-3). Ces chemins
n'écrivent pas encore de vente, et leurs lignes de recharge cadeau gardent l'écriture
d'avant. *(Fait dans les sessions suivantes : B-2a, B-2b, B-2c et B-3a, plus bas. La
branche sans vente de `_creer_lignes_articles` ne sert plus qu'aux appels directs de
tests existants ; elle est retirée en fiche H.)*

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Product.consigne_remboursee` (FK nullable vers `Product`, `SET_NULL`, `related_name="retours_de_consigne"`) |
| `BaseBillet/migrations/0231_product_consigne_remboursee.py` | nouvelle migration (ajout du champ) |
| `Administration/admin/products.py` | `POSProductAdmin` : champ dans « General », `conditional_fields` (visible pour `CR`) ; `POSProductForm` : queryset limité aux produits de méthode « Vente » (il valide la valeur postée) |
| `laboutik/views.py` | nouvelles `_prix_de_la_consigne_remboursee_en_centimes`, `_panier_melange_recharge_cadeau_et_autres_articles`, `_somme_encaissee_du_panier_en_centimes`, `_operateur_de_la_caisse`, `_diviseur_de_la_quantite_saisie` (règle g/cl partagée avec `_montant_poids_mesure_en_centimes`), `_taux_tva_de_la_ligne_de_caisse`, `_ouvrir_la_vente_de_caisse`, `_regler_et_encaisser_la_vente_de_caisse` ; `_creer_lignes_articles(vente=…)` passe par `ajouter_article` (types convertis, coût d'achat sur le poids réel, OFFRIR offert en totalité) et sa boucle HMAC garde le HT du service (`.update()`) ; `_executer_recharges(vente=…, uuid_transaction=…)` ; CB / chèque / OFFRIR, espèces, retour de consigne par carte et recharge cadeau seule (`identifier_client`) écrivent leur vente ; tuile d'un retour au prix du gobelet ; refus du mélange recharge cadeau + autres articles (`_executer_paiement`, `_executer_paiement_complementaire`) ; rejeu : lignes OU vente de la clé |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | nouveau : 13 tests, 14 cas (fiche §6 : 1-8, 6b en espèces et en NFC, 17, 17b, 22, refus du retour sans consigne reliée) |
| `tests/pytest/test_pos_retour_consigne.py` | réécrit (voir plus bas) |

Chaînes i18n ajoutées (msgid en français, workflow i18n à lancer par le mainteneur) :
« Rembourse la consigne », « Le produit consigne (par exemple le gobelet) que ce retour
rembourse. La caisse rend son prix, avec son taux de TVA. », « Le retour « %(nom)s » ne dit
pas quelle consigne il rembourse. Prévenez le gestionnaire : il faut le relier au produit
consigne dans l'administration. », « La consigne « %(nom)s » n'a pas de tarif en euros : le
retour ne peut pas être remboursé. Prévenez le gestionnaire. », « La recharge cadeau se fait
à part : retirez les autres articles. »

#### Tests existants réécrits / Rewritten existing tests

| Fichier | Raison |
|---|---|
| `tests/pytest/test_pos_retour_consigne.py` | un retour sans consigne reliée est refusé (D11) : `setUp` crée le gobelet consigne vendu 1,00 € et le relie au retour (`consigne_remboursee`) ; le second retour (deux monnaies) est relié à une assiette consignée ; le test « TVA sur le retour » pose le taux sur le **gobelet** (le retour prend le taux du gobelet) ; les totaux postés suivent le prix du gobelet. Les montants attendus ne changent pas (gobelet 1,00 € = ancien prix du retour). 24 tests. |

Pas de réécriture pour la TVA des recharges (fiche §7) : aucun test existant ne l'assertait
par une vraie route de caisse ; la suite complète reste verte.

Panier vide (tous les articles écartés à la lecture) : comportement gardé, succès sans
rien écrire. Aucune vente n'est ouverte (le service refuse une vente sans article) ; vu par
`test_paiement_especes_cb.py` (2 tests) et `test_vente_en_points.py` (1 test), inchangés.

#### Tests vus échouer / Tests seen failing (B-1)

Rouge (avant le code ; prouvé par l'orchestrateur pour les 12 premiers) :
```
test_caisse_ecrit_la_vente.py:306: AssertionError: Attendu : une vente pour la clé …, trouvé : 0.   (1, 2, 3, 5, 17b, 22)
test_caisse_ecrit_la_vente.py:535: AssertionError: assert Decimal('20.00') == Decimal('0')   (4)
test_caisse_ecrit_la_vente.py:657: AssertionError: La ligne de la recharge cadeau n'appartient à aucune vente.   (6)
test_caisse_ecrit_la_vente.py:758: AssertionError: assert '-150' == '-100'   (7 : tuile au prix du retour)
test_caisse_ecrit_la_vente.py:839: assert 1.5 == 1   (8 : 1,50 € à rendre)
test_caisse_ecrit_la_vente.py:884: assert 200 == 400   (retour sans consigne reliée)
test_caisse_ecrit_la_vente.py:927: assert 92 == 93   (17)
test_caisse_ecrit_la_vente.py:733: assert 200 == 400   (6b[espece], 6b[nfc])
```

Vert : `test_caisse_ecrit_la_vente.py` 14 passed ; `test_pos_retour_consigne.py` réécrit
24 passed ; suite complète (`tests/pytest/`, `booking/tests/`) : **2188 passed**, 0 échec
(caractérisation 22 inchangés, fiche A, B-0 compris) ; `manage.py check` : aucun
problème ; `makemigrations --check --dry-run` : « No changes detected » ;
`migrate_schemas --executor=multiprocessing` appliqué (tous les schémas, `test_*` compris,
ont la colonne).

### Session B-1b — consigne : coût du gobelet, tuile masquée, validation admin, démo / Deposit: cup cost, hidden tile, admin validation, demo

**Migration :** Non (le champ `consigne_remboursee` existe depuis B-1).

**Quoi / What :** trois sécurités pour un « Retour de consigne » mal configuré
(« ceinture et bretelles », décision du mainteneur) et le coût d'achat du retour :
- **coût d'achat du retour = coût du gobelet relié, en négatif** (D21 : un gobelet rendu
  retire son coût de la marge). Le prix d'achat propre du produit de retour n'est jamais
  lu. Gobelet à prix d'achat 0 → coût inconnu (vide) ;
- **tuile masquée** : la caisse n'affiche pas la tuile d'un retour dont elle ne sait pas
  calculer le prix (pas de consigne reliée, ou gobelet sans tarif en euros vendable en
  caisse, par exemple tarif dépublié après coup) ;
- **validation de l'admin** : le formulaire d'un produit de caisse refuse d'enregistrer un
  « Retour de consigne » sans consigne reliée, ou relié à un gobelet sans tarif en euros
  vendable en caisse (erreur sur le champ « Rembourse la consigne ») ;
- le refus à la vente (B-1) reste, en troisième sécurité ;
- **démo** : « Retour Consigne » est relié à « Consigne », à la création et pour un retour
  déjà présent sans lien (commande rejouable). /
A deposit return's purchase cost is its cup's, negative. A return whose price cannot be
computed has no tile; the admin refuses to save it; the sale refusal stays. The demo
return is linked to its cup.

**Pourquoi / Why :** décisions du mainteneur du 2026-09-29 (`CHANTIER-05-SUIVI.md` §4
et §5, fiche B §3). / Maintainer's decisions.

**Changements de comportement voulus / Intended behaviour changes :**
- `cout_achat` d'un article de retour de consigne : −(prix d'achat du gobelet × quantité)
  au lieu de +(prix d'achat du produit de retour × quantité) ;
- tuile absente (au lieu d'une tuile à son propre prix, refusée au clic) ;
- enregistrement refusé dans l'admin (au lieu d'un produit accepté puis refusé en caisse).

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | nouvelle `_tarifs_en_euros_vendables_a_la_caisse(produit)` (la règle « tarif en euros vendable », lue par la caisse et par l'admin) ; `_prix_de_la_consigne_remboursee_en_centimes` l'utilise ; `_construire_donnees_articles` : pas de tuile quand le prix du retour ne se calcule pas ; `_creer_lignes_articles` : prix d'achat du gobelet relié, en négatif, pour un retour |
| `Administration/admin/products.py` | `POSProductForm.clean` : deux erreurs possibles sur `consigne_remboursee` (champ vide ; gobelet sans tarif en euros vendable), import local de la règle de la caisse |
| `laboutik/management/commands/create_test_pos_data.py` | « Retour Consigne » relié à « Consigne » (création et produit existant sans lien) |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 5 tests : coût du gobelet en négatif (espèces, 2 gobelets : −60 ; carte : −30), gobelet sans prix d'achat (coût vide), tuile masquée sans consigne reliée, tuile masquée pour un gobelet au tarif dépublié |
| `tests/pytest/test_admin_retour_de_consigne.py` | nouveau : 5 tests (formulaire de l'admin : refus sans lien, refus gobelet sans tarif, deux témoins acceptés ; vrai POST de la page d'ajout avec `admin@admin.com` : rien de créé, seule erreur sur le champ) |
| `tests/pytest/test_pos_models.py` | `test_create_test_pos_data_command` : une assertion (le retour de la démo rembourse « Consigne ») |

Chaînes i18n ajoutées (msgid en français, workflow i18n à lancer par le mainteneur) :
« Choisissez la consigne que ce retour rembourse (par exemple le gobelet). Sans elle, la
caisse ne sait pas quel prix rendre. », « La consigne « %(nom)s » n'a pas de tarif en
euros publié pour la caisse. Ajoutez-lui un tarif en euros, ou choisissez une autre
consigne : sinon la caisse ne sait pas quel prix rendre. »

#### Tests vus échouer / Tests seen failing (B-1b)

Rouge (avant le code ; rejoué par l'orchestrateur : 9 failed, 26 passed) :
```
test_admin_retour_de_consigne.py:192: assert not True   (refus sans lien : formulaire valide)
test_admin_retour_de_consigne.py:212: assert not True   (refus gobelet sans tarif : formulaire valide)
test_admin_retour_de_consigne.py:326: AssertionError: Le retour de consigne sans consigne reliée a été enregistré.
test_caisse_ecrit_la_vente.py:1127: assert 198 == -60   (coût : prix d'achat du retour, positif)
test_caisse_ecrit_la_vente.py:1163: assert 99 == -30    (idem, par carte)
test_caisse_ecrit_la_vente.py:1193: assert 99 is None   (gobelet à 0 : le 99 du retour était lu)
test_caisse_ecrit_la_vente.py:1252: assert not True     (tuile d'un retour non relié affichée)
test_caisse_ecrit_la_vente.py:1278: assert not True     (tuile d'un gobelet au tarif dépublié affichée)
test_pos_models.py:554: AssertionError: 'Retour Consigne' doit rembourser le produit 'Consigne'
```
Verts avant le code (témoins) : `test_admin_accepte_un_retour_relie_a_un_gobelet_avec_tarif_en_euros`,
`test_admin_vente_ordinaire_sans_consigne_reliee_acceptee`.

Vert : les trois fichiers `35 passed` ; `test_caisse_effets_adhesion.py`,
`test_pos_retour_consigne.py`, `test_hors_argent_offerts.py`, `test_vente_en_points.py`,
`test_synchronisation_tva_categorie.py` et les 5 fichiers de caractérisation :
`180 passed` (caractérisation seule : 22 passed, sans modification) ; `manage.py check` :
aucun problème ; `makemigrations --check --dry-run` : « No changes detected ».

#### Mutations (B-1b)

Jouées à la main par l'orchestrateur, une par une : **9/9 tuées** (chacune fait tomber exactement les tests annoncés), `sha256sum` identiques après retour. La mutation de la démo a été jouée après avoir délié « Retour Consigne » dans `lespass` ; le test l'a relié de nouveau au retour arrière.
/ Played by hand: 9/9 killed, identical checksums.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| coût du retour positif (`laboutik/views.py:5742`) | `-int(produit_du_gobelet_rendu.prix_achat)` → `int(…)` | coût espèces (60 ≠ −60), coût carte (30 ≠ −30) |
| coût lu sur le produit de retour (`laboutik/views.py:5740-5742`) | bloc `if produit.methode_caisse == Product.RETOUR_CONSIGNE:` retiré | coût espèces (198), coût carte (99), gobelet sans prix d'achat (99 ≠ None) |
| tuile d'un retour non relié ré-affichée (`laboutik/views.py:722-723`) | `except ValueError: continue` → `except ValueError: prix_de_la_consigne_remboursee_en_centimes = None` | les deux tests de tuile masquée |
| tuile d'un gobelet sans tarif ré-affichée (`laboutik/views.py:723`) | `continue` → `if product.consigne_remboursee_id is None: continue` | `test_tuile_retour_consigne_gobelet_sans_tarif_en_euros_masquee` seul |
| validation (a) retirée (`Administration/admin/products.py:1735-1742`) | `if gobelet_rembourse is None:` + `add_error` → `if gobelet_rembourse is None: pass` | `test_admin_refuse_un_retour_de_consigne_sans_consigne_reliee`, `test_admin_post_d_un_retour_sans_consigne_reliee_ne_cree_rien` |
| validation (b) retirée (`Administration/admin/products.py:1752`) | `if not gobelet_a_un_tarif_en_euros_vendable:` → `if False:` | `test_admin_refuse_un_retour_relie_a_un_gobelet_sans_tarif_en_euros` |
| validateur qui refuse tout retour (`Administration/admin/products.py:1735`) | `if gobelet_rembourse is None:` → `if True:` | `test_admin_accepte_un_retour_relie_a_un_gobelet_avec_tarif_en_euros` |
| validateur qui refuse toute méthode (`Administration/admin/products.py:1730-1732`) | `methode_est_un_retour_de_consigne = (…)` → `= True` | `test_admin_vente_ordinaire_sans_consigne_reliee_acceptee` |
| démo sans lien (`laboutik/management/commands/create_test_pos_data.py:741` et `:752-754`) | `"consigne_remboursee": produit_consigne,` et le bloc `if … consigne_remboursee_id is None:` retirés | `test_create_test_pos_data_command` — **à condition** de délier d'abord « Retour Consigne » dans le schéma `lespass` (la commande écrit dans la base de dev, sans rollback : le lien posé par un run précédent reste et la mutation survivrait) |

### Session B-2a — le paiement NFC seul écrit la Vente / NFC-only payment writes the sale

**Migration :** Non.

**Quoi / What :** le paiement par la carte NFC du client, quand la carte paie tout (cascade
des monnaies du lieu, jetons cadeau, points, monnaie du réseau qui couvre le reste), écrit
dans la même transaction que ses lignes une `Vente` encaissée, ses règlements et les
montants entiers de chaque part :
- les lignes sont écrites comme avant (même `amount` = prix unitaire, même `qty`
  partielle, mêmes champs historiques, même ordre des parts, adhésion sur la même part),
  par `ajouter_article` ; chaque part reçoit `total_catalogue_impose` = son argent réel ;
- une part payée en jetons cadeau (LG) est offerte (`part_offerte` = son argent, source
  `JETONS`, net 0) et réglée par un règlement « jetons » (LG) : les jetons ne sont pas de
  l'argent (D8) ;
- les règlements sont copiés des débits réels : un par transaction `fedow_core` (montant et
  uuid de la transaction renvoyée, dans `fedow_transaction_uuid`) ; points : un règlement
  `NM` par transaction (une par article), vente tenue dans la monnaie de points
  (`Vente.unite` = son uuid), TVA 0 ; monnaie du réseau (Fedow distant) : un règlement par
  transaction distante, son uuid dans `reference_externe` (`_debiter_legacy` rend
  désormais l'uuid) ;
- coût d'achat d'une vente au poids : sur le poids réel, pour la fraction de l'article que
  paie chaque part ;
- les recharges cadeau du paiement NFC sont des articles de la même vente, avec
  l'identifiant du paiement sur leurs lignes ;
- `encaisser_vente` en dernier ; une égalité rompue (`EgaliteDeVenteRompue`) est attrapée
  au même endroit que le solde insuffisant : rien n'est écrit, la caisse montre son écran
  d'erreur (409, jamais une erreur 500), et si la monnaie du réseau a déjà été débitée, un
  INCIDENT est journalisé (montant, carte, uuid de chaque transaction du réseau) pour une
  régularisation à la main. Le journal d'incident du solde insuffisant porte aussi ces
  uuid ;
- la boucle d'empreinte (HMAC) de la cascade garde le HT du service et écrit par
  `.update()`.
Le paiement complémentaire et la 2ᵉ carte gardent l'écriture d'avant (fiches B-2b, B-2c). /
The NFC-only card payment writes, in the same transaction as its lines, a settled `Vente`,
its payments (copied from the real debits: one per fedow_core transaction, one per remote
network transaction with its uuid in `reference_externe`, gift tokens offered and paid
LG, points in their own unit) and the whole-cent amounts of each part. A broken equality
is caught like an insufficient balance: nothing written, error screen, incident logged
with the network transaction uuids.

**Pourquoi / Why :** chantier 05, fiche B §1, §2, §4 (B-2a), §6 ; tronc §2, D7-D10, §5 ;
décisions `CHANTIER-05-SUIVI.md` §4-§5 (monnaie du réseau → `reference_externe` ; journal
d'incident avec les uuid du réseau). / Work 05, sheet B.

**Changements de comportement voulus / Intended behaviour changes :**
- **`LigneArticle.total_ht` d'une part payée en jetons : 0** (net vendu 0, part offerte,
  D8) au lieu du HT de son montant. Le champ porte le HT du NET vendu, comme pour une
  ligne offerte depuis B-1.
- **Archive fiscale LNE : mêmes HT et TVA qu'avant le chantier.** Son seul lecteur de
  `total_ht` (`laboutik/archivage.py`, `_extraire_lignes_article`) en déduisait
  TVA = TTC de la ligne − HT : une ligne offerte (depuis B-1) ou une part en jetons y
  aurait reçu une TVA inventée (bière offerte à 5 € : TVA 500). Pour une ligne écrite par
  le service de vente (elle appartient à une vente), l'archive recalcule donc le HT comme
  la caisse le stockait avant (TTC de la ligne = `amount × qty` arrondi 0,5 vers le haut,
  puis `calculer_total_ht`) ; une ligne sans vente garde son HT stocké. La formule de TVA
  ne change pas. La fiche G fait passer l'archive aux montants entiers des ventes. Cette
  correction répare aussi la régression de B-1 (ligne offerte).
- Égalité rompue en NFC : écran d'erreur « Le paiement n'a pas été enregistré : la vente
  est incohérente. Prévenez un responsable du lieu. » (409).

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_debiter_legacy` rend aussi l'uuid de chaque transaction (4ᵉ élément) ; `_repartir_legacy_sur_articles` lit les éléments par position (produit inchangé, tuples à 3 ou 4 éléments) ; `_creer_lignes_articles_cascade(vente=…)` : parts par `ajouter_article` (argent réel imposé, jetons offerts, TVA par `_taux_tva_de_la_ligne_de_caisse`, prix d'achat, coût au poids par part), boucle HMAC par `.update()` sans recalcul du HT ; `_payer_par_nfc` : vente ouverte dans l'`atomic` (unité des points, client, carte, opérateur, clé d'idempotence ; panier vide : pas de vente, comme B-1), recharges dans la même vente avec `uuid_transaction`, règlements depuis les transactions (points, cascade, legacy), `encaisser_vente` en dernier, `except EgaliteDeVenteRompue`, journal d'incident avec les uuid du réseau ; docstrings de `_executer_recharges` et de `_creer_lignes_articles` mises à jour (le NFC seul écrit sa vente) |
| `laboutik/archivage.py` | `_extraire_lignes_article` : HT recalculé pour une ligne d'une vente (voir plus haut) |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 16 tests ajoutés : fiche §6 10, 11, 12a, 14, 15, 16, 17c, 17d ; poids payé avec deux monnaies ; 22b ; recharge cadeau seule par la route NFC ; archive LNE (ligne offerte, part en jetons, ligne ordinaire, ligne sans vente, part au centime arrondie comme avant) |
| `tests/pytest/test_total_ht_ligne.py` | réécrit (voir plus bas) |

Chaîne i18n ajoutée (msgid en français, workflow i18n à lancer par le mainteneur) :
« Le paiement n'a pas été enregistré : la vente est incohérente. Prévenez un responsable
du lieu. »

#### Tests existants réécrits / Rewritten existing tests (B-2a)

| Fichier | Raison |
|---|---|
| `tests/pytest/test_total_ht_ligne.py::test_le_ht_des_parts_d_un_paiement_en_cascade` | attendu `[0, 333]` au lieu de `[333, 500]` : `total_ht` porte le HT du net vendu, et la part payée en jetons cadeau est offerte (D8, net 0). Décision du mainteneur (SUIVI §4) ; l'archive fiscale, seul ancien lecteur du champ, garde ses valeurs d'avant (voir plus haut). |

#### Tests vus échouer / Tests seen failing (B-2a)

Rouge (avant le code ; rejoué par l'orchestrateur : 10 failed, 21 passed) :
```
test_caisse_ecrit_la_vente.py:331: AssertionError: Attendu : une vente pour la clé …, trouvé : 0.   (10, 11, 12a, 14, 15, 17c, 17d, 22b, recharge cadeau NFC, puis poids à deux monnaies)
test_caisse_ecrit_la_vente.py:2034: assert 'data-testid="alerte-messages"' in '…ECRAN SUCCES DE PAIEMENT…'   (16)
```
Journal d'incident sans les uuid du réseau (code écrit, message encore d'avant) :
```
test_caisse_ecrit_la_vente.py:2053: AssertionError: assert '27287c98-…' in 'INCIDENT legacy débité sans LigneArticle (atomic local échoué) — uuid_transaction=… carte=74F6DC7A montant_legacy=850 : régularisation manuelle requise.'
```
Archive LNE (code NFC écrit, archive encore d'avant : 2 failed, 2 passed) :
```
test_caisse_ecrit_la_vente.py:2375: AssertionError: assert '0' == '500'   (ligne offerte)
test_caisse_ecrit_la_vente.py:2410: AssertionError: assert '0' == '500'   (part en jetons)
```
Verts avant le code de l'archive (témoins) : `test_archive_lne_ligne_ordinaire_inchangee`,
`test_archive_lne_ligne_sans_vente_garde_son_ht_stocke`.
Test existant tombé avec le code NFC, puis réécrit (voir plus haut) :
`test_total_ht_ligne.py:240: AssertionError: HT des parts : [0, 333]`.

Vert : `test_caisse_ecrit_la_vente.py` + `test_total_ht_ligne.py` : 40 passed ; lot cascade,
NFC, points, legacy, archive et caractérisation (29 fichiers) : 436 passed ; voisins
(clôtures, Z, export comptable, point de vente, vider carte, rapports, service de vente,
admin consigne, controlvanne, panier) : 193 passed ; caractérisation seule : 22 passed,
sans modification ; `manage.py check` : aucun problème ; `makemigrations --check
--dry-run` : « No changes detected ».

#### Mutations (B-2a)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`,
sauf mention.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| `total_catalogue_impose` retiré (`:6211`) | ligne retirée (total depuis la `qty` partielle) | **aucun : mutation équivalente**. Les quantités partielles ont 6 décimales, et l'arrondi 0,5 vers le haut de prix × quantité retombe sur l'argent de la part tant que le prix unitaire est sous 10 000 €. Gardé en double sécurité (décision de l'orchestrateur) |
| règlement cashless = somme des parts (`:9317`) | `montant=transaction_de_la_monnaie.amount` → `montant=total_debit_asset` | aucun : équivalent (même valeur) |
| uuid de la transaction perdu (`:9321`) | `fedow_transaction_uuid=transaction_de_la_monnaie.uuid` → `None` | 10, 11 |
| un règlement par part au lieu d'un par monnaie (`:9302-9322`) | boucle sur les parts de `lignes_nfc` | 10 |
| règlement legacy par part (`:9332`) | `for transaction_legacy in transactions_legacy:` → boucle sur `lignes_legacy` | 15 |
| `reference_externe` legacy non posée (`:9343`) | `reference_externe=str(uuid_de_la_transaction_legacy)` → `""` | 15 |
| `EgaliteDeVenteRompue` plus attrapée (`:9491`) | `except EgaliteDeVenteRompue as erreur_d_egalite:` → `except ZeroDivisionError as erreur_d_egalite:` | 16 |
| uuid du réseau hors du journal (`:9188`) | `uuids_des_transactions_legacy.append(…)` retiré | 16 |
| boucle HMAC de la cascade qui repasse par `calculer_total_ht` (`:6304`) | `if vente is None:` → `if True:` | 17c |
| `quantite_pour_cout` non passé (`:6212`) | ligne retirée | 17d, poids à deux monnaies |
| coût au poids sans la fraction de la part (`:6191`) | `* quantite_de_la_part` retiré | poids à deux monnaies |
| jetons comptés comme argent : part non offerte (`:6171`) | `part_payee_en_jetons = payment_method_code == PaymentMethod.LOCAL_GIFT` → `= False` | 12a, 10 |
| jetons comptés comme argent : règlement LE (`:9314`) | `moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[…]` → `moyen=PaymentMethod.LOCAL_EURO` | 12a, 10 |
| `unite` non posée en points (`:9215`) | `unite_de_la_vente = str(monnaie_du_panier_en_points.uuid)` → `= "EUR"` | 14 |
| `idempotency_key` non posée (`:9234`) | `idempotency_key=str(uuid_transaction),` → `idempotency_key=None,` | 22b et tous les tests qui retrouvent leur vente |
| panier vide qui ouvre une vente (`:9222`) | `panier_vide = len(articles_panier) == 0` → `panier_vide = False` | `test_vente_en_points.py::test_une_monnaie_archivee_ne_vend_plus_ses_tarifs` (erreur 500) |
| archive qui relit le champ stocké (`laboutik/archivage.py:190`) | `ligne_ecrite_par_le_service_de_vente = ligne.vente_id is not None` → `= False` | archive : ligne offerte, part en jetons |
| archive qui recalcule toutes les lignes (`laboutik/archivage.py:190`) | `… = ligne.vente_id is not None` → `= True` | archive : ligne sans vente |
| archive qui tronque le TTC (`laboutik/archivage.py:194`) | `rounding=ROUND_HALF_UP` → `rounding=ROUND_DOWN` | `test_archive_lne_part_au_centime_arrondi_comme_avant` (ajouté après la première série de mutations, où elle survivait) : 3 jus à 3,50 € payés 550 en jetons + 500 en monnaie locale ; part locale 350 × 1,428571 = 499,99985 → HT 417, TVA 82 (troncature : HT 416) |

### Session B-2b — la carte ne suffit pas : le reste en espèces ou en CB écrit la Vente / Card + cash or bank card writes the sale

**Migration :** Non.

**Quoi / What :** le paiement complémentaire en espèces ou en CB
(`_executer_paiement_complementaire`, branche espèces / CB : la carte du client paie ce
qu'elle peut, la monnaie du réseau éventuellement une partie du reste, les espèces ou la
CB le solde) écrit dans la même transaction que ses lignes une `Vente` encaissée, ses
règlements et les montants entiers de chaque part, sur le modèle de B-2a :
- vente ouverte dans l'`atomic` : origine caisse, point de vente, opérateur, client = le
  titulaire de la carte 1, carte 1, clé d'idempotence = la clé du paiement ;
- lignes écrites comme avant, par `_creer_lignes_articles_cascade(..., vente=vente)` ;
- règlements copiés des débits réels : un par transaction `fedow_core` de la carte 1
  (montant et uuid de la transaction renvoyée, monnaie, carte, portefeuille ; jetons
  cadeau → `LG`), un par transaction du réseau (uuid dans `reference_externe`), et UN
  règlement espèces ou CB du **reste dû** (jamais la somme donnée : la monnaie rendue
  n'est pas un règlement ; aucun règlement de 0 si le réseau paie tout le reste) ;
- `encaisser_vente` en dernier ; `except EgaliteDeVenteRompue` placé **avant**
  `except Exception` : rien n'est écrit, écran d'erreur 409 (même message qu'en B-2a),
  et si la monnaie du réseau a déjà été débitée, un seul INCIDENT journalisé (montant,
  carte, uuid de chaque transaction du réseau), préparé avant l'`atomic`. Le même
  message sert au solde insuffisant ; le journal « débit legacy orphelin » de
  `except Exception` porte aussi ces uuid ;
- les recharges cadeau de ce chemin (injoignables aujourd'hui : mêlées à d'autres
  articles elles sont refusées, seules elles ne laissent rien à payer) reçoivent quand
  même la vente et l'identifiant du paiement, au cas où une garde changerait. Pas de
  test (décision de l'orchestrateur, SUIVI §4).
Adhésions inchangées (FK sur la même part, effets B-0). La 2ᵉ carte garde l'écriture
d'avant (B-2c). /
The complementary payment in cash or by bank card writes, in the same transaction as its
lines, a settled `Vente` and its payments: one per card transaction, one per remote
network transaction (`reference_externe`), and ONE cash / bank card payment of the amount
due (never the amount handed over). A broken equality is caught before the generic
`except`: nothing written, error screen, one incident log with the network uuids.

**Pourquoi / Why :** chantier 05, fiche B §1, §2 (ligne « Complément espèces/CB »), §4
(B-2b), §6 (tests 9, 12, 16) ; tronc §2, D7, D8, §5 ; décisions `CHANTIER-05-SUIVI.md`
§4-§5. / Work 05, sheet B.

**Changements de comportement voulus / Intended behaviour changes :**
- Égalité rompue au paiement complémentaire : écran d'erreur « Le paiement n'a pas été
  enregistré : la vente est incohérente. Prévenez un responsable du lieu. » (409) au lieu
  d'une erreur 500.
- Journaux d'incident du complément (solde insuffisant, égalité rompue, exception) : ils
  portent les uuid des transactions du réseau.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_executer_paiement_complementaire`, branche espèces / CB seulement : `transactions_legacy` initialisée ; journal d'incident préparé avant l'`atomic` avec les uuid du réseau ; vente ouverte ; recharges avec `vente` et `uuid_transaction` ; règlements depuis les transactions (non fiduciaires, cascade de la carte 1, réseau) et règlement du reste dû ; `_creer_lignes_articles_cascade(vente=vente)` ; `encaisser_vente` en dernier ; `except EgaliteDeVenteRompue` (409) avant `except Exception` ; uuid du réseau dans le journal « débit legacy orphelin » |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 7 tests ajoutés : fiche §6 9, 12, 12b, 15b, 16b, 22c, et 15c `test_complement_reseau_paie_tout_le_reste_aucun_reglement_especes` (le solde du réseau, relu au complément, couvre tout le reste : aucun règlement espèces, ni de 0) ; assistants `payer_le_reste_en_especes_ou_en_cb`, `reglements_complets_de_la_vente` ; docstring du module |

Aucune nouvelle chaîne i18n (le message d'égalité rompue existe depuis B-2a).

Tests existants : aucun modifié.

#### Tests vus échouer / Tests seen failing (B-2b)

Rouge (avant le code ; rejoué par l'orchestrateur : 6 failed, 37 passed) :
```
test_caisse_ecrit_la_vente.py:341: AssertionError: Attendu : une vente pour la clé …, trouvé : 0.   (9, 12, 12b, 15b, 22c)
test_caisse_ecrit_la_vente.py:2778: assert 'data-testid="alerte-messages"' in '…ECRAN SUCCES DE PAIEMENT…'   (16b)
```
Après le rouge, le 15b a été renforcé (le réseau paie 7,00 € au lieu de 5,00 €, sa
transaction FED couvre deux parts) pour que la mutation « règlement legacy par part »
le fasse tomber ; il échouait toujours au même endroit (aucune vente).
Le 15c est ajouté après le vert, à la demande de l'orchestrateur : il passe sur le code
et fixe la garde « aucun règlement de 0 ». Chemin atteignable par la vraie route :
`lire_depensable_fed_frais` relu au complément rend au moins le reste dû, donc
`montant_legacy = total_complementaire` et `montant_paye_en_complement = 0`.

Vert : `test_caisse_ecrit_la_vente.py` : 43 passed, puis 44 avec le 15c ; complément, legacy, adhésion,
offerts, idempotence, HT, archive LNE, ticket, écrans de paiement, points et les
5 fichiers de caractérisation (15 fichiers) : 211 passed ; caractérisation seule :
22 tests, sans modification ; `manage.py check` : aucun problème ; `makemigrations
--check --dry-run` : « No changes detected ».

#### Mutations (B-2b)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| règlement du reste = somme donnée (`:10620`) | `montant=montant_paye_en_complement,` → `montant=somme_donnee_en_centimes or montant_paye_en_complement,` | 12b (égalité rompue → 409) |
| règlement du reste absent (`:10616-10621`) | bloc `if montant_paye_en_complement > 0:` retiré | 9, 12, 12b, 15b, 22c (409) |
| garde du règlement de 0 retirée (`:10616`) | `if montant_paye_en_complement > 0:` → `if True:` | 15c (`ajouter_reglement` refuse un montant 0 : `ValueError` relayée par `except Exception`) |
| `fedow_transaction_uuid` non posé (`:10585`) | `fedow_transaction_uuid=transaction_de_la_monnaie.uuid,` → `=None,` | 9 |
| règlement legacy par part (`:10596`) | `for transaction_legacy in transactions_legacy:` → boucle sur `lignes_legacy` (asset, montant, moyen de la part) | 15b (SF 300 + SF 200 au lieu de SF 500 ; plus de `reference_externe`) |
| `reference_externe` non posée (`:10607`) | `reference_externe=str(uuid_de_la_transaction_legacy),` → `=""` | 15b |
| `EgaliteDeVenteRompue` non attrapée (`:10710`) | `except EgaliteDeVenteRompue as erreur_d_egalite:` → `except ZeroDivisionError as erreur_d_egalite:` | 16b (exception relayée par `except Exception`) |
| `EgaliteDeVenteRompue` attrapée après `except Exception` | bloc `except EgaliteDeVenteRompue` (`:10710-10738`) déplacé après `except Exception` (`:10740`) | 16b |
| uuid du réseau absents du journal (`:10458`) | `uuids_des_transactions_legacy.append(…)` retiré | 16b |
| `vente` non passée à la cascade (`:10650`) | `vente=vente,` retiré | 9, 12, 12b, 15b, 22c (vente sans article refusée → exception) |
| jetons comptés comme argent (`:10578`) | `moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[asset_a_debiter.category]` → `moyen=PaymentMethod.CC` | 12 (2ᵉ égalité rompue → 409), 9 (moyen du règlement de la carte) |
| `idempotency_key` non posée (`:10489`) | `idempotency_key=str(uuid_transaction),` → `idempotency_key=None,` | 9, 12, 12b, 15b, 22c (aucune vente retrouvée) |
| client de la vente non posé (`:10487`) | `client=carte1.user,` → `client=None,` | 15b |
| recharges hors de la vente (`:10508`) | `vente=vente,` retiré | aucun : chemin injoignable (décision : pas de test) |

### Session B-2c — la 2ᵉ carte écrit la Vente, la cascade exige une vente / 2nd card writes the sale, the cascade requires a sale

**Migration :** Non.

**Quoi / What :** le paiement complémentaire par une 2ᵉ carte
(`_executer_paiement_complementaire`, branche `nfc` : la carte 1 paie ce qu'elle peut, le
réseau éventuellement une partie du reste pour elle, la carte 2 le reste — sa cascade
locale, ou son réseau s'il couvre tout —, puis au besoin les espèces ou la CB depuis le
second écran « reste à payer ») écrit dans la même transaction que ses lignes une `Vente`
encaissée, ses règlements et les montants entiers de chaque part, sur le modèle de B-2b :
- vente ouverte dans l'`atomic` : origine caisse, point de vente, opérateur, client = le
  titulaire de la carte 1, carte 1, clé d'idempotence = la clé du paiement ;
- lignes écrites comme avant (`carte = carte 1` sur toutes les parts, jusqu'à H), par
  `_creer_lignes_articles_cascade(..., vente=vente)` ;
- règlements copiés des débits réels, **chacun avec la carte qui a payé** : un par
  transaction `fedow_core` de la carte 1 (carte 1, son portefeuille) et de la carte 2
  (carte 2, **son** portefeuille), montant et uuid de la transaction renvoyée ; un par
  transaction du réseau de chaque carte (uuid dans `reference_externe`, la carte débitée,
  sans portefeuille comme en B-2b) ; UN règlement espèces ou CB du **reste dû** après les
  deux cartes (jamais la somme donnée ; aucun règlement de 0 quand les cartes couvrent
  tout) ;
- `encaisser_vente` en dernier ; `except EgaliteDeVenteRompue` **avant**
  `except Exception` : rien n'est écrit, écran d'erreur 409 (même message qu'en B-2a) ;
- journal d'incident **unique**, préparé avant l'`atomic`, qui couvre les débits du réseau
  **des deux cartes** (pour chaque carte débitée : carte, montant, uuid des transactions) :
  utilisé pour le solde insuffisant et l'égalité rompue. Avant, seul le réseau de la
  carte 2 y figurait, sans uuid ;
- **débit orphelin** : le réseau de la carte 2 est débité avant celui de la carte 1 ; si
  le débit de la carte 1 échoue (409 « rescannez la carte »), le débit déjà fait de la
  carte 2 est maintenant journalisé (INCIDENT : montant, carte 2, uuid). Même écran, même
  statut qu'avant ;
- débits non fiduciaires et recharges cadeau de ce chemin, **injoignables** (panier en
  points refusé en tête de fonction ; recharge cadeau mêlée refusée, seule elle ne laisse
  rien à payer) : ils reçoivent quand même la vente (et l'identifiant du paiement pour
  les recharges), avec un commentaire qui dit la contrainte. Pas de test (décision de
  l'orchestrateur, SUIVI §4) ;
- `_creer_lignes_articles_cascade` : la branche « vente absente » (création directe par
  `LigneArticle.objects.create`, HT recalculé par la boucle HMAC) est retirée ; `vente`
  devient un paramètre obligatoire (2ᵉ position, sans valeur par défaut). Ses trois
  appelants (NFC seul, complément espèces / CB, 2ᵉ carte) la passent.
- `except Exception` (exception imprévue dans l'`atomic`) : son journal INCIDENT reprend
  le message préparé avant l'`atomic` (les débits du réseau des DEUX cartes : carte,
  montant, uuid), suivi de l'exception, puis l'exception est relayée (500 volontaire,
  comme avant). Avant, il ne citait que le réseau de la carte 2, sans uuid (décision de
  l'orchestrateur, SUIVI §4).
Adhésions inchangées (FK sur la même part, effets B-0). `carte_complement`, paramètre non
utilisé de la cascade, est gardé (hors périmètre). /
The second-card complementary payment writes a settled `Vente` and its payments, each
payment carrying the card that paid (card 2's payments carry card 2 and its wallet). One
incident log covers both cards' network debits; a card-2 network debit left orphaned by a
failed card-1 network debit is now logged. The cascade no longer accepts a missing sale.

**Pourquoi / Why :** chantier 05, fiche B §1, §2 (ligne « 2ᵉ carte »), §4 (B-2c), §6
(tests 13, 16) ; tronc §2, D7, D8, §5 ; décisions `CHANTIER-05-SUIVI.md` §4-§5. /
Work 05, sheet B.

**Changements de comportement voulus / Intended behaviour changes :**
- Égalité rompue au paiement par 2ᵉ carte : écran d'erreur « Le paiement n'a pas été
  enregistré : la vente est incohérente. Prévenez un responsable du lieu. » (409) au lieu
  d'une erreur 500.
- Journal d'incident de la 2ᵉ carte : il porte aussi le débit du réseau de la carte 1, et
  les uuid des transactions du réseau des deux cartes.
- Débit du réseau de la carte 1 en échec après celui de la carte 2 : un INCIDENT est
  journalisé (rien avant).
- Exception imprévue dans l'`atomic` de la 2ᵉ carte : l'INCIDENT couvre les débits du
  réseau des deux cartes, avec les uuid (avant : carte 2 seule, sans uuid).

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_executer_paiement_complementaire`, branche 2ᵉ carte seulement : `transactions_legacy_c1` / `_c2` initialisées ; INCIDENT du débit de la carte 2 quand le débit de la carte 1 échoue ; journal d'incident unique préparé avant l'`atomic` ; vente ouverte ; recharges avec `vente` et `uuid_transaction` ; règlements depuis les transactions (non fiduciaires, cascades carte 1 et carte 2, réseau des deux cartes) et règlement du reste dû ; `_creer_lignes_articles_cascade(vente=vente)` ; `encaisser_vente` en dernier ; `except EgaliteDeVenteRompue` (409) avant `except Exception` ; `except Exception` journalise le message préparé (deux cartes) plus l'exception. `_creer_lignes_articles_cascade` : branche « vente absente » retirée (création et boucle HMAC), `vente` obligatoire, docstring mise à jour (plus de TODO) |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 7 tests ajoutés : fiche §6 13, 13b, 13c, 16c, 22d, 16d `test_deuxieme_carte_debit_reseau_carte1_echoue_incident_carte2_journalise` et 16e `test_deuxieme_carte_exception_imprevue_journalise_les_deux_cartes` ; assistants `payer_le_reste_avec_une_deuxieme_carte`, `payer_le_reste_apres_les_deux_cartes`, `solde_du_reseau_simule_par_membre`, `fedow_du_reseau_simule_par_membre`, `montant_debite_par_membre` ; docstring du module |
| `tests/pytest/test_paiement_complementaire.py` | simulacre de `_debiter_legacy` au format à 4 éléments (voir « Tests existants réécrits ») |

Aucune nouvelle chaîne i18n (le message d'égalité rompue existe depuis B-2a ; les
journaux ne sont pas traduits).

#### Tests existants réécrits / Rewritten existing tests (B-2c)

| Test | Raison |
|---|---|
| `tests/pytest/test_paiement_complementaire.py::TestPaiementComplementaire::test_carte1_fed_plus_carte2_finalise_le_paiement` | son simulacre de `_debiter_legacy` rendait des 3-uplets `(asset, montant, moyen)` ; la vraie fonction rend depuis B-2a un 4ᵉ élément, l'uuid de la transaction distante, que la 2ᵉ carte copie désormais dans le règlement (`reference_externe`) et le journal d'incident. Seul ce simulacre change (uuid en texte fixe), avec un commentaire (décision de l'orchestrateur, SUIVI §4) |

#### Tests vus échouer / Tests seen failing (B-2c)

Rouge (avant le code ; rejoué par l'orchestrateur : 5 failed, 44 passed) :
```
test_caisse_ecrit_la_vente.py:341: AssertionError: Attendu : une vente pour la clé …, trouvé : 0.   (13, 13b, 13c, 22d)
test_caisse_ecrit_la_vente.py:3502: assert 'data-testid="alerte-messages"' in '…ECRAN SUCCES DE PAIEMENT…'   (16c)
```
Avant de tomber, le 13b et le 16c ont vérifié que le réseau est bien débité pour les
DEUX cartes dans le même paiement (chemin atteignable par la vraie route), et le 13c que
le 1er passage « 2ᵉ carte insuffisante » n'écrit aucune vente.
16d, ajouté sur décision de l'orchestrateur, vu rouge avant son code :
```
test_caisse_ecrit_la_vente.py:3617: AssertionError: Attendu : un incident journalisé, trouvé : []
```
(le 409 et l'écran d'erreur existaient déjà ; seul le journal manquait).
16e, ajouté sur décision de l'orchestrateur, vu rouge avant son code (l'exception était
déjà relayée ; le client de test Django relaie l'exception de la vue, le test l'attend
par `pytest.raises(RuntimeError)`) :
```
test_caisse_ecrit_la_vente.py:3732: AssertionError: assert None
  where None = re.search('\\b300\\b', 'INCIDENT : débit legacy orphelin (2ème carte, exception atomic) — carte=7E0B9490 montant_legacy_centimes=550 uuid_transaction=… exception=Erreur imprévue simulée par le test.')
```
Vert après le code : `test_caisse_ecrit_la_vente.py` + `test_paiement_complementaire.py` :
66 passed.
Après le vert, le 13b a été renforcé (un café en plus, 10,50 € ; la transaction FED de
CHAQUE carte couvre deux parts) : sinon la mutation « règlement legacy par part » sur la
carte 1 survivait (sa transaction ne couvrait qu'une part).

Vert : `test_caisse_ecrit_la_vente.py` : 50 passed ; complément, legacy, adhésion,
offerts, idempotence, HT, archive LNE, ticket, écrans de paiement, points, les autres
fichiers qui parlent de 2ᵉ carte (`test_admin_annulation_abonnement_stripe.py`,
`test_bank_transfer_service.py`, `test_card_refund_service.py`,
`test_pages_admin_apercu.py`, `test_panier_mvt.py`) et les 5 fichiers de caractérisation
(20 fichiers) : 340 passed ; caractérisation : 22 tests, sans modification ;
`manage.py check` : aucun problème ; `makemigrations --check --dry-run` : « No changes
detected ».

#### Mutations (B-2c)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| règlement de la carte 2 avec la carte 1 (`:11338`) | `carte=carte2,` → `carte=carte1,` | 13, 13c |
| portefeuille de la carte 2 remplacé par celui de la carte 1 (`:11339`) | `wallet=wallet_carte2,` → `wallet=wallet_carte1,` | 13, 13c |
| `fedow_transaction_uuid` non posé, carte 1 (`:11302`) | `fedow_transaction_uuid=transaction_de_la_monnaie_c1.uuid,` → `=None,` | 13, 13c |
| `fedow_transaction_uuid` non posé, carte 2 (`:11340`) | `fedow_transaction_uuid=transaction_de_la_monnaie_c2.uuid,` → `=None,` | 13, 13c |
| règlement legacy par part (`:11353`, `:11362`) | boucles sur `transactions_legacy_c1` / `_c2` → boucles sur `lignes_legacy_c1` / `_c2` (asset, montant, moyen de la part) | 13b (SF 500 + SF 100 au lieu de SF 600 ; SF 100 + SF 200 au lieu de SF 300) |
| `reference_externe` non posée (`:11360`, `:11369`) | `reference_externe=str(…[3]),` → `=""` | 13b |
| règlement legacy de la carte 2 avec la carte 1 (`:11368`) | `carte=carte2,` → `carte=carte1,` | 13b |
| règlement du reste = somme donnée (`:11382`) | `montant=total_reste_apres_carte2,` → `montant=donnees_paiement["given_sum"] or total_reste_apres_carte2,` | 13c (égalité rompue → 409) |
| garde du règlement de 0 retirée (`:11378`) | `if lignes_reste_apres_carte2:` → `if True:` | 13, 13b, 22d (`pm_reste` non défini → `NameError`, relayée par `except Exception`) |
| legacy de la carte 1 absent du journal (`:11158-11162`) | bloc `if transactions_legacy_c1:` retiré | 16c |
| uuid de la carte 2 absents du journal (`:11155`) | `uuids_des_transactions_legacy_c2.append(…)` retiré | 16c |
| INCIDENT de la carte 2 absent quand le débit de la carte 1 échoue (`:11106-11124`) | bloc `if transactions_legacy_c2:` retiré | 16d |
| `EgaliteDeVenteRompue` non attrapée (`:11485`) | `except EgaliteDeVenteRompue as erreur_d_egalite:` → `except ZeroDivisionError as erreur_d_egalite:` | 16c |
| `EgaliteDeVenteRompue` attrapée après `except Exception` | bloc `except EgaliteDeVenteRompue` (`:11485-11513`) déplacé après `except Exception` (`:11515`) | 16c |
| `vente` non passée à la cascade (`:11424`) | `vente=vente,` retiré | 13, 13b, 13c, 22d (`TypeError` : `vente` est obligatoire) |
| `encaisser_vente` retiré (`:11460`) | ligne retirée | 13, 13b, 13c, 22d (vente `EN_ATTENTE`, sans numéro ; `verifier_egalites`) et 16c (écran de succès) |
| carte 1 absente du journal de `except Exception` (`:11525-11528`) | `logger.error(f"{message_d_incident_legacy} Exception imprévue dans l'atomic : {e}")` → l'ancien journal de la carte 2 seule (`carte={carte2.tag_id} montant_legacy_centimes={montant_legacy_c2}`) | 16e |
| `idempotency_key` non posée (`:11202`) | `idempotency_key=str(uuid_transaction),` → `idempotency_key=None,` | 13, 13b, 13c, 22d (aucune vente retrouvée) |
| client de la vente non posé (`:11200`) | `client=carte1.user,` → `client=None,` | 13b |
| recharges hors de la vente (`:11221`) | `vente=vente,` retiré | aucun : chemin injoignable (décision : pas de test) |
| règlement non fiduciaire non écrit (`:11252-11260`) | appel `ajouter_reglement` retiré | aucun : chemin injoignable (décision : pas de test) |

### Session B-2d — la caisse encaisse l'ancien Fedow, preuve de bout en bout / The register settles old-Fedow money, end to end

**Migration :** Non. **Aucun code de production.**

**Quoi / What :** deux tests E2E contre le VRAI ancien Fedow (distant) prouvent que le
système hybride tient à la caisse : une carte NFC sans aucun jeton du moteur local
(`fedow_core`) paie un article à 2,50 € par la vraie route `/laboutik/paiement/payer/`,
et la cascade passe par l'ancien Fedow (`lire_depensable_fed_frais`, `_debiter_legacy`,
`to_place_from_qrcode`). Chaque test relit l'état réel (ancien Fedow et base) :
- solde de l'ancien Fedow baissé du prix, moteur local intact (jetons à 0, aucune
  transaction émise par le portefeuille) ;
- `Vente` retrouvée par la clé du paiement, `REGLEE`, numérotée ;
- un règlement par transaction distante : moyen attendu, `reference_externe` = uuid d'une
  transaction qui EXISTE sur l'ancien Fedow (relue par `transaction/<uuid>`) : même
  montant, bonne monnaie, action « QRS », du portefeuille de l'adhérent vers celui du
  lieu, métadonnées = la clé du paiement ; `fedow_transaction_uuid` vide ;
- les deux égalités de la vente.

Les deux monnaies de l'ancien Fedow :
- **FED** (`test_caisse_encaisse_du_fed_de_l_ancien_fedow`, marqué `stripe_listen`) : le
  FED s'achète, il ne se crée pas (`refill_from_lespass_to_user_wallet` le refuse côté
  Fedow : « Asset type must be LOCAL »). L'adhérent le recharge d'abord par carte
  bancaire (vrai Stripe, 3 €), puis paie : règlement `SF`.
- **Monnaie locale du lieu** (`test_caisse_encaisse_la_monnaie_locale_de_l_ancien_fedow`,
  sans Stripe) : fixture `adherent_credite` (5 € de TLF sur l'ancien Fedow) : règlement
  `LE`. Le moyen seul ne distingue pas l'ancien Fedow du moteur local (une TLF locale
  donne aussi `LE`) : la preuve est le moteur local intact et la transaction distante
  « QRS » portant la clé du paiement.

Les étapes de la recharge Stripe sont sorties de `test_recharge_federee_par_carte_bancaire`
dans l'assistant `_recharger_en_monnaie_federee_par_carte_bancaire` (plus
`_verifier_que_la_recharge_federee_est_creditee`) ; le test existant garde le même
comportement. /
Two E2E tests against the real old Fedow prove a card with no local token pays at the
register through the old Fedow (FED, bought by card first; and the venue's local
currency), and that the written sale and payments are right. No production code.

**Pourquoi / Why :** chantier 05, fiche B §1 (ligne « Débit legacy Fedow »), §4 (B-2d) ;
SUIVI §5 (système hybride). Tous les tests pytest du paiement legacy en caisse simulent
l'ancien Fedow. / All pytest legacy-payment tests simulate the old Fedow.

| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_parcours_fedow_reel.py` | 2 tests ajoutés ; fixture `comptoir_de_l_ancien_fedow` (point de vente « Comptoir ancien Fedow E2E », article « Sirop E2E ancien Fedow » à 2,50 €) ; assistants `_rattacher_une_carte_a_l_adherent`, `_soldes_des_deux_moteurs_de_l_adherent`, `_payer_l_article_en_nfc`, `_lire_la_vente_et_ses_transactions`, `_verifier_la_vente_encaissee_par_l_ancien_fedow`, `_lire_json_marque` ; recharge Stripe sortie dans `_recharger_en_monnaie_federee_par_carte_bancaire` + `_verifier_que_la_recharge_federee_est_creditee` |

Ce que les tests laissent : à chaque passage, une vente encaissée et chaînée sur le lieu ;
2,50 € de TLF et 2,50 € de FED passés d'adhérents neufs au lieu sur l'ancien Fedow ; un
paiement Stripe de test de 3 €. Rien n'est annulé.

Vert : `-k caisse_encaisse_la_monnaie_locale` : 1 passed ; `-k caisse_encaisse_du_fed` :
1 passed ; fichier entier (`stripe listen` tourne) : 5 passed.

#### Mutations (B-2d)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| `reference_externe` non posée (`:9301`) | `reference_externe=str(uuid_de_la_transaction_legacy),` → ligne retirée | les deux (« ne dit pas quelle transaction ») |
| FED enregistré en monnaie locale (`:1663`) | `payment_method = PaymentMethod.STRIPE_FED` → `payment_method = PaymentMethod.LOCAL_EURO` | FED (moyen `LE` au lieu de `SF`) |
| uuid distant dans le mauvais champ (`:9301`) | `reference_externe=str(uuid_de_la_transaction_legacy),` → `fedow_transaction_uuid=uuid_de_la_transaction_legacy,` | les deux (`fedow_transaction_uuid` non vide) |
| TLF de l'ancien Fedow enregistrée en FED (`:1665`) | `payment_method = PaymentMethod.LOCAL_EURO` → `payment_method = PaymentMethod.STRIPE_FED` | monnaie locale (moyen `SF` au lieu de `LE`) |
| cran de l'ancien Fedow coupé (`:8977`) | `if total_complementaire > 0 and carte_client.user is not None:` → `if False:` | les deux (écran « reste à payer », aucune vente pour la clé, solde distant inchangé) |

### Session B-3a — la commande de table écrit la Vente et la garde / Table order writes the sale and keeps it

**Migration :** Non (`CommandeSauvegarde.vente` existe depuis `laboutik 0007`).

**Quoi / What :** le paiement d'une commande de table (`CommandeViewSet.payer_commande`)
écrit une `Vente` encaissée, et la commande la garde dans `CommandeSauvegarde.vente`.
Aucune logique métier ne change : commande payée, articles servis, table libérée,
comme avant.
- `payer_commande` tire l'identifiant du paiement (`uuid_transaction`). Il va sur
  chaque ligne et devient la clé d'idempotence de la vente.
- Espèces, CB, chèque : dans le même `atomic` que le statut de la commande, la vente
  est ouverte (`_ouvrir_la_vente_de_caisse`), les lignes sont écrites par
  `_creer_lignes_articles(..., uuid_transaction=, vente=)`, puis UN règlement du moyen,
  du montant encaissé (jamais la somme donnée), et `encaisser_vente` en dernier
  (`_regler_et_encaisser_la_vente_de_caisse`). Enfin `commande.vente = vente`.
- NFC : la clé est passée à `_payer_par_nfc` (`uuid_transaction_impose`). Après le
  succès, la vente est retrouvée par cette clé et posée sur la commande, dans l'`atomic`
  externe. Introuvable après un succès : `RuntimeError`, l'`atomic` externe annule le
  paiement NFC et le statut de la commande (jamais une commande payée sans vente).
/ Paying a table order writes a settled sale, kept on the order. Cash / card / cheque:
same atomic block, one payment of the collected amount. NFC: the key is passed to the
NFC payment, the sale is found by it; missing sale after a success → exception, the
outer atomic block rolls everything back.

**Pourquoi / Why :** chantier 05, fiche B §2 (ligne « Commande de table »), §5 (B-3a),
§6 (tests 18, 19) ; décisions `CHANTIER-05-SUIVI.md` §4 (B-3). / Work 05, sheet B.

**Inchangé, noté (bugs hors chantier) / Unchanged, noted :**
- n° 10 : aucune clé d'idempotence ni verrou sur `payer_commande` ; deux requêtes
  simultanées peuvent payer deux fois la même commande (la garde de statut est lue sans
  verrou). Aucune interface n'appelle cette route aujourd'hui.
- n° 11 : adhésion, recharge ou billet dans une commande de table : ni adhésion, ni
  crédit de carte, ni billet hors NFC ; billet jamais reconnu.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `payer_commande` seulement : `uuid_transaction` tiré ; NFC : clé passée à `_payer_par_nfc`, vente retrouvée par la clé (sinon `RuntimeError`), `commande.vente` posée ; hors NFC : vente ouverte, lignes avec `vente` et `uuid_transaction`, règlement et encaissement, `commande.vente` posée |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 4 tests (5 cas) : fiche §6 18, 18b (CB et chèque, paramétré), 19, 19b (témoin : solde insuffisant, rien d'écrit) ; assistants `creer_une_table_occupee_avec_sa_commande`, `payer_la_commande_de_table`, `vente_des_lignes_du_tarif`, `verifier_que_la_commande_est_payee_et_la_table_libre` ; docstring du module |

Aucune nouvelle chaîne i18n (le message de `RuntimeError` est un journal, pas un texte
affiché).

Tests existants : aucun modifié.

#### Tests vus échouer / Tests seen failing (B-3a)

Rouge (avant le code ; rejoué par l'orchestrateur : 4 failed, 52 passed) :
```
test_caisse_ecrit_la_vente.py:4158: AssertionError: La commande payée n'a pas de vente.   (18)
test_caisse_ecrit_la_vente.py:4228: AssertionError: La commande payée n'a pas de vente.   (18b CB, 18b chèque)
test_caisse_ecrit_la_vente.py:4298: AssertionError: La commande payée n'a pas de vente.   (19)
PASSED test_paiement_table_nfc_refuse_aucune_vente_commande_ouverte                       (19b, témoin)
```
En 19, la vente du paiement NFC existait déjà (règlement LE 1000 avec l'uuid de la
transaction) : seul le lien manquait.

Vert : `test_caisse_ecrit_la_vente.py` : 56 passed ; caractérisation (5 fichiers,
22 tests, sans modification), `test_caisse_effets_adhesion.py`, commandes de table
existantes (`test_hors_argent_offerts.py`, `test_cloture_caisse.py`,
`test_pos_retour_consigne.py`, `test_vente_en_points.py`) : 180 passed ;
`test_admin_retour_de_consigne.py`, `test_paiement_complementaire.py`,
`test_pos_models.py`, `test_total_ht_ligne.py` : 33 passed ; `manage.py check` : aucun
problème ; `makemigrations --check --dry-run` : « No changes detected ».

#### Mutations (B-3a)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| `commande.vente` non posée, hors NFC (`:13185-13186`) | ligne `commande.vente = vente` retirée, `update_fields=["statut"]` | 18, 18b (« La commande payée n'a pas de vente ») |
| `commande.vente` non posée, NFC (`:13122-13123`) | ligne `commande.vente = vente_du_paiement_nfc` retirée, `update_fields=["statut"]` | 19 |
| règlement absent (`:13178-13180`) | `_regler_et_encaisser_la_vente_de_caisse(vente, articles_panier, moyen_paiement_code)` → `encaisser_vente(vente)` | 18, 18b (égalité rompue : `EgaliteDeVenteRompue` sort de la vue) |
| règlement au mauvais moyen (`:13179`) | `vente, articles_panier, moyen_paiement_code` → `vente, articles_panier, "espece"` | 18b (CC / CHEQUE attendu, CASH trouvé ; 2ᵉ égalité tenue, donc pas d'exception) |
| clé non passée à `_payer_par_nfc` (`:13089`) | ligne `uuid_transaction_impose=uuid_transaction,` retirée | 19 (vente introuvable → `RuntimeError`) ; aussi P12 de la caractérisation |
| `encaisser_vente` retiré | dans `payer_commande`, `_regler_et_encaisser_la_vente_de_caisse(...)` → `ajouter_reglement(vente, moyen=MAPPING_CODES_PAIEMENT[moyen_paiement_code], montant=total_centimes)` | 18, 18b (vente `EN_ATTENTE`, sans numéro) |
| `vente` non passée à `_creer_lignes_articles` (`:13173`) | ligne `vente=vente,` retirée | 18, 18b (vente sans article refusée à l'encaissement → exception ; et lignes sans vente) |

### Session B-3c — correction de moyen : une vente CORRECTION liée / Payment method correction: a linked CORRECTION sale

**Migration :** Non.

**Quoi / What :** corriger le moyen de paiement d'une vente de caisse
(`PaiementViewSet.corriger_moyen_paiement`) écrit, **en plus** de la correction des
lignes d'aujourd'hui, une vente `CORRECTION`. La vente d'origine, déjà encaissée, ne
change jamais (D14).
- Ceinture (inchangée) : une `CorrectionPaiement` par ligne, et le nouveau
  `payment_method` sur les lignes (les anciens lecteurs en dépendent jusqu'à H).
- Bretelles, dans le même `atomic` : une vente `CORRECTION`, liée à la vente des
  lignes (`vente_liee`), de la caisse, au point de vente de la vente d'origine (le
  formulaire n'en envoie pas), à l'opérateur de la correction, sans article. Deux
  règlements : −montant à l'ancien moyen, +montant au nouveau ; montant = Σ `total_ttc`
  des lignes corrigées (additionnés, jamais recalculés). `encaisser_vente` en dernier.
- Lignes sans vente (écrites avant le chantier, base de dev seulement) : correction
  comme avant, sans vente `CORRECTION` (TODO fiche H).
- Nouvelle garde : lignes du périmètre appartenant à plusieurs ventes (ou certaines à
  aucune) → refus 400, rien d'écrit.
/ The line correction stays as today. On top of it, in the same transaction, a
CORRECTION sale linked to the original one, without items, with two payments
(−old method, +new method) of the sum of the corrected lines. The original sale never
changes. Lines without a sale: as before. Lines of several sales: refused.

**Pourquoi / Why :** chantier 05, fiche B §2 (ligne « Correction de moyen »), §5
(B-3c), §6 (test 21) ; tronc D14 ; décisions `CHANTIER-05-SUIVI.md` §4 (point de vente
de la vente d'origine, opérateur de la requête, base partagée pour ces tests). /
Work 05, sheet B; D14.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `corriger_moyen_paiement` seulement : lignes du périmètre lues une fois (`list`) ; garde « plusieurs ventes » ; montant corrigé = Σ `total_ttc` ; dans l'`atomic`, après la correction des lignes : `ouvrir_vente(CORRECTION, vente_liee=…)`, deux `ajouter_reglement`, `encaisser_vente` ; docstring |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 8 tests : fiche §6 21, 21b (témoin : clôture), 21c, 21d (témoin : ligne sans vente), 21e ; 21f (lignes de deux ventes refusées) ; 21g (deux lignes : montant = leur somme) ; 21h (vente de correction en échec : la correction des lignes est annulée aussi) ; assistants `corriger_le_moyen_de_paiement`, `ventes_de_correction_liees_a`, `nombre_de_ventes_de_correction`, `photographie_de_la_vente`, `anomalies_de_la_chaine_pour`, `verifier_la_vente_de_correction` ; docstring du module |

**Base partagée, pas de schéma dédié :** ces tests ne lisent que les anomalies de chaîne
de LEURS ventes (qui dépendent de leurs données et de la vente précédente, posée sous
verrou), n'assertent aucune valeur de numéro ; la clôture du 21b est annulée avec la
transaction du test.

Nouvelle chaîne i18n (1) : « Ces lignes appartiennent à plusieurs ventes : correction
impossible ».

Tests existants : aucun modifié.

#### Tests vus échouer / Tests seen failing (B-3c)

Rouge (avant le code ; rejoué par l'orchestrateur : 3 failed, 58 passed) :
```
test_caisse_ecrit_la_vente.py:4562: AssertionError: Attendu : une vente CORRECTION liée, trouvé : 0.   (21)
test_caisse_ecrit_la_vente.py:4719: AssertionError: Attendu : une vente CORRECTION liée, trouvé : 0.   (21c)
test_caisse_ecrit_la_vente.py:4863: AssertionError: Attendu : deux ventes CORRECTION liées, trouvé : 0. (21e)
PASSED test_correction_moyen_apres_cloture_refusee_aucune_vente                                          (21b, témoin)
PASSED test_correction_d_une_ligne_sans_vente_comme_avant                                                (21d, témoin)
```
21f, ajouté avant le code (garde demandée par l'orchestrateur) :
`test_caisse_ecrit_la_vente.py:4942: assert 200 == 400`.
21g et 21h sont ajoutés **après** le code, pour que deux mutations du brief aient un test
qui tombe (montant pris sur une seule ligne ; vente écrite hors de l'`atomic`) : leur
rouge est celui des mutations.

Vert : `test_caisse_ecrit_la_vente.py` : 64 passed ; `test_corrections_fond_sortie.py`,
`test_hors_argent_offerts.py`, `test_vente_en_points.py`, `test_vente_service.py` et la
caractérisation (5 fichiers, 22 tests, sans modification) : 193 passed (257 ensemble) ;
`manage.py check` : aucun problème ; `makemigrations --check --dry-run` : « No changes
detected ».

#### Mutations (B-3c)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). Toutes dans `laboutik/views.py`
(`sha256` avant : `b4a6adbd2dd0b2352cbe0661d5670bbd08a3c4b0ccb61ee86f6bc9818b11c552`).

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| correction qui modifie la vente d'origine (après `:12525`) | ajouter `Reglement.objects.filter(vente=vente_d_origine).update(moyen=nouveau_moyen)` (import local de `Reglement`) | 21, 21c, 21e (photographie : règlements et empreinte ; chaîne : « empreinte fausse ») |
| `vente_liee` non posée (`:12508`) | ligne `vente_liee=vente_d_origine,` retirée | 21, 21c, 21e, 21g (0 vente liée) |
| signes inversés (`:12516`, `:12521`) | `-montant_corrige_en_centimes` ↔ `montant_corrige_en_centimes` | 21, 21c, 21e, 21g |
| montant = 0 (`:12464`) | `+= ligne_a_corriger.total_ttc` → `+= 0` | 21, 21c, 21e, 21g (`ajouter_reglement` refuse 0 : exception) |
| montant d'une seule ligne (`:12463-12464`) | boucle → `montant_corrige_en_centimes = lignes_a_corriger[0].total_ttc` | 21g seul |
| `encaisser_vente` retiré (`:12525`) | ligne retirée | 21, 21c, 21e (vente `EN_ATTENTE`), 21h (aucune exception) |
| vente `CORRECTION` écrite hors de l'`atomic` (`:12497-12525`) | bloc `if vente_d_origine is not None:` sorti du `with` (désindenté) | 21h (la ligne reste en CB après l'échec) |
| vente `CORRECTION` pour une ligne sans vente (`:12497`) | `if vente_d_origine is not None:` → `if True:` | 21d (exception : `None.point_de_vente`) |
| garde « plusieurs ventes » retirée (`:12444`) | `> 1` → `> 99` | 21f |
| point de vente non posé (`:12506`) | `vente_d_origine.point_de_vente` → `None` | 21, 21c, 21e |
| opérateur non posé | `operateur=operateur,` → `operateur=None,` (dans `ouvrir_vente`) | 21, 21c, 21e |

### Session B-3d — les anciens rapports de caisse gardent leurs totaux / Old register reports keep their totals

**Migration :** Non.

**Quoi / What :** test de non-régression (fiche §6, test 23), aucun code de production.
Trois ventes par la vraie route de la caisse, dans un schéma dédié : 3 jus à 3,50 € en
espèces (scénario 1) ; 3 jus payés 5,00 € en monnaie locale sur la carte + 5,50 € en CB
(scénario 9) ; une bière à 5,00 € payée 3,00 € en jetons cadeau + 2,00 € en CB
(scénario 12). Pour chacune, l'ancien rapport de caisse (`laboutik/reports.py`,
`RapportComptableService`) est relu sur les six calculs du ticket Z : totaux par moyen,
détail des ventes, TVA, solde de caisse, offerts, recharges. Les valeurs attendues sont
calculées à la main avec les formules du rapport et les champs que la caisse écrivait
avant le chantier (calcul en commentaire au-dessus de chaque valeur). Chaque scénario
vérifie aussi que la vente existe et `verifier_egalites(vente)`. /
Non-regression test, no production code: three register sales, then the old register
report's six Z computations, with expected values computed by hand from the report's
formulas.

**Pourquoi / Why :** tronc §5 (transition) : pendant « écrire deux fois », les anciens
lecteurs doivent donner les mêmes totaux. / During the transition, old readers must give
the same totals.

`laboutik/reports.py` est identique à `HEAD` et n'a pas été modifié depuis avant le
chantier (dernier commit : `1b1aedcb`) : l'ancien et le nouveau rapport sont le même
code. / The report file is unchanged since before the work.

| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_caisse_anciens_rapports.py` | nouveau : `FastTenantTestCase` (schéma `test_anciens_rapports`), 3 tests `test_anciens_rapports_inchanges_*` (scénarios 1, 9, 12) |

Chaînes i18n ajoutées : aucune. Tests existants : aucun modifié.

#### Valeurs attendues (ancien rapport) / Expected values

| Calcul | Scénario 1 | Scénario 9 | Scénario 12 |
|---|---|---|---|
| lignes écrites | CA 350 × 3 | LE 350 × 1,428571 ; CC 350 × 1,571429 | LG 500 × 0,6 ; CC 500 × 0,4 |
| totaux par moyen | espèces 1050, total 1050 | CB 550, cashless 500 (monnaie locale), total 1050 | CB 200, cashless 300 (jetons), total 500 |
| détail des ventes | vendus 3, TTC 1050, HT 875, TVA 175, coût 300, bénéfice 575 | idem scénario 1 | vendus 0,4, offerts 0,6, TTC 500, HT 417, TVA 83, coût 100, bénéfice 317 |
| TVA 20 % | 1050 / 875 / 175 | 1050 / 875 / 175 | 500 / 417 / 83 |
| solde de caisse | 0 + 1050 − 0 = 1050 | 0 | 0 |
| offerts, recharges | vides | vides | vides (LG n'est pas FREE) |

La TVA du scénario 12 reste 417 / 83 dans l'ancien rapport (les jetons y comptent comme
avant), alors que la Vente porte HT 167, TVA 33 : c'est voulu, l'ancien rapport ne lit
pas la Vente (bascule en fiche G).

#### Tests (B-3d)

Vert au premier lancement (fiche §6 : « le 23 est vert avant et doit le rester ») :
`test_caisse_anciens_rapports.py` : 3 passed ; avec `test_caracterisation_caisse.py`,
`test_hors_argent_offerts.py`, `test_total_ht_ligne.py` : 33 passed. Aucune valeur
calculée à la main ne diffère du code actuel. Pas de preuve « avant le chantier » par
exécution (elle demanderait de remettre l'ancien `laboutik/views.py`, opération git
interdite) : la preuve est le calcul à la main depuis les formules de
`git show HEAD:laboutik/reports.py` et l'ancien `_creer_lignes_articles_cascade` /
`_calculer_qty_partielles` (inchangé).

#### Mutations proposées (B-3d)

Non jouées par l'ouvrier (à jouer par l'orchestrateur).
`sha256` avant : `laboutik/views.py` `b4a6adbd2dd0b2352cbe0661d5670bbd08a3c4b0ccb61ee86f6bc9818b11c552`,
`laboutik/reports.py` `dd86300159f22645c563a91feb6ff23855cfb327633f5689c2d94cb2d88f98f7`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| prix unitaire d'une part = argent de la part (`laboutik/views.py:6198`) | `prix_unitaire=prix_unitaire_en_centimes` → `prix_unitaire=argent_reel_de_la_part_en_centimes` | 9 (CB 864, cashless 714), 12 (CB 80, cashless 180) — la Vente reste juste (catalogue imposé) : seul l'ancien rapport le voit |
| quantité d'une part = quantité de l'article (`laboutik/views.py:6197`) | `quantite=quantite_de_la_part` → `quantite=Decimal(quantite)` | 9, 12 |
| quantité de la vente simple (`laboutik/views.py:5789`) | `quantite=quantite_vendue` → `quantite=Decimal(1)` | 1 |
| quantité partielle à 2 décimales (`laboutik/views.py:4787`) | `.quantize(SIX_DECIMALES)` → `.quantize(Decimal("0.01"))` | 9 (LE 350 × 1,43 = 500,5 → 501) |
| TVA d'une part en jetons (`laboutik/views.py:5588-5591`) | ajouter `PaymentMethod.LOCAL_GIFT,` au tuple hors vente en argent | 12 (TVA coupée en 0 % / 20 %, détail en deux articles) |
| complément CB écrit en espèces (`laboutik/views.py:10339`) | `PaymentMethod.CC` → `PaymentMethod.CASH` | 9, 12 (espèces et solde) |
| montant d'une ligne sans la quantité (`laboutik/reports.py:48`) | `F("amount") * F("qty")` → `F("amount")` | 1, 9, 12 |
| jetons retirés du cashless (`laboutik/reports.py:241`) | `[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT]` → `[PaymentMethod.LOCAL_EURO]` | 12 |
| jetons retirés des offerts du détail (`laboutik/reports.py:365`) | `[PaymentMethod.LOCAL_GIFT]` → `[]` | 12 |
| HT tronqué au lieu d'arrondi (`laboutik/reports.py:417`) | `int(round(total_ttc / …))` → `int(total_ttc / …)` | 12 (HT 416) |
| solde sans les espèces (`laboutik/reports.py:563`) | `fond_de_caisse + entrees_especes - sorties_especes` → `fond_de_caisse - sorties_especes` | 1 |

### Session B-3b-1 — vider une carte sur les DEUX Fedow / Emptying a card on BOTH Fedow servers

**Migration :** Non.

**Quoi / What :** « Vider carte » à la caisse vide la carte sur l'ancien Fedow (serveur
distant, `POST card/refund`) **puis** sur le Fedow local, et écrit une vente
`VIDAGE_CARTE`.
- Ancien Fedow d'abord, hors transaction de base. Lieu non relié, ou carte inconnue là-bas
  (réponse 404) : vidage local seul. Carte connue : toujours envoyée à `card/refund`,
  même sans solde (« vider et délier » → `VOID`, sinon `REFUND`), avec le tag de la carte
  primaire du caissier (la même pour les deux Fedow). Ancien Fedow en échec (refus,
  serveur injoignable) : rien n'est fait, message clair.
- Puis un seul `atomic` : vidage local, vente, `encaisser_vente` en dernier. Échec après
  un vidage distant : journal INCIDENT (montant d'argent repris là-bas, carte, uuid de
  toutes les transactions distantes, jetons cadeau compris), écran d'erreur, pas de 500.
- Espèces rendues = monnaie locale du lieu + FED, sur les deux Fedow. Jetons cadeau du
  lieu repris aussi en local (transaction REFUND vers le lieu), sans argent ni règlement.
- Vente `VIDAGE_CARTE` sans article : un règlement positif par remboursement d'argent
  (`LE` / `SF` ; local → `fedow_transaction_uuid`, distant → `reference_externe`), puis
  espèces −total ; Σ = 0. Carte avec seulement des jetons cadeau : aucune vente, aucune
  ligne « Refund ».
- La vidange se fait dès qu'un des deux Fedow a quelque chose à reprendre (carte vide en
  local mais pas sur l'ancien Fedow : seul l'ancien est vidé). Carte vide partout mais
  connue de l'ancien Fedow, « vider et délier » : déliée des deux côtés, sans vente.
- Lignes « Refund » (anciens lecteurs, jusqu'à H) : totaux des deux Fedow. Ligne FED =
  FED local + FED distant, avec le FED local s'il y en a, sinon l'uuid du FED distant (le
  cas de la production, où un FED local est interdit).
- Contexte de l'écran : totaux des deux Fedow ; détail séparé
  (`transactions_fedow_local`, `transactions_ancien_fedow`) pour l'écran et le reçu
  détaillés de B-3b-2. Gabarits inchangés.
/ One gesture empties the old Fedow (remote) first, then the local one, and writes a
`VIDAGE_CARTE` sale without items: one positive payment per money refund, then minus the
total in cash. Gift tokens are taken back on both sides, with no money. Old Fedow
failure: nothing done; local failure after it: INCIDENT logged.

**Pourquoi / Why :** système hybride : la vidange de la caisse V2 ne touchait que le
Fedow local (fiche B §5 « B-3b », règle validée par le mainteneur, décisions du
2026-09-29 ; `CHANTIER-05-SUIVI.md` §4 et §5). / Hybrid system: the register only
emptied the local Fedow.

| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | `NFCcardFedow.refund` : `POST card/refund` (`VID` / `RFD`), 205 attendu sinon exception, transactions validées (`TransactionValidator`) ; sans les écritures en base de LaBoutik V1 |
| `fedow_core/services.py` | `rembourser_en_especes` seulement : jetons cadeau (TNF) du lieu repris ; paramètres des montants de l'ancien Fedow (lignes des deux Fedow) ; `NoEligibleTokens` seulement si rien nulle part et rien à délier ; pas de ligne espèces sans argent ; asset de la ligne FED |
| `laboutik/views.py` | `_vider_la_carte_sur_l_ancien_fedow`, `_ecrire_la_vente_du_vidage` (après `_debiter_legacy`) ; `vider_carte` : ancien Fedow d'abord, puis un seul `atomic`, journal INCIDENT ; import de `CarteInconnueDeFedow` |
| `tests/pytest/test_caisse_vider_carte_deux_fedow.py` | nouveau : 14 tests (22 cas) ; ancien Fedow simulé, garde contre tout appel réseau réel |
| `tests/pytest/test_card_refund_service.py` | test réécrit (voir plus bas) |
| `tests/pytest/test_pos_vider_carte.py`, `tests/pytest/test_remboursement_especes_trace_comptable.py` | tests de route en `django_db`, lieu non relié simulé (voir plus bas) |

Nouvelles chaînes i18n (2) : « L'ancien Fedow n'a pas pu vider la carte. Rien n'a été
fait : réessayez. » ; « La carte est vidée sur l'ancien Fedow, mais pas en local.
Incident enregistré : prévenez un responsable. »

#### Tests existants réécrits / Rewritten existing tests (B-3b-1)

- `test_card_refund_service.py::test_rembourser_exclut_tnf_tim_fid` → renommé
  `test_rembourser_reprend_les_jetons_cadeau_du_lieu_et_exclut_tim_fid`. Raison : décision
  du mainteneur, les jetons cadeau du lieu sont repris aussi en local (sans argent). Le
  test vérifie la reprise (solde 0, une REFUND), aucun argent (total 0, aucune ligne), et
  que le temps (TIM) et les points (FID) restent sur la carte (vérifié : ils étaient déjà
  exclus avant, ils le restent).
- `test_pos_vider_carte.py::test_vider_carte_execute_remboursement_complet`,
  `test_pos_vider_carte.py::test_vider_carte_execute_avec_vv`,
  `test_remboursement_especes_trace_comptable.py::test_vider_une_carte_depuis_la_caisse_ecrit_les_deux_lignes`
  : (1) lieu non relié à l'ancien Fedow simulé (`FedowConfig.can_fedow` → False) — en
  base de dev le lieu est relié, et la vraie route appellerait le vrai ancien Fedow ;
  (2) marqués `django_db` — la route écrit maintenant une vente scellée, qu'aucun
  nettoyage à la main ne peut supprimer (PROTECT). Leurs fixtures de carte, de carte
  primaire et de point de vente sautent le nettoyage à la main quand le test est marqué
  (le rollback efface tout). Valeurs attendues inchangées.

**Incident pendant la session :** un premier lancement de ces trois tests, avant (2), a
laissé en base de dev deux ventes scellées (n° 31, 32), leurs cartes, et une monnaie FED
locale `[rbt_trace]` (nettoyage de fin de module bloqué). Nettoyé par un script jetable
hors dépôt (passage à blanc validé par le mainteneur, puis `--appliquer`) : numéro
maximum des ventes de lespass revenu à 30, plus de FED local. Deux lancements successifs
des fichiers de vidage ne laissent plus rien.

#### Tests vus échouer / Tests seen failing (B-3b-1)

Rouge d'abord (avant le code ; rejoué par l'orchestrateur : 15 failed) :
```
:535: AssertionError: Attendu : une vente de vidage pour la carte …, trouvé : 0.   (20, 20f ×2)
:733: assert 200 == 0                                                              (20b)
:817 / :961 / :1077: assert 0 == 1  (card/refund jamais appelé)                     (20c, 20e, 20g ×2)
:603: 'data-testid="alerte-messages"' absent (écran de succès)                      (20d ×2)
mock.py:1183: RuntimeError: Vidage local en échec (simulé par le test).            (20e)
:1201: AttributeError: 'NFCcardFedow' object has no attribute 'refund'             (20g bis ×2)
:1254: assert 0 == 1  (aucun envoi)                                                  (20g ter)
:1290: assert [('CA', -800), ('SF', 300)] == [… STRIPE_FED 400 …]                   (20h)
```
Ajoutés après les décisions du mainteneur, vus rouges avant leur code :
20i `test_vider_carte_vide_en_local_avec_solde_ancien_fedow` (écran d'erreur),
20j `test_vider_carte_seulement_jetons_cadeau_aucune_vente` (écran d'erreur),
20k `test_vider_carte_fed_seulement_sur_l_ancien_fedow_ligne_fed_avec_uuid_distant`
(`[('CA', -500)]`), 20l `test_vider_et_delier_une_carte_vide_partout_la_delie_des_deux_cotes`
(écran d'erreur).
20g ter (`test_client_card_refund_reponse_en_erreur_leve_une_exception`) paramétré après
coup sur 400 (deux corps réels du validateur de l'ancien Fedow, en JSON), 404 et 500
(corps HTML) : il exige le code de la réponse dans le message de l'exception. Vert sur
le code ; il tue la mutation « `!= 205` → `not in (205, 400)` », qui survivait (sous
elle, le 400 levait quand même une exception, plus loin, à la lecture des transactions).

Vert : fichiers de vidage (`test_caisse_vider_carte_deux_fedow.py`,
`test_pos_vider_carte.py`, `test_remboursement_especes_trace_comptable.py`,
`test_card_refund_service.py`) : 47 passed, deux fois de suite, sans reste en base ;
`test_caisse_ecrit_la_vente.py` + 22 de caractérisation (sans modification) : 86 passed ;
`manage.py check` : aucun problème ; `makemigrations --check --dry-run` : « No changes
detected ».

#### Mutations (B-3b-1)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). `sha256` avant :
`laboutik/views.py` `e8e8f2c075c7302e27c2bc7a8b33833c3c47cc22dc4ba80f3c37ba7dbbc7e577`,
`fedow_core/services.py` `fcf6105430efb656932d28f208caaf4a4830b5e0136fceb1dd9c845938ab2c65`,
`fedow_connect/fedow_api.py` `c22bf339c22fe5a832237fa1ab4339076fc306e39bbc482fe7f213bf775cffdf`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| ordre : local avant l'ancien Fedow (`laboutik/views.py:12198-12203`) | bloc `try: reponse_de_l_ancien_fedow = …` déplacé après le bloc `atomic` (et ses totaux avec) | 20c (état local au moment de l'appel ≠ `(0, 500)`), 20d (jetons locaux vidés), 20h |
| échec distant ignoré (`laboutik/views.py:12203-12213`) | `return _render_erreur_toast(…)` → `reponse_de_l_ancien_fedow = None` | 20d ×2 |
| injoignable pris pour inconnue (`laboutik/views.py:1722`) | `except CarteInconnueDeFedow:` → `except Exception:` | 20d [serveur_injoignable] |
| carte connue sans solde non envoyée (`laboutik/views.py:1724`) | `reponse_du_vidage = fedow_api.NFCcard.refund(` précédé de `if not …: return []` sur un solde lu | 20l (VOID non envoyé) |
| lieu non relié : `FedowAPI` créé quand même (`laboutik/views.py:1716-1719`) | les deux premières lignes échangées (`fedow_api = FedowAPI()` d'abord) | 20f [lieu_non_relie] |
| `VOID` jamais envoyé (`laboutik/views.py:1728`) | `void=vider_et_delier` → `void=False` | 20g [True], 20l |
| carte primaire du client (`laboutik/views.py:12200`) | `carte_primaire_obj.carte.tag_id` → `carte_client.tag_id` | 20g ×2 |
| client : action inversée (`fedow_connect/fedow_api.py:828/830`) | `VOID` ↔ `REFUND` | 20g bis ×2 |
| client : pas d'exception hors 205 (`fedow_connect/fedow_api.py:843`) | `!= 205` → `not in (205, 400)` | 20g ter [400 ×2] (l'exception vient de la lecture des transactions, sans le code 400 dans son message) |
| client : tags non mis en majuscules (`fedow_connect/fedow_api.py:833`) | `.upper()` retiré | 20g bis ×2 |
| jetons cadeau locaux non repris (`fedow_core/services.py:618`) | ligne `| Q(asset__category=Asset.TNF, …)` retirée | 20b, 20j, `test_rembourser_reprend_les_jetons_cadeau…` |
| jeton cadeau compté comme argent (`fedow_core/services.py:665`) | `elif token.asset.category == Asset.FED:` → `else:` | 20b (espèces −700), 20j (ligne espèces), test du service |
| règlement pour un jeton cadeau (`laboutik/views.py:1840-1842`) | `else: continue` → `else: moyen_du_reglement = PaymentMethod.LOCAL_GIFT` | 20c (règlement LG en trop), 20h |
| signe des règlements (`laboutik/views.py:1892`) | `-argent_rendu_en_centimes` → `argent_rendu_en_centimes` | 20, 20b, 20c, 20f, 20i (Σ ≠ 0 : `EgaliteDeVenteRompue`) |
| local → `reference_externe` (`laboutik/views.py:1884`) | `fedow_transaction_uuid=uuid_de_la_transaction_locale` → `=None` | 20, 20b, 20c, 20f |
| distant → `fedow_transaction_uuid` (`laboutik/views.py:1885`) | `reference_externe=reference_distante` → `""` | 20c, 20i |
| vente pour une carte sans argent (`laboutik/views.py:1858`) | `== 0` → `< 0` | 20j, 20l (vente sans règlement : exception) |
| `encaisser_vente` retiré (`laboutik/views.py:12283`) | ligne retirée | 20, 20c (vente `EN_ATTENTE`), 20e [a_l_encaissement] (aucune exception) |
| journal INCIDENT retiré (`laboutik/views.py:12299`) | ligne retirée | 20e ×2 |
| INCIDENT sans les uuid (`laboutik/views.py:12249`) | `{', '.join(uuids…)}` → `""` | 20e ×2 |
| vidage local seul bloqué (`fedow_core/services.py:633`) | `if rien_a_reprendre_nulle_part and not …:` → `if not tokens_eligibles:` | 20i, 20l |
| carte vide partout non déliée (`fedow_core/services.py:632`) | `vider_carte and carte_videe_sur_l_ancien_fedow` → `False` | 20l |
| lignes : FED distant oublié (`fedow_core/services.py:670`) | `+ total_fed_ancien_fedow_centimes` retiré | 20h, 20k |
| lignes : monnaie locale distante oubliée (`fedow_core/services.py:674`) | ligne retirée | 20h (espèces −900) |
| asset de la ligne FED sans FED local (`fedow_core/services.py:701`) | `uuid_fed_ancien_fedow` → `None` | 20k |
| asset de la ligne FED avec FED local (`fedow_core/services.py:699`) | `fed_asset.uuid` → `uuid_fed_ancien_fedow` | 20h |
| ligne espèces à 0 écrite (`fedow_core/services.py:728`) | `> 0` → `>= 0` | 20j, test du service |

### Session B-3b-2 — vider une carte : aperçu, écran et reçu séparés par Fedow / Emptying a card: preview, screen and receipt split by Fedow

**Migration :** Non.

**Quoi / What :** l'aperçu, l'écran de succès et le reçu imprimé d'un vidage de carte
sont séparés et détaillés : une partie « Fedow local », une partie « Ancien Fedow », une
ligne par monnaie reprise (jetons cadeau compris, « repris, sans argent »), puis le total
rendu en espèces.
- Aperçu : l'ancien Fedow est lu SANS rien débiter (`NFCcard.retrieve`, GET
  `card/{tag_id}/`), avec le même filtre que `card/refund` (monnaie fédérée, monnaie
  locale et jetons cadeau créés par le lieu). Lieu non relié ou carte inconnue : pas de
  partie « Ancien Fedow ». Ancien Fedow injoignable : l'aperçu le dit. L'aperçu accepte
  les mêmes cartes que la vidange : carte vide en local mais pas sur l'ancien Fedow,
  carte avec seulement des jetons cadeau, carte vide partout mais connue de l'ancien
  Fedow (seul « réinitialiser » est proposé). Il montre aussi les jetons cadeau locaux.
- Reçu : le navigateur ne poste que des uuid. Le Fedow local est relu en base ;
  l'ancien Fedow par uuid (`transaction.retrieve`), en ne gardant que les
  remboursements reçus par le portefeuille du lieu (un uuid inconnu, d'un autre lieu,
  d'une vente, mal formé ou en double est ignoré). Ancien Fedow injoignable à
  l'impression : impression refusée, jamais de reçu partiel.
/ Preview, success screen and receipt are split by Fedow, one line per currency, gift
tokens "taken back, no money", then the cash given back. The preview reads the old Fedow
without debiting. The receipt only receives uuids and re-reads every transaction.

**Pourquoi / Why :** décision 3 du mainteneur (fiche B §5, « B-3b ») : écran et reçu
séparés et détaillés ; décision (a) : une carte vide en local mais avec un solde sur
l'ancien Fedow se vide ; décisions de l'orchestrateur (SUIVI §4) sur la source du reçu.
/ Maintainer decisions: split, detailed screen and receipt.

**Corrigé en passant (défaut antérieur) / Fixed along the way (earlier defect) :** le reçu
de vidage imprimait des lignes sans montant (« 1 x Monnaie locale (Remboursement) »), sans
nom ni adresse du lieu, et un total qui comptait les jetons cadeau
(`formatter_recu_vider_carte` écrivait `prix_centimes` / `total_centimes` et
`organisation` / `adresse`, clés que les imprimantes ne lisent pas). Il imprime
maintenant le montant de chaque ligne, le nom, l'adresse et le SIREN du lieu
(`Configuration.siren`, comme le ticket de vente), et un total égal à l'argent rendu.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_ligne_de_vidage`, `_lire_la_carte_sur_l_ancien_fedow` (aperçu), `_relire_les_transactions_de_l_ancien_fedow` (reçu) ; `vider_carte_preview` et `vider_carte_imprimer_recu` réécrites ; contexte de `vider_carte` (lignes par Fedow, uuid des transactions distantes) ; `_vider_la_carte_sur_l_ancien_fedow` garde le nom et le code de chaque monnaie |
| `laboutik/printing/formatters.py` | `formatter_recu_vider_carte` réécrite : parties par Fedow, clés lues par les imprimantes, total = argent rendu |
| `laboutik/printing/escpos_builder.py`, `laboutik/printing/sunmi_inner.py` | une ligne `texte_seul` (titre de partie, ligne sans argent) s'imprime seule, sans « 1 x » |
| `laboutik/templates/laboutik/partial/hx_vider_carte_parties.html` | nouveau : les deux parties, incluses par l'aperçu et l'écran de succès |
| `laboutik/templates/laboutik/partial/hx_vider_carte_confirm.html` | parties par Fedow, avertissement « ancien Fedow injoignable », « garder le compte » seulement s'il y a quelque chose à reprendre |
| `laboutik/templates/laboutik/partial/hx_vider_carte_success.html` | parties par Fedow ; le formulaire du reçu poste aussi les uuid de l'ancien Fedow |
| `tests/pytest/test_caisse_vider_carte_deux_fedow.py` | 15 tests ajoutés (20m à 20z bis, 16 cas) |
| `tests/e2e/test_parcours_fedow_reel.py` | deux E2E réels de vidage (monnaie locale, FED par Stripe) et la fixture `carte_primaire_declaree_a_l_ancien_fedow` |

Nouvelles chaînes i18n (6) : « Fedow local » ; « Ancien Fedow » ; « repris, sans
argent » ; « Repris » ; « L'ancien Fedow ne répond pas : son solde n'est pas affiché. La
carte ne pourra pas être vidée tant qu'il ne répond pas. » ; « L'ancien Fedow ne répond
pas : le reçu n'est pas imprimé. Réessayez plus tard. ». « Rendu en espèces » existait
déjà (gabarit), elle sert aussi au reçu.

#### E2E réels contre l'ancien Fedow / Real E2E against the old Fedow

`test_caisse_vide_une_carte_avec_de_la_monnaie_locale_de_l_ancien_fedow` (sans Stripe) et
`test_caisse_vide_une_carte_avec_du_fed_de_l_ancien_fedow` (`stripe_listen`). Chacun :
adhérent neuf crédité (monnaie locale du lieu, ou FED acheté par Stripe), carte NEUVE
créée sur l'ancien Fedow et liée à l'adhérent des deux côtés, aperçu (partie « Ancien
Fedow » affichée), vidage « rembourser et réinitialiser » par les vraies routes avec la
carte primaire de la caisse V2 ; puis : solde distant à 0 (relu sans cache), une vente
`VIDAGE_CARTE` `REGLEE` sans article, un règlement `LE` (ou `SF`) +montant dont la
`reference_externe` est une transaction qui EXISTE sur l'ancien Fedow (action `RFD`, même
montant, bonne monnaie, du portefeuille de l'adhérent vers celui du lieu), espèces
−montant, Σ = 0.

Premier essai, avant B-3b-3 : l'ancien Fedow refusait la carte primaire
(`400 {"non_field_errors":["Primary card must be in place primary cards"]}`, `A49E8E2A`
lue `is_primary: False`). Après B-3b-3 (la carte déclarée), les deux passent.

La fixture `carte_primaire_declaree_a_l_ancien_fedow` lit l'état de la carte primaire du
seed sur l'ancien Fedow (`is_primary`, lecture sans cache), la déclare
(`declarer_la_carte_primaire_a_l_ancien_fedow`, 208 normal), et à la fin remet l'état
trouvé : retirée si elle n'était pas primaire, pas touchée sinon.

Sorties (`stripe listen` tourne, vers le Fedow et vers Lespass) :
```
make e2e ARGS="tests/e2e/test_parcours_fedow_reel.py -k caisse_vide -v"   (1er passage)
2 passed, 5 deselected, 2 warnings in 27.88s
make e2e ARGS="tests/e2e/test_parcours_fedow_reel.py -k caisse_vide -v"   (2e passage)
2 passed, 5 deselected, 2 warnings in 22.38s
make e2e ARGS="tests/e2e/test_parcours_fedow_reel.py -v"
7 passed, 2 warnings in 67.57s (0:01:07)
```
Après les passages, `A49E8E2A` est lue `is_primary: True` sur l'ancien Fedow (elle l'était
au départ). La branche « retirer » de la fixture a été éprouvée ensuite par
l'orchestrateur : carte retirée de l'ancien Fedow avant le lancement, deux E2E verts, carte
lue `is_primary: False` après (état trouvé remis), puis déclarée de nouveau
(`is_primary: True`).

Ce que les E2E laissent : par passage et par test, un adhérent neuf et une carte neuve
(sur le lieu et sur l'ancien Fedow), vidée et déliée ; une vente de vidage encaissée,
numérotée et chaînée (en base de dev : ventes 31 à 34, 37 et 38) ; pour le test FED, un
paiement Stripe de test de 3 €. Le premier essai, avant B-3b-3, a laissé un adhérent
crédité de 5,00 € et une carte neuve liés (aucune vente).

Mutations proposées pour les E2E (non jouées) :

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| carte primaire du client (`laboutik/views.py:12444`) | `carte_primaire_obj.carte.tag_id` → `carte_client.tag_id` | les deux E2E (`card/refund` refusé, écran d'erreur) |
| référence distante perdue (`laboutik/views.py:1900`) | `reference_externe=reference_distante` → `reference_externe=""` | les deux E2E (aucune transaction distante relue) |
| mauvais portefeuille à l'aperçu (`laboutik/views.py:1981`) | `fedow_place_wallet_uuid` → `fedow_place_uuid` | E2E monnaie locale (partie « Ancien Fedow » absente de l'aperçu) |
| vente non encaissée (`laboutik/views.py:12527`) | ligne retirée | les deux E2E (vente `EN_ATTENTE`) |

#### Tests vus échouer / Tests seen failing (B-3b-2)

Rouge d'abord (avant le code ; rejoué par l'orchestrateur : 9 failed, puis 13 failed) :
```
:2098 aucune partie « Fedow local » (aperçu séparé, 20m)
:2158 toast « Aucun solde remboursable » (carte vide en local, 20n)
:1696 aucune ligne locale (20o ×2)
:2244 avertissement « injoignable » absent (20p)
:2273 aucune partie locale (succès, 20q)
:1983 aucune partie « ancien Fedow » sur le reçu (20r) — reçu réel : « 1 x Monnaie locale (Remboursement) … TOTAL: 7.00 EUR »
:2397 le formulaire ne porte pas les uuid distants (20s)
:1953 aucune impression (20t)
:2513 impression demandée malgré l'ancien Fedow injoignable (20u)
:2547 ni nom ni adresse du lieu sur le reçu (20v)
:2581 / :2629 toast « Aucun solde remboursable » (20w, 20x)
```
Vert : `test_caisse_vider_carte_deux_fedow.py` 38 passed ; fichiers de vidage (avec
`test_pos_vider_carte.py`, `test_remboursement_especes_trace_comptable.py`,
`test_card_refund_service.py`) 63 passed avant les trois derniers tests ;
`test_caisse_ecrit_la_vente.py` + 22 de caractérisation : 86 passed ; tests d'impression
(6 fichiers) : 159 passed ; `manage.py check` : aucun problème ; `makemigrations --check
--dry-run` : « No changes detected ».

#### Mutations (B-3b-2)

Jouées par l'ouvrier pour les quatre dernières (fichiers restaurés, `sha256` vérifiés) ;
les autres, non jouées. `sha256` de référence : `laboutik/views.py` `f09df4e2…cdfb33`,
`laboutik/printing/formatters.py` `ee210cbd…500311`, `escpos_builder.py` `b7edc352…66ee654`,
`sunmi_inner.py` `c7b9ad20…c8549`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| destinataire non vérifié (`laboutik/views.py:2063`) | ligne `if str(receiver) != portefeuille_du_lieu: continue` retirée | 20s (77.77 imprimé) |
| panne à l'impression ignorée (`laboutik/views.py:12660`) | `except` : `return …` → `transactions_ancien_fedow = []` | 20u |
| monnaie d'un autre lieu (`laboutik/views.py:1987-1990`) | `… or (categorie in (TLF, TNF) and monnaie_du_lieu)` → `… or categorie in (TLF, TNF)` | 20m |
| lieu non relié (`laboutik/views.py:1967`) | garde `can_fedow()` retirée | 20o [lieu_non_relie] |
| carte vide connue refusée (`laboutik/views.py:12340`) | `and not carte_connue_de_l_ancien_fedow` retiré | 20x |
| jetons cadeau comptés à l'aperçu (`laboutik/views.py:12350`) | `if ligne.est_de_l_argent_rendu:` → toujours vrai | 20m, 20w |
| « garder le compte » sans rien à reprendre (`hx_vider_carte_confirm.html:72`) | `carte.user and il_y_a_quelque_chose_a_reprendre` → `carte.user` | 20x |
| uuid distants non postés (`hx_vider_carte_success.html:47`) | boucle retirée | 20s, 20r, 20t |
| total avec jetons cadeau (`laboutik/printing/formatters.py:818`) | `(TLF, FED)` → `(TLF, FED, TNF)` | 20r, 20s |
| clé du nom du lieu (`laboutik/printing/formatters.py:776`) | `"business_name"` → `"organisation"` | 20v |
| clé du montant (`laboutik/printing/formatters.py:823`) | `"price"` → `"prix_centimes"` | 20r, 20s, 20t |
| **joué** — filtre sur l'action (`laboutik/views.py:2061-2062`) | lignes retirées | 20y (`'33.33' not in …`) |
| **joué** — dédoublonnage (`laboutik/views.py:2037-2038`) | lignes retirées | 20z (deux lignes « Euro du lieu (ancien) ») |
| **joué** — texte seul ESC/POS (`laboutik/printing/escpos_builder.py:151`) | `if article.get("texte_seul"):` → `if False and …` | 20z bis (`'1 x FEDOW LOCAL'`) |
| **joué** — texte seul Sunmi (`laboutik/printing/sunmi_inner.py:97`) | idem | 20z bis (`'1 x FEDOW LOCAL'`) |

### Session B-3b-3 — la carte primaire déclarée à l'ancien Fedow / Primary card declared to the old Fedow

**Migration :** Non.

**Quoi / What :** la même carte primaire sert aux deux Fedow. Comme dans LaBoutik V1,
elle est déclarée à l'ancien Fedow quand elle est créée (`POST card/set_primary`,
`delete=False`), et retirée quand elle est supprimée (`delete=True`). Seulement si le
lieu est relié à l'ancien Fedow (`FedowConfig.can_fedow()`), et en synchrone.
- **Des appels explicites, pas un signal** (écart avec V1, validé par le mainteneur) :
  - le formulaire d'ajout de l'admin (`clean()`) lit d'abord la carte sur l'ancien
    Fedow, puis la déclare ;
  - la suppression de l'admin, unitaire (`delete_model`) et groupée
    (`delete_queryset`) ;
  - `create_test_pos_data`, quand il crée la carte primaire du simulateur ;
  - une commande de rattrapage.
- **Refus à l'ajout** (400, 500) : erreur en tête du formulaire, avec le code ; rien
  n'est créé en local.
- **Carte inconnue de l'ancien Fedow** : refus avec « créez-la d'abord dans l'admin des
  cartes ». La carte est lue avant d'être déclarée : sans cela, le serveur répond une
  erreur 500 opaque.
- **Retrait refusé** : la suppression locale est gardée (la carte n'ouvre plus la
  caisse) ; un message d'erreur nomme le tag et le code.
- **Modification** : la carte NFC passe en lecture seule ; le mode gérant et les points
  de vente n'appellent pas l'ancien Fedow.
- **« Vider et délier »** à la caisse n'appelle rien : le VOID de l'ancien Fedow retire
  déjà lui-même le lien primaire.
- **Commande de rattrapage** `declarer_cartes_primaires_ancien_fedow --schema <lieu>` :
  passage à blanc par défaut (liste, n'envoie rien), `--appliquer` déclare chaque carte
  une fois (208 = déjà déclarée) ; un refus n'arrête pas les autres cartes.
/ The same primary card serves both Fedow servers. It is declared to the old Fedow when
created and withdrawn when deleted (linked venue only), by explicit calls, not a signal.
A refusal is shown to the admin and nothing is created. Unknown cards are refused with
a clear message. A catch-up command declares existing primary cards.

**Pourquoi / Why :** l'ancien Fedow refusait la vidange signée par la carte primaire de
la caisse V2 (`card/refund` → 400 « Primary card must be in place primary cards ») : elle
n'y était pas déclarée. Décision du mainteneur, 2026-09-29 (`CHANTIER-05-SUIVI.md` §5).
/ The old Fedow refused emptying signed by the V2 register's primary card.

| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | `NFCcardFedow.set_primary(tag_id, delete=False)` : `POST card/set_primary`, `delete` en vrai booléen ; 200 / 205 / 208 acceptés, sinon exception avec le code |
| `laboutik/carte_primaire_ancien_fedow.py` (nouveau) | `declarer_la_carte_primaire_a_l_ancien_fedow` (lecture puis déclaration), `retirer_la_carte_primaire_de_l_ancien_fedow` ; lieu non relié : rien, `FedowAPI` non créé |
| `Administration/admin/laboutik.py` | `CartePrimaireAdminForm` (déclaration dans `clean()` à l'ajout) ; `get_readonly_fields` (carte en lecture seule en modification) ; `delete_model`, `delete_queryset` ; fonction de module `_retirer_la_carte_primaire_et_prevenir_le_gestionnaire` |
| `laboutik/management/commands/create_test_pos_data.py` | déclare la carte primaire du simulateur quand elle est créée ; refus écrit en rouge, sans planter |
| `laboutik/management/commands/declarer_cartes_primaires_ancien_fedow.py` (nouveau) | commande de rattrapage (`--schema`, `--a-blanc`, `--appliquer`) |
| `tests/pytest/test_carte_primaire_ancien_fedow.py` (nouveau) | 28 tests (voir plus bas) |

Nouvelles chaînes i18n (3), msgid en français : « La carte %(tag)s est inconnue de
l'ancien Fedow : créez-la d'abord dans l'admin des cartes. » ; « L'ancien Fedow a refusé
la carte primaire %(tag)s, elle n'a pas été créée. Détail : %(detail)s » ; « Carte
primaire %(tag)s supprimée ici, mais l'ancien Fedow a refusé de la retirer. Détail :
%(detail)s ». Workflow i18n à lancer par le mainteneur.

Tests existants : aucun modifié.

**Passage à blanc sur `lespass`** (aucun envoi) :
```
Lieu lespass : 2 carte(s) primaire(s). Relié à l'ancien Fedow : oui.
  - A49E8E2A (n° A49E8E2A)
  - RCT00001 (n° RCT00001)
Passage à blanc : rien n'est envoyé. Relancer avec --appliquer.
```
`RCT00001` est une carte primaire laissée par un test sans `django_db`
(`test_retour_carte_recharge.py`) ; probablement inconnue de l'ancien Fedow : un
`--appliquer` la dira « INCONNUE » sans arrêter la déclaration de `A49E8E2A`.
`--appliquer` n'a pas été lancé (feu vert de l'orchestrateur attendu).

#### Tests vus échouer / Tests seen failing (B-3b-3)

Rouge (avant le code ; rejoué par l'orchestrateur : 22 failed, 4 passed) :
```
ajout déclare                 assert [] == [('A5EF16D6', False)]
ajout refusé 400 / 500        reçu 302 : la carte primaire a été enregistrée
carte inconnue                reçu 302 : la carte primaire a été enregistrée
déjà déclarée (208)           assert [] == ['card/set_primary']
carte changée en modification assert 25721 == 25720
suppression / groupée         assert [] == [('DD251BB9', True)] / deux retraits absents
retrait refusé                aucun message d'erreur rendu
create_test_pos_data          assert [] == [('A49E8E2A', False)]
rattrapage ×3                 CommandError: Unknown command: 'declarer_cartes_primaires_ancien_fedow'
client set_primary ×9         'NFCcardFedow' object has no attribute 'set_primary'
```
Les 4 verts du rouge sont des gardes voulues (lieu non relié à l'ajout et à la
suppression, modification du mode gérant, « vider et délier »). Deux tests sont ajoutés
après le code : le libellé français de la carte inconnue (décision du mainteneur) et la
commande dans un lieu non relié (pour la mutation « garde retirée »).

Vert : `test_carte_primaire_ancien_fedow.py` : 28 passed ; avec les tests de caisse
(`test_caisse_*.py`, 5 fichiers), de vidage (`test_caisse_vider_carte_deux_fedow.py`,
`test_pos_vider_carte.py`, `test_remboursement_especes_trace_comptable.py`),
`test_pos_models.py` et les 22 de caractérisation (sans modification) : 203 passed ; `manage.py check` : aucun problème ;
`makemigrations --check --dry-run` : « No changes detected ». Base de dev inchangée
(cartes primaires : `A49E8E2A`, `RCT00001`).

#### Mutations (B-3b-3)

Non jouées par l'ouvrier (à jouer par l'orchestrateur). `sha256` avant :
`fedow_connect/fedow_api.py` `f1de685e…a03fe74a` ;
`laboutik/carte_primaire_ancien_fedow.py` `e5c6539d…c9165707` ;
`Administration/admin/laboutik.py` `382a954b…c46d71d8` ;
`create_test_pos_data.py` `f458b614…2d29c8d093` ;
`declarer_cartes_primaires_ancien_fedow.py` `20362d7e…cd48a2b8`.

| Mutation (fichier:ligne) | Avant → après | Doit faire tomber |
|---|---|---|
| 400 accepté (`fedow_connect/fedow_api.py:909`) | `[200, 205, 208]` → `[200, 205, 208, 400]` | client [400] |
| `delete` figé (`fedow_connect/fedow_api.py:901`) | `"delete": delete` → `"delete": False` | client [True-205] |
| `delete` en chaîne (`fedow_connect/fedow_api.py:901`) | `delete` → `str(delete)` | client ×2 (`is retirer`) |
| mauvaise route (`fedow_connect/fedow_api.py:906`) | `'card/set_primary'` → `'card/set_primaire'` | client ×2, 208 à l'ajout |
| garde « lieu relié » retirée à la déclaration (`laboutik/carte_primaire_ancien_fedow.py:57-58`) | `if not …: return False` retiré | ajout lieu non relié |
| lecture préalable retirée (`laboutik/carte_primaire_ancien_fedow.py:61`) | ligne `retrieve` retirée | carte inconnue ×2 |
| déclaration en retrait (`laboutik/carte_primaire_ancien_fedow.py:62`) | `delete=False` → `delete=True` | ajout déclare, rattrapage appliqué |
| garde « lieu relié » retirée au retrait (`laboutik/carte_primaire_ancien_fedow.py:81-82`) | `if not …: return False` retiré | suppression lieu non relié |
| retrait en déclaration (`laboutik/carte_primaire_ancien_fedow.py:85`) | `delete=True` → `delete=False` | suppression, suppression groupée |
| déclaration aussi en modification (`Administration/admin/laboutik.py:815`) | `if not carte_primaire_en_creation:` → `if False:` | modifier le mode gérant |
| déclaration retirée (`Administration/admin/laboutik.py:825`) | appel → `pass` | ajout déclare, refus 400 / 500, carte inconnue |
| carte inconnue non distinguée (`Administration/admin/laboutik.py:827-835`) | bloc `except CarteInconnueDeFedow` retiré | libellé français |
| code absent du message (`Administration/admin/laboutik.py:842-848`) | `"detail": str(…)` → `"detail": ""` | refus 400 / 500 |
| carte modifiable (`Administration/admin/laboutik.py:958`) | `append('carte')` retiré | carte changée en modification |
| retrait oublié (`Administration/admin/laboutik.py:966-968`) | appel retiré de `delete_model` | suppression |
| retrait groupé oublié (`Administration/admin/laboutik.py:976-978`) | boucle retirée de `delete_queryset` | suppression groupée |
| refus du retrait avalé (`Administration/admin/laboutik.py:875`) | `messages.error(…)` → `pass` | retrait refusé |
| `create_test_pos_data` ne déclare plus (`laboutik/management/commands/create_test_pos_data.py:1253`) | `if carte_primaire_cm_creee:` → `if False:` | create_test_pos_data |
| passage à blanc qui envoie (`declarer_cartes_primaires_ancien_fedow.py:92`) | `if not options["appliquer"]:` → `if False:` | rattrapage à blanc |
| garde « lieu relié » retirée (`declarer_cartes_primaires_ancien_fedow.py:88-90`) | bloc retiré | rattrapage lieu non relié (« rien à déclarer ») |
| un refus arrête tout (`declarer_cartes_primaires_ancien_fedow.py:114-119`) | `except Exception` : ajouter `raise` | rattrapage après un refus |

### Session B-3f — `test_cloture_caisse.py` en schéma dédié / Closure tests in a dedicated schema

**Migration :** Non. Aucun code de production.

**Quoi / What :** `tests/pytest/test_cloture_caisse.py` tourne dans son propre lieu de
test (`FastTenantTestCase`, schéma `test_cloture_caisse`) au lieu de la base partagée
`lespass`. Mêmes 7 scénarios, mêmes assertions. Le comptoir, le produit, son tarif et
l'admin sont créés dans `setUp` ; `create_test_pos_data` n'est plus appelé. Chaque test
annule sa transaction : ni clôture, ni ligne de vente, ni table, ni commande n'arrive
plus dans `lespass`.
/ The closure tests run in their own test venue instead of the shared `lespass` base.
Same scenarios, same assertions. Each test rolls back: nothing reaches the dev base.

**Pourquoi / Why :** la clôture couvre tout le lieu depuis la dernière clôture du point
de vente. Sur `lespass`, elle comptait les sorties d'espèces (lignes CASH négatives)
laissées par les E2E réels de vidage : `test_cloture_totaux_corrects` tombait
(`assert 200 >= 500`). Le tronc §8.5 impose un schéma dédié à tout test qui lit une
clôture. Décision du mainteneur, 2026-09-30.
/ On the shared base the closure counted cash exits left by real emptying E2E tests.

| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_cloture_caisse.py` | 7 classes sur `lespass` → 1 classe `FastTenantTestCase`, 7 tests ; `TenantClient` + `force_login` au lieu d'`APIClient` sur `lespass` |

#### Tests existants réécrits / Rewritten existing tests (B-3f)

Assertions devenues exactes (le lieu ne contient que les ventes du test) :

| Test | Avant | Après |
|---|---|---|
| `test_cloture_totaux_corrects` | `>= 500`, `>= 1000`, `>= 2000`, `>= 3500` | `== 500`, `== 1000`, `== 2000`, `== 3500` |
| `test_cloture_nombre_transactions` | `nombre_transactions >= 3` | `== 3` |
| `test_cloture_datetime_ouverture_auto` | `nombre_transactions >= 1` | `== 1` |
| `test_double_cloture_meme_periode` | `apres >= avant + 2` | `apres == avant + 2` |

Les trois autres (tables libérées, 15 clés du rapport, commande annulée) sont inchangés.

#### Vérifications (B-3f)

- Fichier seul : 7 passed, deux fois de suite (le premier lancement crée le schéma).
- Avec `test_cloture_*.py` (4 fichiers) et les 22 de caractérisation : 54 passed.
- Mutation jouée dans le test puis retirée : une sortie d'espèces de -300 ajoutée à
  `test_cloture_totaux_corrects` → `assert 200 == 500` (la signature du rouge).
- Base de dev : clôtures, lignes de vente, `ProductSold` / `PriceSold`, tables,
  commandes, total perpétuel et comptes identiques avant / après le fichier lancé seul
  (`pytest --api-key dummy`, pour que le conftest ne crée pas sa clé API de test).
  Le schéma dédié reste vide après le run (0 clôture, 0 ligne).

Constat hors périmètre : `test_cloture_enrichie.py` tourne encore sur `lespass` et y
supprime TOUTES les clôtures (`_nettoyer_clotures_et_perpetuel`) ; `lespass` est passé
de 26 à 2 clôtures pendant le lancement groupé. Candidat au même traitement (§8.5).

### Session B-4 — corrections de la relecture de la fiche B / Fixes from the sheet B review

**Migration :** Non.

**Quoi / What :**
1. Paiement NFC dont la monnaie du réseau est déjà débitée : toute exception imprévue
   dans le bloc atomic (erreur du service, contrainte de la base…) journalise désormais
   l'INCIDENT (montant, carte, uuid de chaque transaction du réseau, exception), puis
   remonte (500 volontaire). Même filet que le complément et la 2ᵉ carte.
2. Vider une carte : si `card/refund` a réussi sur l'ancien Fedow mais que la caisse ne
   sait pas lire ce qui a été repris, l'écran dit la vérité (« La carte est vidée sur
   l'ancien Fedow, mais pas en local. Incident enregistré : prévenez un responsable. »)
   au lieu de « Rien n'a été fait : réessayez ». Exception dédiée
   `CarteVideeSurLAncienFedowReponseIllisible`. Toujours un seul INCIDENT, rien d'écrit
   en local.
3. Docstring de `_executer_recharges` au présent (paramètre `vente`).
4. Correction de moyen de paiement : des lignes d'une vente dont le net vendu total vaut
   0 sont refusées proprement (400, « Rien à corriger : le montant est nul. »), sans
   rien écrire. Avant : `ValueError` du service de vente, donc une 500.
/ 1. NFC: any unexpected exception after the network debit logs the INCIDENT, then is
re-raised. 2. Card emptying: emptied on the old Fedow but unreadable answer → the screen
tells the truth. 3. `_executer_recharges` docstring. 4. Correcting zero-worth lines:
clean 400, nothing written.

**Pourquoi / Why :** relecture de la fiche B (2026-09-30), constats 1 à 4. Sans le
point 1, un débit réseau irréversible pouvait se perdre sans trace ; sans le point 2, le
caissier réessayait un vidage déjà fait là-bas.
/ Sheet B review findings 1 to 4.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_payer_par_nfc` : `except Exception` après `SoldeInsuffisant` et `EgaliteDeVenteRompue` ; `CarteVideeSurLAncienFedowReponseIllisible` levée par `_vider_la_carte_sur_l_ancien_fedow`, attrapée par `vider_carte` ; docstring `_executer_recharges` ; `corriger_moyen_paiement` : garde du montant nul |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | + `test_exception_imprevue_apres_debit_legacy_journalisee`, + `test_correction_de_lignes_au_montant_nul_refusee_rien_n_est_ecrit` |
| `tests/pytest/test_caisse_vider_carte_deux_fedow.py` | + `test_vider_carte_ancien_fedow_vide_puis_categories_illisibles_ecran_dit_la_verite` |

Chaîne traduisible ajoutée : « Rien à corriger : le montant est nul. » (le message du
point 2 existait déjà). Workflow i18n à lancer par le mainteneur.
/ One new translatable string; i18n workflow to run by the maintainer.

Hors B-4 : le point 4 n'est atteignable que par un POST « espece » (ou « carte_bancaire »)
d'un panier gratuit, que l'écran ne propose pas (`payer()` ne confronte pas le moyen reçu
aux moyens proposés) : bug n°16 du TODO.

#### Tests vus échouer / Tests seen failing (B-4)

Écrits avant le code, lancés : 3 failed.

| Test | Rouge (avant le code) |
|---|---|
| `test_exception_imprevue_apres_debit_legacy_journalisee` | `Attendu : un incident journalisé, trouvé : []` |
| `test_vider_carte_ancien_fedow_vide_puis_categories_illisibles_ecran_dit_la_verite` | message affiché « L'ancien Fedow n'a pas pu vider la carte. Rien n'a été fait : réessayez. » |
| `test_correction_de_lignes_au_montant_nul_refusee_rien_n_est_ecrit` | `ValueError: Un règlement de 0 n'existe pas` (views.py, `ajouter_reglement`) |

Vert après le code : les deux fichiers (105 passed) ; `test_pos_vider_carte.py`,
`test_corrections_fond_sortie.py`, `test_paiement_complementaire.py` et les 22 de
caractérisation (69 passed) ; `check` sans erreur ; `makemigrations --check` : aucun
changement.

#### Mutations (B-4)

Proposées, non jouées :

| Mutation (laboutik/views.py) | Test qui doit tomber |
|---|---|
| `_payer_par_nfc` : retirer le `logger.error` du `except Exception` | `test_exception_imprevue_apres_debit_legacy_journalisee` (aucun incident) |
| `_payer_par_nfc` : `raise` → `pass` dans ce `except` | le même (`DID NOT RAISE RuntimeError`, ou une autre erreur) |
| `_payer_par_nfc` : placer `except Exception` AVANT `except EgaliteDeVenteRompue` | `test_egalite_rompue_apres_debit_legacy_journalisee` (500 au lieu de l'écran) |
| `_vider_la_carte_sur_l_ancien_fedow` : `raise CarteVidee…` → `raise` | `test_vider_carte_ancien_fedow_vide_puis_categories_illisibles_ecran_dit_la_verite` (message) |
| `vider_carte` : ajouter un `logger.error("INCIDENT …")` dans `except CarteVidee…` | le même (deux incidents) |
| `corriger_moyen_paiement` : retirer la garde du montant nul | `test_correction_de_lignes_au_montant_nul_refusee_rien_n_est_ecrit` (`ValueError`) |
| `corriger_moyen_paiement` : retirer `vente_d_origine is not None and` | `test_correction_d_une_ligne_sans_vente_comme_avant` (400 au lieu de 200) |

### Session B-5 — l'ancien Fedow fait autorité à l'ouverture de la caisse / The old Fedow is authoritative when opening the register

**Migration :** Non.

**Quoi / What :** à l'ouverture de la caisse (`POST carte_primaire`), une fois la carte
primaire trouvée en local, la caisse lit la carte sur l'ancien Fedow
(`NFCcard.retrieve`), comme LaBoutik V1 :
1. `is_primary` vrai : ouverture comme avant ;
2. `is_primary` faux : la `CartePrimaire` locale est supprimée (en local seulement, aucun
   `set_primary`), avertissement journalisé, écran « Cette carte n'est plus une carte
   primaire pour ce lieu. Prévenez un responsable. » ;
3. ancien Fedow injoignable, erreur HTTP, réponse illisible, carte inconnue : ouverture
   refusée, rien n'est supprimé, erreur journalisée avec la cause, écran « Impossible de
   vérifier la carte primaire auprès de Fedow. Réessayez dans un instant, puis prévenez
   un responsable si cela recommence. » ;
4. lieu non relié à l'ancien Fedow : ouverture refusée, rien n'est supprimé, `FedowAPI`
   jamais créé, erreur journalisée, écran « Ce lieu n'est pas relié à Fedow : prévenez un
   responsable. »
`CardValidator` garde désormais `is_primary` (obligatoire : l'ancien Fedow le renvoie
toujours, calculé pour le lieu qui signe la requête).
/ On opening, the register asks the old Fedow whether the card is still primary. Not
primary: the local primary card is deleted and the register stays closed. Old Fedow
failing, card unknown there, or venue not linked: the register stays closed, nothing is
deleted. `CardValidator` now keeps `is_primary`.

**Pourquoi / Why :** l'ancien Fedow retire une carte primaire sans prévenir (VOID de la
carte, carte perdue). La caisse V2 s'ouvrait quand même, puis le vidage d'une carte
client (`card/refund`, qui exige la carte primaire) échouait en plein service.
/ The old Fedow withdraws primary cards silently; the register opened anyway and card
emptying then failed mid-service.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | + `_verifier_carte_primaire_aupres_de_l_ancien_fedow` (garde `can_fedow()` avant `FedowAPI`) ; appelée par `carte_primaire` après `_charger_carte_primaire` |
| `fedow_connect/validators.py` | `CardValidator.is_primary` (`BooleanField`, obligatoire) |
| `tests/pytest/test_caisse_ouverture_ancien_fedow.py` | nouveau : 14 tests (ouverture, retrait, pannes, carte inconnue, refus local, tag demandé, lieu non relié, client `retrieve`) |
| `tests/pytest/test_caisse_navigation.py` | faux ancien Fedow (autouse) : lieu relié, carte primaire confirmée, aucun envoi réseau |

Chaînes traduisibles ajoutées (3) : « Ce lieu n'est pas relié à Fedow : prévenez un
responsable. », « Impossible de vérifier la carte primaire auprès de Fedow. Réessayez dans
un instant, puis prévenez un responsable si cela recommence. », « Cette carte n'est plus
une carte primaire pour ce lieu. Prévenez un responsable. » Workflow i18n à lancer par le
mainteneur.
/ Three new translatable strings; i18n workflow to run by the maintainer.

Autres appelants de `retrieve` / `CardValidator` : kiosque (`kiosk/validators.py`,
`kiosk/views.py`), `laboutik/carte_primaire_ancien_fedow.py`, vidage de carte, lecture
de carte par signature, carte imbriquée des transactions. Aucun ne change : l'ancien
Fedow envoie `is_primary` dans toutes ses fiches de carte (`CardSerializer`), et les
tests du kiosque simulent `FedowAPI` en entier.

Hors B-5 : `point_de_vente` (GET avec `tag_id_cm`) ouvre l'interface sans passer par
`carte_primaire`, donc sans la vérification de l'ancien Fedow : bug n°17 du TODO.

#### Tests vus échouer / Tests seen failing (B-5)

Écrits avant le code, lancés : 10 failed, 4 passed (les 4 verts protègent le
comportement inchangé). Puis le test du lieu non relié, réécrit après la décision du
mainteneur, lancé seul : 1 failed.

| Test | Rouge (avant le code) |
|---|---|
| `test_ouverture_carte_plus_primaire_pour_l_ancien_fedow_la_supprime_en_local` | la caisse s'ouvre (`HX-Redirect` vers `point_de_vente`) |
| `test_ouverture_ancien_fedow_en_echec_refuse_sans_rien_supprimer` (4 cas) | la caisse s'ouvre |
| `test_ouverture_carte_inconnue_de_l_ancien_fedow_refuse_sans_rien_supprimer` | la caisse s'ouvre |
| `test_ouverture_l_ancien_fedow_recoit_le_tag_de_la_carte_scannee` | `assert [] == ['B93DCC88']` |
| `test_ouverture_lieu_non_relie_a_l_ancien_fedow_refuse_sans_rien_supprimer` | la caisse s'ouvre |
| `test_client_retrieve_garde_is_primary_de_l_ancien_fedow` (2 cas) | `KeyError: 'is_primary'` |
| `test_client_retrieve_refuse_une_reponse_sans_is_primary` | `DID NOT RAISE` |

Vert après le code : B-5 et navigation (26 passed) ; `test_carte_primaire_ancien_fedow.py`,
`test_caisse_vider_carte_deux_fedow.py` et les 4 fichiers du kiosque (96 passed) ; les
fichiers qui manipulent des fiches de carte Fedow (99 passed) ; les 22 de
caractérisation ; `check` sans erreur ; `makemigrations --check` : aucun changement.

#### Mutations (B-5)

Proposées, non jouées :

| Mutation | Test qui doit tomber |
|---|---|
| `laboutik/views.py` (`_verifier_…`) : retirer la garde `if not lieu_relie_a_l_ancien_fedow` | `test_ouverture_lieu_non_relie_…` (`FedowAPI` créé, la caisse s'ouvre) |
| la même garde : `return` du message → `return None` | le même (la caisse s'ouvre) |
| déplacer `FedowAPI()` avant le test `can_fedow()` | le même (`FedowAPI.__init__` appelé) |
| retirer `carte_primaire_obj.delete()` | `test_ouverture_carte_plus_primaire_…` (la carte primaire existe encore) |
| `if not carte_encore_primaire` → `if carte_encore_primaire` | le même, et `test_ouverture_carte_encore_primaire_…` |
| `except Exception` : `return message_verification_impossible` → `return None` | `test_ouverture_ancien_fedow_en_echec_…` (4 cas) |
| `except CarteInconnueDeFedow` : retirer le `logger.error` | `test_ouverture_carte_inconnue_de_l_ancien_fedow_…` (aucune erreur journalisée) |
| `retrieve(tag_id_de_la_carte)` → `retrieve(tag_id_de_la_carte[::-1])` | `test_ouverture_l_ancien_fedow_recoit_le_tag_…` |
| `carte_primaire` : appeler la vérification AVANT `_charger_carte_primaire` | `test_ouverture_carte_inconnue_en_local_…` et `…_non_primaire_en_local_…` |
| `fedow_connect/validators.py` : `is_primary = BooleanField(required=False)` | `test_client_retrieve_refuse_une_reponse_sans_is_primary` |
| retirer `is_primary` de `CardValidator` | `test_client_retrieve_garde_is_primary_…` (`KeyError`) |

### Session B-6 — docstrings et numérotation après la relecture de B-5 / Docstrings and numbering after the B-5 review

**Quoi / What :** documentation seulement, aucun changement de comportement.
/ Documentation only, no behaviour change.

| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_caisse_ouverture_ancien_fedow.py` | Docstring au présent : plus de date ni de décision de session, renvois V1/Fedow par nom de fonction (plus de numéros de ligne). Une seule numérotation 1 à 7, la même dans la docstring, les constantes et les sections de tests. |
| `laboutik/views.py` | Docstring de `CaisseViewSet.carte_primaire` : redirection vers le premier point de vente visible (tri `poid_liste`), pas d'écran de choix. Commentaire au-dessus de `except CarteInconnueDeFedow` : branche gardée pour un journal plus clair. |
| `tests/pytest/test_caisse_navigation.py` | Docstring de la garde réseau : elle couvre les tests, pas la fixture de module `test_data` (bug n°14). |

Tests : les deux fichiers de caisse, 26 passed ; `check` sans erreur.
/ Tests: both register files, 26 passed; `check` clean.

---

## Comment tester (a la main) / Manual test

### B-0, test 1 — adhésion vendue en espèces
1. Ouvrir la caisse (`https://lespass.tibillet.localhost/laboutik/`), point de vente
   qui propose une adhésion.
2. Ajouter l'adhésion, identifier un adhérent par e-mail (nouvel e-mail), prénom et nom,
   payer en espèces.
3. Vérifier : un mail « Confirmation » arrive à l'adhérent (Mailpit), avec le bouton
   « demander un reçu » ; dans l'admin, l'adhérent apparaît dans les utilisateurs du
   lieu, avec son prénom et son nom ; l'adhésion a une échéance.
4. Si le tarif a une récompense en monnaie (`fedow_reward_*`), le portefeuille de
   l'adhérent est crédité.

### B-0, test 2 — adhésion payée par carte NFC
1. Carte rattachée à un adhérent, chargée en monnaie cadeau et en monnaie locale (la
   monnaie cadeau ne couvre pas tout le prix).
2. Vendre l'adhésion, payer par NFC.
3. Vérifier : UN seul mail de confirmation, UNE seule récompense, deux lignes de vente
   (cadeau + locale).

### B-0, test 3 — renouvellement
1. Revendre la même adhésion au même adhérent.
2. Vérifier : pas de seconde adhésion, échéance prolongée, un mail de confirmation.
   (Deux webhooks sortants partent : bug connu n°2.)

### B-1, test 1 — vente en espèces
1. Caisse, 3 jus à 3,50 €, payer en espèces.
2. Admin « Ventes & comptabilité » (ou shell ci-dessous) : une vente `REGLEE` numérotée,
   un règlement espèces de 10,50 €, un article 10,50 € (HT 8,75 €, TVA 1,75 € à 20 %).

### B-1, test 2 — recharge en euros
1. Carte client scannée, recharge de 10 € payée en espèces.
2. La ligne de recharge a une TVA de 0 (et plus 20 %) ; la vente a un article hors chiffre
   d'affaires et un règlement espèces de 10 €.

### B-1, test 3 — recharge cadeau mêlée à une bière
1. Mettre une bière et une recharge cadeau dans le panier, choisir un moyen de paiement.
2. Message « La recharge cadeau se fait à part : retirez les autres articles. », rien
   n'est encaissé ; la carte n'est pas créditée.
3. La recharge cadeau seule (scan de la carte) reste créditée sans paiement.

### B-1, test 4 — retour de consigne relié
1. Admin, produits de caisse : un produit « Retour de consigne » ; le champ « Rembourse la
   consigne » n'apparaît que pour cette méthode. Le relier au gobelet (vendu 1,00 €, 20 %).
   Donner au retour un autre prix (ex. −1,50 €).
2. Caisse : la tuile du retour affiche −1 (le prix du gobelet). Rembourser en espèces :
   l'écran annonce 1,00 € à rendre. Par carte : la carte est recréditée de 1,00 €.
3. La ligne du retour vaut −1,00 € à 20 % ; la vente est un avoir.
4. Retirer le lien : l'admin refuse d'enregistrer, et la caisse n'affiche plus la tuile
   (voir B-1b).

### B-1b, test 1 — l'admin refuse un retour mal configuré
1. Admin, produits de caisse, « Ajouter » : méthode « Retour de consigne », un tarif à
   −1,00 €, champ « Rembourse la consigne » vide. Enregistrer.
2. La page revient avec une erreur sous « Rembourse la consigne » ; aucun produit créé.
3. Choisir un gobelet dont le seul tarif en euros est dépublié : même refus, message qui
   nomme le gobelet.
4. Choisir un gobelet avec un tarif en euros publié : enregistré.

### B-1b, test 2 — tuile masquée
1. Retour relié au gobelet, tuile visible à la caisse (prix du gobelet).
2. Dans l'admin, dépublier le tarif en euros du gobelet (ou délier le retour en base) :
   recharger la caisse, la tuile du retour a disparu ; les autres tuiles restent.
3. Republier le tarif : la tuile revient.

### B-1b, test 3 — coût d'achat du retour
1. Gobelet à prix d'achat 30 (centimes), retour à prix d'achat 99.
2. Rembourser 2 gobelets en espèces ; en base, l'article du retour a `cout_achat = -60`.
3. Gobelet à prix d'achat 0 : `cout_achat` vide.

### B-1b, test 4 — démo
1. `create_test_pos_data` (mainteneur) : « Retour Consigne » a « Rembourse la consigne » =
   « Consigne » ; sa tuile s'affiche à −1.

### B-2a, test 1 — paiement NFC avec jetons et monnaie locale
1. Charger une carte avec 3,00 € de monnaie cadeau et 2,00 € de monnaie locale.
2. Vendre une bière à 5,00 €, payer avec la carte.
3. En base (voir plus bas) : la dernière vente a deux articles (catalogue 300 offert,
   catalogue 200), deux règlements LG 300 et LE 200, total net 200.

### B-2a, test 2 — archive fiscale
1. Offrir une bière (mode gérant), puis exporter l'archive fiscale de la journée.
2. La ligne offerte a HT = TTC de la ligne et TVA 0 (pas de TVA inventée).

### B-2b, test 1 — la carte ne suffit pas, le reste en espèces
1. Charger une carte avec 5,00 € de monnaie locale.
2. Vendre 3 jus à 3,50 € (10,50 €), payer avec la carte : l'écran « reste à payer »
   annonce 5,50 €. Choisir les espèces, taper 10,00 € : l'écran annonce 4,50 € à rendre.
3. En base (voir plus bas) : la dernière vente a deux articles (catalogue 500 et 550),
   deux règlements LE 500 et espèces 550 (pas 1000), total net 1050, HT 875, TVA 175.

### B-2b, test 2 — jetons et CB
1. Carte avec 3,00 € de monnaie cadeau seulement ; vendre une bière à 5,00 €, payer
   avec la carte, puis le reste (2,00 €) en CB.
2. En base : règlements LG 300 et CB 200 ; vente nette 200, HT 167, TVA 33.

### B-2c, test 1 — deux cartes
1. Charger une carte A avec 5,00 € et une carte B avec 6,00 € de monnaie locale.
2. Vendre 3 jus à 3,50 € (10,50 €), payer avec la carte A : l'écran « reste à payer »
   annonce 5,50 €. Choisir « 2ᵉ carte », poser la carte B : succès, un cadre par carte.
3. En base : la dernière vente a deux règlements LE 500 (carte A, son portefeuille) et
   LE 550 (carte B, son portefeuille) ; ses articles portent tous la carte A.

### B-2c, test 2 — deux cartes, puis espèces
1. Carte A avec 5,00 €, carte B avec 3,00 € ; 3 jus (10,50 €).
2. Payer avec A, puis 2ᵉ carte B : le second écran annonce 2,50 €. Choisir les espèces,
   taper 10,00 € : 7,50 € à rendre.
3. En base : règlements LE 500 (A), LE 300 (B), espèces 250 (pas 1000).

### B-2d, test 1 — payer en FED à la caisse
1. `stripe listen` tourne. Avec un compte neuf, « Mon compte » → « Solde » → recharger
   3 € par carte (4242 4242 4242 4242, 12/42, 424, Douglas Adams). Le solde FED passe à
   3,00 €.
2. Rattacher une carte NFC à ce compte (admin, cartes), sans aucune monnaie locale
   `fedow_core` dessus.
3. Caisse : vendre un article à 2,50 €, payer avec la carte : écran de succès.
4. Vérifier : le solde FED du compte vaut 0,50 € ; en base (voir plus bas), la dernière
   vente est `REGLEE`, numérotée, avec UN règlement `SF` de 250, `reference_externe`
   remplie, `fedow_transaction_uuid` vide. Dans le shell du lieu,
   `FedowAPI().transaction.retrieve(reference_externe)` rend la transaction : 250,
   action « QRS ».

### B-2d, test 2 — payer en monnaie locale de l'ancien Fedow
1. Un compte crédité en monnaie locale du lieu sur l'ancien Fedow (sans jeton
   `fedow_core`), carte rattachée.
2. Caisse : article à 2,50 €, payer avec la carte.
3. Vérifier : règlement `LE` de 250 avec `reference_externe` (transaction « QRS » sur le
   Fedow), `fedow_transaction_uuid` vide ; aucune transaction `fedow_core` émise par le
   portefeuille ; le solde de l'ancien Fedow a baissé de 2,50 €.

### B-3a, test 1 — commande de table en espèces
1. Ouvrir une commande de table de 2 bières à 5,00 € (route `/laboutik/commande/ouvrir/`,
   aucune interface ne l'appelle aujourd'hui : par un test ou une requête).
2. La payer en espèces, somme donnée 20,00 €.
3. En base : la commande est `PA` et porte une vente `REGLEE` numérotée ; un règlement
   espèces de 1000 (pas 2000) ; la clé de la vente = `uuid_transaction` des lignes ;
   la table est libre.

### B-3a, test 2 — commande de table en NFC
1. Même commande, payée avec une carte chargée de 20,00 € de monnaie locale.
2. En base : `commande.vente` = la vente dont le règlement LE 1000 porte l'uuid de la
   transaction de la carte. Avec une carte à 3,00 € : écran « reste à payer », la
   commande reste `OP`, sans vente.

### B-3c, test 1 — corriger des espèces en CB
1. Caisse : vendre 3 jus à 3,50 € en espèces.
2. Ventes → Historique de vente → clic sur la vente → « Corriger moyen » → CB.
3. En base : la vente d'origine a toujours son règlement espèces 1050 et la même
   empreinte (`hmac_hash`) ; une nouvelle vente `CORRECTION` `REGLEE`, numérotée, dont
   `vente_liee` est la vente d'origine, sans article, règlements espèces −1050 et
   CB +1050 ; la ligne est en CB avec sa `CorrectionPaiement`.
4. Corriger encore en chèque : une 2ᵉ vente `CORRECTION` liée à la même vente d'origine
   (CB −1050, chèque +1050).

### B-3c, test 2 — vente couverte par une clôture
1. Faire la clôture journalière, puis tenter de corriger une vente d'avant la clôture :
   message « couverte par une cloture », aucune vente `CORRECTION`.

### B-3d, test 1 — le ticket X garde ses totaux
1. Sur un lieu sans autre vente du jour : vendre 3 jus à 3,50 € en espèces, puis une
   bière à 5,00 € avec une carte qui porte 3,00 € de jetons cadeau, le reste en CB.
2. Ticket X : espèces 10,50 € ; CB 2,00 € ; cashless 3,00 € (jetons) ; total 15,50 € ;
   TVA 20 % : TTC 15,50 €, HT 12,92 €, TVA 2,58 € (comme avant le chantier).

### B-3b-1, test 1 — vider une carte sur les deux Fedow
1. Lieu relié à l'ancien Fedow ; une carte avec de la monnaie locale du lieu en local,
   et de la monnaie locale et du FED sur l'ancien Fedow.
2. Caisse → « Vider carte » → scanner la carte → confirmer.
3. L'écran rend le total des deux Fedow. En base : une vente `VIDAGE_CARTE` `REGLEE`,
   sans article : `LE` local (`fedow_transaction_uuid`), `LE` et `SF` distants
   (`reference_externe`), espèces −total ; sur l'ancien Fedow, la carte est vide.

### B-3b-1, test 2 — ancien Fedow injoignable
1. Couper l'accès à l'ancien Fedow, vider une carte connue : message « L'ancien Fedow n'a
   pas pu vider la carte… », solde local intact, aucune vente.

### B-3b-1, test 3 — vider et délier une carte vide
1. Une carte d'adhérent vide partout, connue de l'ancien Fedow : « Vider carte », case
   « vider et délier » cochée → succès, carte déliée en local et sur l'ancien Fedow,
   aucune vente.

### B-3b-2, test 1 — l'aperçu et l'écran de succès, séparés par Fedow
1. Lieu relié à l'ancien Fedow ; une carte avec de la monnaie locale et des jetons
   cadeau en local, et de la monnaie locale et du FED sur l'ancien Fedow.
2. Caisse → « Vider carte » → scanner la carte. L'aperçu montre « Fedow local » et
   « Ancien Fedow », une ligne par monnaie, les jetons cadeau « repris, sans argent », et
   « À rendre en espèces » = monnaie locale + FED des deux Fedow. Rien n'est débité : le
   solde sur l'ancien Fedow n'a pas bougé.
3. Confirmer : l'écran de succès montre les mêmes parties et le montant rendu.

### B-3b-2, test 2 — le reçu imprimé
1. Sur un terminal avec imprimante, après le test 1 : « Imprimer le reçu ».
2. Le ticket porte le nom et l'adresse du lieu, « FEDOW LOCAL » puis « ANCIEN FEDOW »
   avec le montant de chaque ligne d'argent, les jetons cadeau « repris, sans argent »
   (sans « 1 x »), puis « TOTAL » = l'argent rendu (sans les jetons cadeau).
3. Couper l'accès à l'ancien Fedow, puis « Imprimer le reçu » : message « L'ancien Fedow
   ne répond pas : le reçu n'est pas imprimé… », rien ne sort.

### B-3b-2, test 3 — l'aperçu accepte ce que la vidange accepte
1. Carte vide en local, avec de la monnaie locale sur l'ancien Fedow : l'aperçu s'ouvre.
2. Carte avec seulement des jetons cadeau : l'aperçu s'ouvre, 0,00 € à rendre.
3. Carte d'adhérent vide partout, connue de l'ancien Fedow : l'aperçu s'ouvre et ne
   propose que « Rembourser et réinitialiser la carte ».
4. Ancien Fedow coupé : l'aperçu dit « L'ancien Fedow ne répond pas… ».

Ces tests sont jouables à la main : la carte primaire du terminal doit être déclarée à
l'ancien Fedow (B-3b-3 ; pour la carte du seed, `declarer_cartes_primaires_ancien_fedow`).

### B-3b-3, test 1 — déclarer une carte primaire
1. Admin → Caisse → Cartes primaires → Ajouter : choisir une carte du lieu connue de
   l'ancien Fedow, enregistrer. Elle est créée ; sur l'ancien Fedow, la carte est
   primaire du lieu (`is_primary: True` à la lecture de la carte).
2. Même chose avec une carte inconnue de l'ancien Fedow : message « … créez-la d'abord
   dans l'admin des cartes. », rien n'est créé.
3. Ouvrir une carte primaire existante : la carte NFC est en lecture seule ; changer le
   mode gérant enregistre sans appel à l'ancien Fedow.

### B-3b-3, test 2 — retirer une carte primaire
1. Supprimer une carte primaire (unitaire, puis « supprimer la sélection ») : elle
   disparaît ; sur l'ancien Fedow, la carte n'est plus primaire du lieu.
2. Ancien Fedow coupé : la suppression a lieu, et la liste affiche « Carte primaire …
   supprimée ici, mais l'ancien Fedow a refusé de la retirer… ».

### B-3b-3, test 3 — rattrapage
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py
   declarer_cartes_primaires_ancien_fedow --schema lespass` : liste, n'envoie rien.
2. Avec `--appliquer` (après accord) : chaque carte « déclarée » ou « REFUSÉE » /
   « INCONNUE » ; relancer : même résultat (208 = déjà déclarée).
3. Puis rejouer les E2E de B-3b-2 (vidage sur l'ancien Fedow).

### B-4, test 1 — correction d'une vente à 0 €
1. Un article à 0,00 € payé en espèces : seul un POST « espece » forgé y arrive (l'écran
   ne propose que « Valider »). Par exemple avec le test
   `test_correction_de_lignes_au_montant_nul_refusee_rien_n_est_ecrit`.
2. Corriger la ligne en CB : message « Rien à corriger : le montant est nul. », la ligne
   reste en espèces, aucune `CorrectionPaiement`, aucune vente `CORRECTION`.

### B-4, test 2 — ancien Fedow vidé, réponse illisible
Non reproductible à la main sans couper l'ancien Fedow entre `card/refund` et la lecture
de la fiche d'une monnaie : couvert par
`test_vider_carte_ancien_fedow_vide_puis_categories_illisibles_ecran_dit_la_verite`. Si
le cas arrive : message « La carte est vidée sur l'ancien Fedow, mais pas en local… »,
un INCIDENT « catégories illisibles » dans les logs, rien en local.

### B-5, test 1 — la carte primaire confirmée par l'ancien Fedow
1. Lieu relié à l'ancien Fedow, carte primaire déclarée là-bas (`declarer_cartes_primaires_ancien_fedow`).
2. Ouvrir la caisse avec cette carte : la caisse s'ouvre comme avant.

### B-5, test 2 — la carte primaire retirée par l'ancien Fedow
1. Sur l'ancien Fedow, retirer la carte des cartes primaires du lieu (VOID de la carte,
   ou carte perdue).
2. Ouvrir la caisse avec cette carte : message « Cette carte n'est plus une carte
   primaire pour ce lieu. Prévenez un responsable. », pas d'ouverture.
3. Dans l'admin, la carte primaire a disparu ; la carte NFC existe toujours. Log WARNING.

### B-5, test 3 — ancien Fedow injoignable
1. Couper l'ancien Fedow (ou le rendre injoignable), ouvrir la caisse : message
   « Impossible de vérifier la carte primaire auprès de Fedow… », pas d'ouverture, la
   carte primaire reste. Log ERROR avec la cause.

### B-5, test 4 — lieu non relié
Couvert par `test_ouverture_lieu_non_relie_a_l_ancien_fedow_refuse_sans_rien_supprimer`.
Message « Ce lieu n'est pas relié à Fedow : prévenez un responsable. »

### Verifs DB
```python
# docker exec lespass_django poetry run python /DjangoFiles/manage.py shell
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Membership
with tenant_context(Client.objects.get(schema_name="lespass")):
    adhesion = Membership.objects.filter(status=Membership.LABOUTIK).order_by("-last_contribution").first()
    print(adhesion.deadline, adhesion.user.first_name, adhesion.user.client_achat.all())

# B-1 : la dernière vente de caisse, ses articles et ses règlements
from BaseBillet.models_vente import Vente
with tenant_context(Client.objects.get(schema_name="lespass")):
    vente = Vente.objects.filter(origine="LB").order_by("-numero").first()
    print(vente.numero, vente.nature, vente.statut, vente.total_catalogue, vente.total_ttc)
    for article in vente.articles.all():
        print(article.total_catalogue, article.total_ht, article.total_tva, article.vat)
    for reglement in vente.reglements.all():
        print(reglement.moyen, reglement.montant)
```
