# Chantier 01 — Recharge cashless au check carte, avec un « mode recharge »

**Date :** 2026-11-24
**Statut :** validée par le mainteneur (2026-11-24), après relecture Fable
**Apps touchées :** `laboutik/`, `Administration/`
**Migration :** Oui (`laboutik/migrations/0003_carteprimaire_mode_recharge.py`, schéma + données)

---

## 1. Le besoin

Aujourd'hui, une carte NFC se recharge par deux chemins :

1. **Les tuiles d'un point de vente.** Tout point de vente qui a un produit de recharge dans
   ses produits affiche sa tuile (`_construire_donnees_articles`, `laboutik/views.py:674`).
   C'est en général le point de vente « Cashless » : le signal `fedow_core/signals.py:160`
   y attache chaque nouveau produit de recharge. Ce chemin ne regarde pas la carte primaire.
2. **La zone « Recharger » du check carte.** Elle ne s'affiche que si la carte primaire du
   caissier a au moins un point de vente de type `CASHLESS`
   (`_carte_primaire_a_un_point_de_vente_cashless`, `laboutik/views.py:1292`, règle du
   2026-09-29, commit `2f6007be`).

La règle du check carte **cache seulement la zone à l'écran**. Le serveur accepte une
recharge envoyée depuis n'importe quel point de vente, sans regarder la carte primaire
(`_extraire_articles_du_panier`, `laboutik/views.py:6688`).

**Ce qu'on veut (décisions du mainteneur, 2026-11-24) :**

- **D1.** Le droit de recharger vient d'une **nouvelle case sur la carte primaire :
  « Mode recharge »**. Elle est indépendante du mode gérant (`edit_mode`) : un bénévole peut
  recharger sans pouvoir modifier les prix.
- **D2.** **Sans** mode recharge : aucune recharge possible. La zone « Recharger » du check
  carte est cachée, **et les tuiles de recharge de la grille sont invisibles**.
  **Avec** mode recharge : la zone du check carte et les tuiles sont visibles.
- **D3.** Le point de vente « Cashless » reste. On doit pouvoir mettre **une recharge et une
  adhésion dans le même panier** : les tuiles de recharge restent donc sur la grille, pour
  les caissiers qui ont le droit.
- **D4.** Le **serveur** applique la règle, pas seulement l'écran.

## 2. Ce qui change

### 2.1 Modèle — `laboutik/models.py`, `CartePrimaire`

Un champ, juste après `edit_mode` :

```python
    # Mode recharge : autorise ce caissier à recharger une carte depuis le check carte.
    # / Top-up mode: allows this cashier to top up a card from the check card popup.
    mode_recharge = models.BooleanField(
        default=False,
        verbose_name=_("Mode recharge"),
        help_text=_(
            "Autorise ce caissier à recharger les cartes cashless, depuis le check "
            "carte et depuis les tuiles de recharge."
        ),
    )
```

### 2.2 Migration — `laboutik/migrations/0003_carteprimaire_mode_recharge.py`

Un seul fichier : `AddField`, puis un `RunPython`, comme `0002_preparer_chaque_lieu.py`
(qui a déjà la garde `schema_courant == "public"` à reprendre).

Le `RunPython` donne `mode_recharge=True` aux seules cartes primaires qui ont un point de
vente de type `CASHLESS` (`"C"`, `laboutik/models.py:849`). Ce sont les caissiers qui
rechargent aujourd'hui par le check carte. Sans cette étape, plus personne ne recharge le
jour du déploiement.

Les autres cartes restent sans droit, même si l'un de leurs points de vente a une tuile de
recharge : cette tuile devient invisible pour elles (D2). Un gestionnaire coche la case dans
l'admin s'il veut leur rendre la recharge.

```python
    CartePrimaire.objects.filter(points_de_vente__comportement="C").update(
        mode_recharge=True
    )
```

**À confirmer par le mainteneur** (voir §4).

`reverse_code=migrations.RunPython.noop`.

### 2.3 Admin — `Administration/admin/laboutik.py`

- `CartePrimaireAdminForm.Meta.fields` (ligne 832) : ajouter `mode_recharge`.
- Le fieldset de `CartePrimaireAdmin` (ligne 947) : ajouter `mode_recharge` à côté de
  `edit_mode`.
- `list_display` et `list_filter` (lignes 923-924) : ajouter `mode_recharge`, comme
  `edit_mode`.

### 2.4 La règle, en un seul endroit — `laboutik/views.py`

`_carte_primaire_a_un_point_de_vente_cashless(tag_id)` (ligne 1292) est **remplacée** par
`_carte_primaire_peut_recharger(tag_id)`. Même forme, la dernière ligne devient :

```python
    return carte_primaire_obj.mode_recharge
```

Sans `tag_id` ou carte introuvable : `False`, comme aujourd'hui. (Le code de la caisse
accepte une requête sans carte primaire, `_valider_carte_primaire_pour_pv` ligne 2567. Aucun
écran ne le fait : seuls des tests l'utilisent.)

