# Chantier 01 — « Mode recharge » : plan d'implémentation

> **Pour les agents :** sous-skill requis : `superpowers:executing-plans` (ou
> `superpowers:subagent-driven-development`). Les étapes utilisent des cases `- [ ]`.

**But :** une case « Mode recharge » sur la carte primaire ouvre, ou ferme, toute recharge
cashless en caisse : zone « Recharger » du check carte, tuiles de recharge de la grille, et
paiement côté serveur.

**Architecture :** un champ booléen sur `CartePrimaire`. Une seule fonction lit la règle
(`_carte_primaire_peut_recharger`). L'écran l'appelle pour afficher la zone et les tuiles ; le
serveur l'appelle dans `_extraire_articles_du_panier` pour refuser une recharge forcée.

**Stack :** Django multi-tenant (django-tenants), HTMX, pytest.

**Spec :** `TECH_DOC/SESSIONS/RECHARGE_CAISSE/SPEC.md` (lire avant ce plan).

## Contraintes globales

- **Git : aucun `add`, `commit`, `push`, `merge`, `rebase`, ni commande destructive.** Le
  mainteneur commit. Jamais de `Co-Authored-By`.
- pytest seulement par `ulimit -v 8000000; timeout 900 make test ARGS="<fichiers>"`. Suite
  complète seulement sur accord du mainteneur.
- `poetry`, `python manage.py`, `ruff` seulement dans `docker exec lespass_django`.
- Jamais `ruff format` sur un fichier existant. `ruff check` sans `--fix`.
- Jamais `makemessages` / `compilemessages` : lister les nouvelles chaînes dans le CHANGELOG.
- Texte source des `_()` en français. Commentaires FALC, bilingues FR puis EN.
- Chaque nouveau test est vu **échouer** sur une mutation volontaire, puis la mutation est
  retirée (`# MUTATION` en fin de ligne, retirée par `sed -i '/# MUTATION$/d'`).
- La garde serveur lit `mode_recharge` **en base**, jamais depuis le POST.
- Le message de refus : `_("Cette carte primaire n'a pas le droit de recharger.")`.

## Points à surveiller (Review Focus)

1. **Recharge + adhésion dans le même panier**, carte en mode recharge : le panier passe en
   entier (D3 de la spec). Test : Tâche 4, `test_recharge_et_adhesion_meme_panier_acceptees`.
2. **Carte avec un point de vente Cashless mais sans mode recharge** : la zone est cachée.
   L'ancienne règle ne doit plus rien ouvrir. Test : Tâche 2.
3. **Droit retiré pendant que la popup est ouverte** : `payer` répond 400, rien n'est crédité.
   Test : Tâche 4, `test_payer_une_recharge_sans_mode_recharge_refuse`.
4. **Commande de table qui contient une recharge** : la recharge n'entre pas dans la commande.
   Test : Tâche 4, `test_commande_de_table_ignore_la_recharge`.

Pas de cinquième cas trouvé.

---

### Tâche 1 : le champ, la migration, l'admin, la démo

**Fichiers :**
- Modifier : `laboutik/models.py` (`CartePrimaire`, après `edit_mode`, vers la ligne 1000)
- Créer : `laboutik/migrations/0003_carteprimaire_mode_recharge.py`
- Modifier : `Administration/admin/laboutik.py:928` (`Meta.fields`), `:1019-1020`
  (`list_display`, `list_filter`), `:1043` (fieldset)
- Modifier : `laboutik/management/commands/create_test_pos_data.py:1321-1324`

**Interfaces :**
- Produit : `CartePrimaire.mode_recharge` (`BooleanField`, `default=False`).

- [ ] **Étape 1 : le champ.** Code exact dans la spec §2.1.
- [ ] **Étape 2 : la migration, écrite à la main.** Dépend de `("laboutik",
  "0002_preparer_chaque_lieu")`. `AddField`, puis `RunPython(donner_le_mode_recharge_aux_caissiers_cashless,
  reverse_code=migrations.RunPython.noop)`. La fonction :
  - lit le modèle par `apps.get_model("laboutik", "CartePrimaire")` ;
  - ne fait rien si `connection.schema_name == "public"` (même garde que
    `0002_preparer_chaque_lieu.py`) ;
  - fait `CartePrimaire.objects.filter(points_de_vente__comportement="C").update(mode_recharge=True)`.

  Docstring FALC en tête du fichier : ce que fait la migration, et pourquoi seules les cartes
  avec un point de vente Cashless reçoivent le droit.
