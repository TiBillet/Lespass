# Caisse — Mode gérant à deux niveaux, et tag NFC jamais dans une URL

> **Status :** idée posée, **spec à écrire** (session dédiée). Rien n'est codé.
> **Date :** 2026-09-28 (constats et décisions du mainteneur en fin de chantier 04-E).
> **Pré-requis :** aucun. Les deux parties se touchent (la carte primaire identifiée
> par la caisse) : les spécifier ensemble, livrer la partie B d'abord ou en même temps.

## A. Mode gérant à deux niveaux (tuile OFFRIR)

### Aujourd'hui (vérifié dans le code)
- `CartePrimaire.edit_mode` (`laboutik/models.py`, « Edit mode ») fait apparaître OFFRIR :
  `laboutik/views.py` `_panier_peut_etre_offert()` (lu en base) ; aussi transmis à
  l'interface (`card_dict["mode_gerant"]`, ~l.287, ~l.2428, ~l.4365) pour les pouvoirs
  d'édition (produits, prix depuis la caisse).
- Le bouton « Paramètres » du bandeau (`laboutik/templates/cotton/header.html` ~l.90,
  `data-dest="parametres"`) n'est branché à rien ; le sous-menu « Paramètres » du menu
  burger (~l.179) est un brouillon (« params 1 », « params 2 »).

### Décisions du mainteneur (2026-09-28)
1. Le mode gérant est un mode **à part**, distinct du mode édition (`edit_mode` ne joue
   plus aucun rôle pour OFFRIR).
2. **Deux booléens** sur `CartePrimaire`, faux par défaut :
   - « mode gérant autorisé » : réglé dans l'**admin**, visible dans la **vue liste** ;
   - « mode gérant activé » : allumé / éteint **à la caisse** (menu Paramètres) ; l'option
     n'apparaît à la caisse que si le mode est autorisé dans l'admin.
3. La tuile OFFRIR (et la garde serveur du moyen « gift ») exige **les deux** booléens.
   Ces booléens ne conditionnent **que** OFFRIR.
4. Menu « Paramètres » de la caisse (bouton `data-dest="parametres"` et entrée du menu
   burger) : l'interrupteur « Mode gérant » + les **infos de la carte primaire**
   (numéro imprimé, points de vente accessibles). **Jamais le tag NFC à l'écran** :
   uniquement le numéro imprimé (`CarteCashless.number`).

### À préciser dans la spec
- Noms des champs, migration, données de démo (`create_test_pos_data` : carte de démo
  autorisée, mode non activé ?).
- Le mode activé reste-t-il allumé après la fermeture de la caisse / une clôture ?
- Tests des fiches 04-D et 04-E à adapter (`_carte_primaire(mode_gerant=...)` pose
  aujourd'hui `edit_mode`).

## B. Le tag NFC ne circule jamais dans une URL (POST ou session uniquement)

### Constat (2026-09-28)
Le tag NFC sert d'identifiant : celui de la **carte primaire** donne l'accès aux points
de vente, le mode édition (et bientôt OFFRIR) ; celui d'une **carte client** permet de
payer avec son solde (avec, en plus, une session de terminal connectée).

- **Carte primaire** : `tag_id_cm` est dans les chaînes de requête de la navigation de
  la caisse : 8 liens dans les gabarits (`cotton/header.html`, `views/tables.html`,
  `partial/hx_choose_pv.html`, `partial/_hdr_retour_zone.html`…), 4 fichiers JS, 5 vues
  qui le lisent en `GET`. Cinq liens sont des `href` ou des `hx-push-url` : le tag
  s'affiche dans la **barre d'adresse** et reste dans l'**historique du navigateur**.
- **Carte client** : « Check carte → Recharger »
  (`partial/hx_card_recharge.html`, 5 `hx-get … ?tag_id=`, lu en `GET`
  `laboutik/views.py` ~l.10434).
- **Logs** : le format nginx de prod (`nginx_prod/lespass_bascule.conf`, `log_format
  tibillet`) enregistre `$request_uri` (chaîne de requête comprise) et le `Referer` : les
  tags finissent dans les **logs d'accès**.

### Piste
- Après le scan de la carte primaire, la garder **côté serveur dans la session Django**
  (uuid de la `CartePrimaire`) ; les vues la lisent en session, `tag_id_cm` disparaît des
  URL, des formulaires et du JS.
- Le tag d'une carte client ne passe que dans le **corps d'un POST**.
- Nettoyer les logs existants ; vérifier les autres journaux (Sentry, logs applicatifs
  `logger.info` qui écrivent un tag).
- Toucher : navigation, toutes les vues de paiement (`tag_id_cm`, `tag_id`), JS de lecture
  NFC (`nfc.js`, `SendTagIdAndSubmit`), fixtures E2E (`pos_page` ouvre la caisse avec
  `?tag_id_cm=`).