Textes qui décrivent l'ancienne règle, à mettre à jour :
- `laboutik/views.py:2626-2635` (docstring de `_produits_de_recharge_du_lieu`) et `:2703` ;
- `laboutik/views.py:13891-13897` (commentaire de l'étape 6 de `retour_carte`) ;
- `laboutik/templates/laboutik/partial/hx_card_recharge.html:20` ;
- `laboutik/templates/laboutik/partial/hx_check_card.html:27-29` ;
- `laboutik/models.py:836` (« CASHLESS : charge automatiquement toutes les recharges »).

### 2.5 Check carte — `retour_carte()`

Ligne 13899 : appeler `_carte_primaire_peut_recharger()` au lieu de l'ancienne fonction.
Rien d'autre ne change.

`recharge_carte()` (les étapes quoi / combien) n'est **pas** modifié : c'est un GET qui
n'écrit rien, et la zone n'apparaît que si `retour_carte()` l'a affichée. La garde du §2.7
refuse le paiement.

### 2.6 Grille du point de vente — tuiles de recharge selon le droit

Les tuiles sont construites à un seul endroit : `_construire_donnees_articles`
(`laboutik/views.py:674`). Son seul appelant, `point_de_vente()` (ligne 3617), a déjà chargé
la carte primaire (`carte_primaire_obj`, ligne 3600).

- `_construire_donnees_articles` reçoit un paramètre `afficher_les_recharges=False`.
- Dans le bloc des lignes 725-731 (qui saute déjà les recharges sans asset actif), on saute
  aussi la recharge si `afficher_les_recharges` est faux.
- `point_de_vente()` passe
  `afficher_les_recharges=carte_primaire_obj is not None and carte_primaire_obj.mode_recharge`.
  Pas de requête en plus : la carte est déjà chargée.

Valeur par défaut `False` : sans le droit, pas de tuile. Les deux tests qui appellent la
fonction directement (`test_laboutik_recharge_temps_desactivee.py:85`,
`test_stock_visuel_pos.py`) ne vendent pas de recharge en euros : à vérifier en les lançant.

### 2.7 Garde serveur

**a) `_extraire_articles_du_panier()`** — `moyens_paiement()`, `_executer_paiement()`,
`identifier_client()` et `_executer_paiement_complementaire()` l'appellent, avec
`request.POST`. Les deux formulaires du check carte envoient `tag_id_cm`
(`hx_card_recharge.html:185` vers `payer`, `:214` « Offrir » vers `identifier_client`). Le
panier de la grille l'envoie aussi (`#addition-form`) : à vérifier sur le parcours
recharge + adhésion.

Dans la boucle, après avoir trouvé le produit (dans le M2M du point de vente **ou** parmi
les recharges du lieu) :

```python
        # Une recharge n'est acceptée que si la carte primaire du caissier est en
        # mode recharge, LU EN BASE. Sans ce contrôle, un POST forcé rechargerait
        # depuis n'importe quel point de vente.
        # / A top-up is accepted only when the cashier's primary card is in top-up
        #   mode, read from the database.
        if produit.methode_caisse in METHODES_RECHARGE:
            if not _carte_primaire_peut_recharger(donnees_post.get("tag_id_cm", "")):
                raise ValueError(
                    _("Cette carte primaire n'a pas le droit de recharger.")
                )
```

Le contrôle est dans la boucle : un panier sans recharge ne fait aucune requête de plus.

Effet chez chaque appelant :
- `moyens_paiement()` (`:9295`), `_executer_paiement()` (`:9573`) et
  `_executer_paiement_complementaire()` (`:12169`) rendent le message en 400.
- `identifier_client()` (`:11739`) fait `except (PointDeVente.DoesNotExist, ValueError): pass`.
  Le panier reste vide, **rien n'est crédité**, mais aucun message ne s'affiche. On ne
  change pas ce `except` : ce cas n'arrive que par un POST forcé, ou si le droit est retiré
  pendant que la popup est ouverte.

**b) Commande de table** — `ouvrir_commande()` et `ajouter_articles()` (mode restaurant)
acceptent tout produit du point de vente, recharges comprises. Puis `payer_commande`
crédite par `_payer_par_nfc` sans passer par `_extraire_articles_du_panier`. Une commande de
table ne porte jamais de recharge : la carte du client n'est pas là quand on prend la
commande. Les deux vues refusent donc une recharge (400, « Une recharge se fait au comptoir,
pas depuis une commande. »), comme elles refusent déjà un retour de consigne.
(Implémentation : refus avec message plutôt qu'un `.exclude()` silencieux, et
`ajouter_articles` fermé aussi.)

### 2.8 Données de démo — `laboutik/management/commands/create_test_pos_data.py`