- [ ] **Étape 3 : vérifier qu'il ne manque rien au modèle.**
  Run : `docker exec lespass_django poetry run python manage.py makemigrations laboutik --check --dry-run`
  Attendu : `No changes detected`.
- [ ] **Étape 4 : appliquer en dev.**
  Run : `docker exec lespass_django poetry run python manage.py migrate_schemas laboutik`
  Attendu : `Applying laboutik.0003_carteprimaire_mode_recharge... OK` sur chaque schéma,
  aucune erreur sur `public`.
- [ ] **Étape 5 : contrôler la donnée** sur le schéma `lespass`, dans
  `docker exec lespass_django poetry run python manage.py tenant_command shell --schema=lespass` :
  le nombre de `CartePrimaire` avec `mode_recharge=True` égale le nombre de cartes distinctes
  filtrées par `points_de_vente__comportement="C"`. Noter les deux nombres pour le CHANGELOG.
- [ ] **Étape 6 : l'admin.** Ajouter `mode_recharge` à côté de `edit_mode` aux trois endroits.
- [ ] **Étape 7 : la démo.** `defaults={"edit_mode": True, "mode_recharge": True}`.
- [ ] **Étape 8 : vérifier que Django démarre.**
  Run : `docker exec lespass_django poetry run python manage.py check`
  Attendu : `System check identified no issues`.

---

### Tâche 2 : la règle, et la zone du check carte

**Fichiers :**
- Modifier : `laboutik/views.py:1292` (fonction de la règle), `:13899` (`retour_carte`)
- Modifier (textes seulement) : `laboutik/views.py:2626-2635`, `:2703`, `:13891-13897` ;
  `laboutik/templates/laboutik/partial/hx_card_recharge.html:20` ;
  `laboutik/templates/laboutik/partial/hx_check_card.html:27-29` ; `laboutik/models.py:836`
- Tests : `tests/pytest/test_retour_carte_recharge.py`

**Interfaces :**
- Consomme : `CartePrimaire.mode_recharge` (Tâche 1).
- Produit : `_carte_primaire_peut_recharger(tag_id_carte_primaire: str) -> bool` dans
  `laboutik/views.py`. `False` si le tag est vide ou si la carte est introuvable.

Ce fichier de tests écrit dans la base de dev sans rollback. Une fixture qui change la carte
du caissier la remet dans son état au démontage.

- [ ] **Étape 1 : la fixture.** Ajouter `carte_caissier_en_mode_recharge(point_de_vente,
  carte_caissier)` : passe `mode_recharge=True` sur la `CartePrimaire` du caissier (créée par
  `point_de_vente`), `yield`, puis remet `False`.
- [ ] **Étape 2 : adapter les tests de la zone (écrire les échecs).**
  - `test_retour_carte_avec_point_de_vente_affiche_les_tuiles_de_recharge` (ligne 303) :
    remplacer la fixture `point_de_vente_cashless_du_caissier` par
    `carte_caissier_en_mode_recharge`. Assertions inchangées.
  - Renommer le test de la ligne 349 en
    `test_retour_carte_avec_pv_cashless_mais_sans_mode_recharge_masque_la_recharge` : il prend
    `point_de_vente_cashless_du_caissier` (et pas le mode recharge), et garde
    `assert 'data-testid="recharge-produit-1"' not in contenu`.
  - `test_retour_carte_sans_carte_primaire_masque_la_recharge` (ligne 372) : remplacer
    `point_de_vente_cashless_du_caissier` par `carte_caissier_en_mode_recharge`.
  - Mettre à jour la docstring du fichier (règle, point 1).
- [ ] **Étape 3 : lancer, voir les échecs.**
  Run : `ulimit -v 8000000; timeout 900 make test ARGS="tests/pytest/test_retour_carte_recharge.py"`
  Attendu : les deux premiers tests ci-dessus échouent (l'ancienne règle regarde encore le
  point de vente Cashless).
- [ ] **Étape 4 : la règle.** Renommer la fonction en `_carte_primaire_peut_recharger` ; sa
  dernière ligne devient `return carte_primaire_obj.mode_recharge`. Réécrire sa docstring.
  Appeler la nouvelle fonction dans `retour_carte()`. Mettre à jour les textes listés dans
  « Fichiers ». Vérifier par `grep -rn "_carte_primaire_a_un_point_de_vente_cashless"` qu'il
  ne reste aucun appel.
- [ ] **Étape 5 : relancer.** Même commande. Attendu : tout passe, sauf les tests de paiement
  (lignes 538, 625, 656), qui ne sont pas encore touchés : ils passent aussi, la garde
  n'existe pas encore.

---

### Tâche 3 : les tuiles de recharge de la grille