Ligne 1321-1324 : ajouter `"mode_recharge": True` dans les `defaults` du `get_or_create`
de la carte primaire. Sur une base de dev déjà remplie, les `defaults` ne s'appliquent pas :
c'est la migration (§2.2) qui donne le droit à la carte de démo.

## 3. Hors périmètre (on ne touche pas)

- **Le signal `fedow_core/signals.py:160`** continue d'attacher les produits de recharge aux
  points de vente Cashless.
- **Le point de vente `CASHLESS`** reste tel quel (D3). Le parcours de la grille (recharge +
  adhésion, `moyens_paiement` puis `lire_nfc_client` puis `identifier_client`) ne change pas :
  seule la visibilité des tuiles dépend du droit.
- **Le kiosk** (`kiosk/credit.py:150`) et l'API v2 (`wallet-refills`) ont leurs propres
  flux de recharge.
- **Le mode gérant** (`edit_mode`) et les règles de paiement d'une recharge (pas de NFC pour
  une recharge payante, pas d'OFFRIR pour une recharge en euros) ne changent pas.

## 4. Question ouverte (au mainteneur)

- **La migration de données (§2.2).** Proposition : `mode_recharge=True` pour les seules
  cartes qui ont un point de vente Cashless. L'autre choix serait « aucune carte » : le jour
  du déploiement, plus personne ne recharge dans aucun lieu, tant qu'un gestionnaire n'a pas
  coché la case.
- **Effet de bord à connaître :** un caissier sans droit qui ouvre le point de vente Cashless
  voit une grille sans tuile de recharge. La catégorie « Cashless » peut rester affichée,
  vide. On n'y touche pas dans ce chantier.

## 5. Tests

### 5.1 Tests de la règle — dans `tests/pytest/test_retour_carte_recharge.py`

Pas de nouveau fichier. Les tests de la zone « Recharger » existent déjà (lignes 303, 349,
538, 656) : ils passent de la règle « point de vente cashless » à la règle « mode
recharge ». On ajoute :

1. Grille d'un point de vente qui contient un produit de recharge : la tuile est visible
   avec une carte en mode recharge, invisible sans. Ce test va dans
   `test_caisse_ecrit_la_vente.py`, qui a déjà les aides de la grille.
2. `payer` d'une recharge euros avec une carte **sans** mode recharge : 400, aucune ligne de
   vente, aucun crédit.
3. « Offrir » (recharge cadeau, `identifier_client`) avec une carte **sans** mode recharge :
   aucun crédit sur la carte.

Chaque test passe par une mutation volontaire avant d'être livré.

La migration de données ne reçoit pas de test automatique (elle ne joue qu'une fois). Elle
se vérifie à la main, voir la fiche `CHANGELOG/`.

### 5.2 Tests existants à adapter

Il n'y a pas de fabrique commune de carte primaire : chaque test crée la sienne. Chaque test
qui vend une recharge par les vues doit donc créer sa carte avec `mode_recharge=True` et
envoyer `tag_id_cm`. Beaucoup envoient aujourd'hui un panier **sans** `tag_id_cm` : ils
seront refusés.

Liste repérée par recherche (à confirmer en lançant les fichiers) :
- `tests/pytest/test_retour_carte_recharge.py`
- `tests/pytest/test_hors_argent_offerts.py` (lignes 214, 231, 458, 518, 626)
- `tests/pytest/test_avoirs_ecrivent_la_vente.py:2650`
- `tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py`
- `tests/pytest/test_part_en_jetons.py` (lignes 552, 1432)
- `tests/pytest/test_caisse_une_ligne_par_article.py:1555` (appel direct de
  `_extraire_articles_du_panier` avec un dict)
- `tests/pytest/test_caisse_ecrit_la_vente.py`, `test_vente_en_points.py`,
  `test_identification_solde_reseau.py`, `test_rapatriement_carte_points_de_scan.py`

E2E :
Les E2E utilisent la carte de démo. Elle a `mode_recharge` (§2.8 et migration) : les
tuiles et la zone du check carte restent visibles. À lancer pour confirmer :
- `tests/e2e/test_pos_cashless_simulateur_nfc.py`
- `tests/e2e/test_recharge_pos_puis_qrcode.py`
- `tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py`
- `tests/e2e/test_parcours_fedow_reel.py`

## 6. Ordre d'implémentation

1. Modèle + migration (§2.1, §2.2).
2. Admin (§2.3).
3. Règle + check carte (§2.4, §2.5), et adaptation des tests existants de la zone.
4. Grille (§2.6) et test 1.
5. Garde serveur (§2.7) et tests 2-3.
6. Démo (§2.8), tests existants (§5.2), suite complète (sur accord du mainteneur).
7. `CHANGELOG/2026-11-24-recharge-mode-recharge.md`, avec la vérification à la main de la
   migration. Signaler les nouvelles chaînes i18n.

**Déploiement :** la migration doit passer **avant** que le nouveau code serve des requêtes
(ordre habituel : pull → migrate → restart gunicorn, daphne, celery).