**Fichiers :**
- Modifier : `laboutik/views.py:674` (`_construire_donnees_articles`), `:725-731`, `:3617`
  (`point_de_vente()`)
- Tests : `tests/pytest/test_caisse_ecrit_la_vente.py`

**Interfaces :**
- Consomme : `CartePrimaire.mode_recharge`.
- Produit : `_construire_donnees_articles(point_de_vente_instance, events_billetterie=None,
  afficher_les_recharges=False)`.
- Produit (aides de test, dans `test_caisse_ecrit_la_vente.py`) :
  - `html_de_la_grille_de_la_caisse(client_du_caissier, point_de_vente, tag_id_cm=None)` :
    envoie aussi `tag_id_cm` s'il est donné ;
  - `tag_de_la_carte_primaire_du_caissier(point_de_vente, mode_recharge=False)` : crée la
    carte primaire avec ce `mode_recharge`.

- [ ] **Étape 1 : les aides de test.** Ajouter les paramètres ci-dessus, valeurs par défaut
  qui gardent le comportement actuel des appelants.
- [ ] **Étape 2 : écrire les tests.** Une recharge euros (`creer_un_article_de_caisse(...,
  methode_caisse=Product.RECHARGE_EUROS, asset=monnaie_locale_du_lieu(lieu))`) dans un point
  de vente (`creer_un_point_de_vente([recharge.produit])`).
  - `test_tuile_de_recharge_visible_avec_le_mode_recharge` :
    `assert la_tuile_du_produit_est_affichee(html, recharge.produit)` avec une carte en mode
    recharge.
  - `test_tuile_de_recharge_masquee_sans_le_mode_recharge` :
    `assert not la_tuile_du_produit_est_affichee(html, recharge.produit)` avec une carte sans
    mode recharge.
- [ ] **Étape 3 : lancer, voir l'échec** du test « masquée ».
  Run : `ulimit -v 8000000; timeout 900 make test ARGS="tests/pytest/test_caisse_ecrit_la_vente.py -k tuile_de_recharge"`
- [ ] **Étape 4 : le code.** Le paramètre `afficher_les_recharges` ; dans le bloc des lignes
  725-731, sauter la recharge aussi si `not afficher_les_recharges`. Dans `point_de_vente()`,
  passer `afficher_les_recharges=carte_primaire_obj is not None and carte_primaire_obj.mode_recharge`.
  Pas de requête en plus.
- [ ] **Étape 5 : relancer.** Attendu : les deux tests passent.
- [ ] **Étape 6 : mutation.** Forcer `afficher_les_recharges=True` dans `point_de_vente()` :
  le test « masquée » doit échouer. Retirer la mutation.

---

### Tâche 4 : la garde serveur, et les tests existants à adapter

**Fichiers :**
- Modifier : `laboutik/views.py` dans `_extraire_articles_du_panier` (ligne 6591, après le
  refus de la recharge temps, vers la ligne 6716) ; `ouvrir_commande()` (ligne 15131)
- Tests : `tests/pytest/test_retour_carte_recharge.py`, `tests/pytest/test_caisse_ecrit_la_vente.py`,
  puis les fichiers de la spec §5.2

**Interfaces :**
- Consomme : `_carte_primaire_peut_recharger` (Tâche 2), `tag_de_la_carte_primaire_du_caissier`
  (Tâche 3).
- Produit : `_extraire_articles_du_panier` lève `ValueError` avec le message des contraintes
  globales quand le panier contient une recharge et que `tag_id_cm` ne donne pas le droit.

- [ ] **Étape 1 : écrire les tests de refus**, dans `test_retour_carte_recharge.py`, sur le
  modèle des tests des lignes 538 et 656, **sans** la fixture `carte_caissier_en_mode_recharge` :
  - `test_payer_une_recharge_sans_mode_recharge_refuse` : `reponse_paiement.status_code == 400`,
    le message de refus est dans la réponse, le solde local reste 0, et aucune nouvelle
    `LigneArticle` pour `produit_local` (compter avant et après).
  - `test_offrir_une_recharge_sans_mode_recharge_ne_credite_rien` : le solde cadeau reste 0.
  - Ajouter `carte_caissier_en_mode_recharge` aux tests des lignes 538, 625 et 656 : ils
    doivent continuer à créditer.
- [ ] **Étape 2 : écrire les tests du mélange et de la table**, dans `test_caisse_ecrit_la_vente.py` :
  - `test_recharge_et_adhesion_meme_panier_acceptees` : une recharge euros et une adhésion
    (`creer_adhesion(prix="5.00")`) dans le même point de vente. Appel direct de
    `_extraire_articles_du_panier` avec un `QueryDict` (modèle :
    `test_caisse_une_ligne_par_article.py:1555`) qui contient les deux `repid-` et le
    `tag_id_cm` d'une carte en mode recharge. `assert len(articles_du_panier) == 2`.
  - `test_recharge_sans_mode_recharge_refusee_par_le_panier` : même appel, recharge seule,
    carte sans mode recharge. `pytest.raises(ValueError)`.
  - `test_commande_de_table_ignore_la_recharge` : POST vers `ouvrir_commande` avec une
    recharge et une bière (lire la vue, vers la ligne 15060, pour le format du POST). La
    commande créée ne contient que la bière.
- [ ] **Étape 3 : lancer, voir les échecs.**
  Run : `ulimit -v 8000000; timeout 900 make test ARGS="tests/pytest/test_retour_carte_recharge.py tests/pytest/test_caisse_ecrit_la_vente.py"`
  Attendu : les tests de refus et de la table échouent ; le test du mélange passe déjà.
- [ ] **Étape 4 : la garde.** Le bloc de la spec §2.7a, dans la boucle, après le refus de la
  recharge temps. Le `.exclude(methode_caisse__in=METHODES_RECHARGE)` de la spec §2.7b. Ne
  pas toucher au `except (PointDeVente.DoesNotExist, ValueError): pass` de
  `identifier_client()`.
- [ ] **Étape 5 : relancer.** Attendu : les nouveaux tests passent. Les tests de
  `test_caisse_ecrit_la_vente.py` qui vendent une recharge sans `tag_id_cm` échouent
  (environ 7) : c'est l'étape suivante.
- [ ] **Étape 6 : adapter les tests existants.** Règle unique : un test qui vend une recharge
  par les vues crée une carte primaire **en mode recharge** sur son point de vente et envoie
  son `tag_id_cm`. Dans `test_caisse_ecrit_la_vente.py`, par
  `tag_de_la_carte_primaire_du_caissier(point_de_vente, mode_recharge=True)` ; ailleurs, avec
  la fabrique locale du fichier. Ne changer aucune assertion. Fichiers : la liste de la spec
  §5.2. Un test qui casse pour une autre raison : s'arrêter et le signaler.
- [ ] **Étape 7 : relancer les fichiers de la spec §5.2,** un appel `make test` avec tous les
  fichiers. Attendu : tout passe.
- [ ] **Étape 8 : mutations.** (a) Mettre `if False and produit.methode_caisse in
  METHODES_RECHARGE:` : les tests de refus échouent. (b) Retirer le `.exclude(...)` : le test
  de la table échoue. Retirer les mutations.

---

### Tâche 5 : documentation, E2E, vérification finale

**Fichiers :**
- Créer : `CHANGELOG/2026-11-24-recharge-mode-recharge.md`
- Modifier : `TECH_DOC/SESSIONS/RECHARGE_CAISSE/INDEX.md` (statut)

- [ ] **Étape 1 : CHANGELOG**, sur le modèle de `CHANGELOG/2026-11-24-article-caisse-methode-vente-figee.md`.
  `Migration : Oui`. Tests à la main :
  1. Admin > Caisse > Cartes primaires : la case « Mode recharge » est là.
  2. Carte sans la case : check carte sans zone « Recharger », point de vente Cashless sans
     tuile de recharge.
  3. Cocher la case : la zone et les tuiles reviennent ; une recharge + une adhésion passent.
  4. Contrôle de la migration (les deux nombres de la Tâche 1, étape 5).
  Ajouter l'ordre de déploiement (spec, fin du §6) et la liste des nouvelles chaînes i18n
  (verbose_name, help_text, message de refus, textes modifiés).
- [ ] **Étape 2 : lint des fichiers touchés.**
  Run : `docker exec lespass_django poetry run ruff check laboutik/views.py laboutik/models.py laboutik/migrations/0003_carteprimaire_mode_recharge.py Administration/admin/laboutik.py`
  Attendu : pas d'erreur **nouvelle**. Les fichiers ont déjà des erreurs : seules comptent
  celles des lignes modifiées (comparer avec `git diff`).
- [ ] **Étape 3 : E2E.** Lancer les 4 fichiers E2E de la spec §5.2. Attendu : tout passe
  avec la carte de démo (elle a `mode_recharge`). Un E2E en échec : le signaler, ne pas le
  « réparer » sans comprendre.
- [ ] **Étape 4 : suite complète, sur accord du mainteneur seulement.**
- [ ] **Étape 5 : rapport au mainteneur** (format du skill `djc`) et proposition de message
  de commit. Pas de commit.
