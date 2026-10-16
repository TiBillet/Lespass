# Chantier 06-D — Les ventes de TiBillet dans Dolibarr (mode « articles et ventes »)

> **Statut** : ✅ **CODÉE le 2026-10-16, non commitée** (§11 : tests, mutations, import réel). Spec
> validée le même jour (§9). Plan : [`CHANTIER-06-D-PLAN.md`](CHANTIER-06-D-PLAN.md). Relue par Fable le même
> jour : 2 bloquants et 8 points appliqués (§10).
> Suite de [`06-C`](CHANTIER-06-C-catalogue.md) (le catalogue). Contexte : [`README.md`](README.md)
> du chantier 06 (§5 R6/R7, §12), fiches [`06-A`](CHANTIER-06-A-api-comptable.md) (l'API des
> clôtures) et [`06-B`](CHANTIER-06-B-module-dolibarr.md) (le module).
> Code lu le 2026-10-15 (Lespass `main` 866e0e06, Dolibarr 24.0.1 du conteneur de dev).
> **Revérifier les numéros de ligne avant de coder.**
> Migration Lespass : **non** prévue. Module : **une table** de plus (§6.2).

---

## 1. Le but, en une phrase

En mode « articles et ventes », **chaque nuit**, Dolibarr va chercher chez TiBillet les
**ventes de la journée clôturée** (billetterie, adhésions, ressources, caisse, tireuse) et
les range en **factures payées**. Un acheteur connu devient un **tiers** Dolibarr. Une vente
au bar sans acheteur connu va sur un **tiers « client de passage »**, comme la caisse
native de Dolibarr (TakePOS).

## 2. Expliqué simplement (FALC)

- Chaque soir, TiBillet ferme la journée : c'est la **clôture J** (le « Z »). Elle est
  scellée. Ses ventes ne bougent plus jamais.
- La nuit, Dolibarr demande à TiBillet : « donne-moi les ventes de la journée suivante ».
  Il les reçoit **déjà calculées** : prix, TVA, compte de vente, moyens de paiement,
  acheteur. Dolibarr ne recalcule aucune règle comptable.
- Pour **chaque vente** TiBillet, Dolibarr crée **une facture**, la valide, et enregistre
  son **paiement** sur le bon compte bancaire (caisse, CB, Stripe, monnaie locale…).
- **Un remboursement** dans TiBillet devient un **avoir** dans Dolibarr.
- **Une recharge de carte cashless** n'est pas une vente : c'est de l'argent gardé pour le
  client. Elle devient un **virement interne** : l'argent passe de la banque « monnaie
  locale » à la caisse (ou à la CB). Sans ça, la caisse de Dolibarr ne verrait jamais
  l'argent des recharges.
- Une journée arrive **en entier, ou est reprise au même endroit** la nuit suivante. Une
  vente n'arrive **jamais deux fois**.
- Une journée est importée **soit** en écritures (mode « écritures »), **soit** en
  factures (mode « articles et ventes »). Jamais les deux.

## 3. Ce qu'on sait déjà (lu le 2026-10-15)

### Côté TiBillet

- **`Vente`** (`BaseBillet/models_vente.py:50`) regroupe les articles d'un passage en
  caisse ou d'un panier. `numero` est unique, **sans trou**, posé à l'encaissement (l.85).
  `nature` : VENTE, AVOIR, VIDAGE_CARTE, CORRECTION (l.66-73). `statut` : EN_ATTENTE,
  REGLEE, ANNULEE. `client` (TibilletUser, SET_NULL, l.136), `carte` (l.144), `vente_liee`
  (l.154), totaux en centimes, `datetime_encaissement` (l.175), `unite` ("EUR" ou une
  monnaie de points, l.109). Une vente REGLEE ne se modifie plus (l.256-284).
- **`LigneArticle`** (`BaseBillet/models.py:4289`) : un article. Centimes entiers :
  `total_catalogue`, `part_offerte`, `part_en_jetons`, `total_ttc`, `total_ht`,
  `total_tva` (l.4427-4521), `qty` Decimal (négative dans un avoir), `vat`, `pricesold`
  → `price` (le tarif), `credit_note_for` (l.4363). **L'arrondi se fait par ligne**
  (`calculer_montants_article`, `BaseBillet/services_vente.py:148`, demi-haut) ; le FEC
  additionne les lignes sans recalculer.
- **`Reglement`** (`models_vente.py:287`) : un paiement de la vente (`moyen`, `montant`
  signé, `asset`, `carte`). Il n'est **pas** relié à une ligne. Le « payé comment » d'une
  vente : `reglements_nets_de_la_vente` (`laboutik/affichage_des_ventes.py:244`), qui
  ajoute les ventes CORRECTION dérivées. Le moyen écrit sur la ligne est **vide** pour la
  caisse, la tireuse et le QR, et disparaît en H-2 : **ne jamais le lire**.
- **Toutes les sources** passent par `ouvrir_vente` → `ajouter_article` →
  `ajouter_reglement` → `encaisser_vente` (`services_vente.py:326`, `401`, `1726`, `1810`) :
  panier en ligne, billets, adhésions (en ligne, admin, caisse), ressources
  (`booking/booking_engine.py:723`), crowds, caisse, tireuse
  (`controlvanne/billing.py:710`), QR/NFC.
- **L'acheteur** : `Vente.client`, rempli pour les ventes en ligne, les ressources, et en
  caisse quand une carte liée à un user est lue ou un adhérent identifié
  (`laboutik/views.py:8646-8650`, `10794-10796`). Toutes les fabriques recopient
  `carte.user` dans `client` **au moment de la vente** (aussi `controlvanne/billing.py:714`,
  `BaseBillet/views.py:2235`). Une boisson payée en **espèces ou CB** au
  bar : `client=None` et `carte=None` (la carte n'est lue que pour une recharge). Une carte
  anonyme n'a pas de user (`QrcodeCashless/models.py:72`).
- **La clôture J** (`comptabilite/models.py:31`) couvre les ventes REGLEE dont le
  `numero` est entre `numero_premiere_vente` et `numero_derniere_vente` (plage contiguë,
  posée sous le même verrou que la numérotation). Les ventes **en ligne** y sont aussi.
  Une CORRECTION est refusée si la vente est déjà dans une J (`laboutik/integrity.py:119`) :
  elle est donc toujours encaissée **avant que la J de la vente existe**, donc avant tout
  import. Elle tombe presque toujours dans la même J, mais pas forcément : la J est posée
  en trois temps (`comptabilite/tasks.py:455-520`) et une correction faite pendant le
  calcul du rapport tombe dans la J suivante. La plage d'une J contient **toutes les
  natures et unités** (VENTE, AVOIR, CORRECTION, VIDAGE, points), mais seulement des
  ventes REGLEE (`comptabilite/rapport.py:452-462`).
- **L'API des clôtures** existe : `ClosureViewSet` (`api_v2/views.py:1546`, droit
  `comptabilite`, clé seule) : `list` (`?after_number=`), `entries`, `fec`. Les J
  « reprise » et d'avant la mise en service sont refusées (`journees_a_importer`,
  `comptabilite/tasks.py:742`).
- **`/api/v2/sales/` ne convient pas** : une ligne par article, filtre sur la date de
  **création** de la ligne, `payment_method` de la ligne, uuid du **produit** (pas du
  tarif), sans pagination, droit lié à un **admin humain** (la clé tombe en panne s'il
  part). Elle reste telle quelle (`TODO/API-v2-ventes-reglements.md` reste ouvert pour
  elle).
- **Date d'une J** : le FEC date toute la J au **début de service**
  (`comptabilite/ventilation.py:494-505`) ; `/closures/` publie `accountingDate`.
- **Recharge offerte** (bouton OFFRIR) et **jetons cadeau repris** au vidage : règlement
  `NA` ou `LG`, et une écriture 623400 / 419100 dans le FEC
  (`comptabilite/ventilation.py:233-273`).
- **Comptes** : `compte_pour_produit`, `taux_de_tva_du_produit`,
  `est_une_vente_pour_la_comptabilite` (06-C) ; `compte_pour_reglement`
  (`laboutik/plan_comptable.py:421-484`, compte de la **monnaie** — une monnaie d'un autre
  lieu a son propre compte — ou `MappingMoyenDePaiement`) ; TVA :
  `compte_de_tva_pour_taux` (l.993, un compte par taux : 445711/712/713/714) ;
  jetons cadeau : `compte_des_ventes_reglees_en_jetons` (707900, l.361).
- **Données de l'acheteur** : `TibilletUser` (`AuthBillet/models.py:124-143`) : `id`
  (uuid, stable), `email` (modifiable), `first_name`, `last_name`, `phone`, `postal_code`.
  Pas d'adresse postale.

### Côté Dolibarr 24 (conteneur `dolibarr-dev-dolibarr-1`, `/var/www/html`)

- **Facture** (`compta/facture/class/facture.class.php`) : `create` exige `socid` et
  `date` (l.537-543) ; `addline` en TTC = `$pu_ht=0, $price_base_type='TTC', $pu_ttc`
  (l.4344) ; 11ᵉ paramètre `$fk_code_ventilation` = rowid du compte comptable : **la ligne
  est liée d'avance** (l.4472). `validate` numérote `MAX+1` (`mod_facture_terre`), fige la
  facture. `ref_ext` existe mais **sans index**.
- **Avoir** : `type = TYPE_CREDIT_NOTE` (2), `fk_facture_source`, préfixe AV.
- **Paiement** (`compta/paiement/class/paiement.class.php`) : `create` (l.309), puis
  `addPaymentToBank` (l.798, **utilise le `$user` global**), puis `setPaid`. Régénère le
  PDF de la facture sauf `MAIN_DISABLE_PDF_AUTOUPDATE` (l.618-650).
- **Paiement divers** (`compta/bank/class/paymentvarious.class.php`) : une ligne de banque
  sans facture, avec `accountancy_code` (contrepartie), `sens`, `fk_account`. Le journal
  de banque l'écrit (`bankjournal.php:637`).
- **Compte bancaire** : un compte de **caisse** (type 2) n'accepte que `LIQ`
  (`account.class.php:669-672`). `account_number` = compte comptable de la banque ;
  `fk_accountancy_journal` obligatoire pour le journal de banque. `c_paiement.accountancy_code`
  remplace le compte de la banque si rempli (`bankjournal.php:311-316`).
- **Tiers** (`societe/class/societe.class.php:1003`) : `name` + `client=1`, code client
  auto, `ref_ext`, `email`, `fk_typent` = TE_PRIVATE pour un particulier. `fetch` par
  e-mail renvoie **-2** s'il y a des doublons (l.2063). Aucun index sur `ref_ext` ni
  `email`.
- **TakePOS** : un tiers générique par terminal (`CASHDESK_ID_THIRDPARTY{n}`), un compte
  bancaire par mode (`CASHDESK_ID_BANKACCOUNT_*`), enchaînement
  `validate` → `Paiement::create` → `addPaymentToBank` → `setPaid`
  (`takepos/invoice.php:420-470`). `module_source='takepos'` change la numérotation (TC…)
  et le journal : **à ne pas reprendre**.
- **Comptabilité** : le journal des ventes ne prend que les lignes liées
  (`fk_code_ventilation > 0`) ; **une ligne non liée bloque toute la facture**
  (`sellsjournal.php:540-552`). Il exige `ACCOUNTING_ACCOUNT_CUSTOMER` (411). Aucune tâche
  planifiée n'écrit les journaux : c'est le comptable qui clique « Écrire ».
- **TVA dans le journal des ventes** : le compte vient de `c_tva.accountancy_code_sell` du
  **taux actif** (taux + pays), sinon d'un compte unique `ACCOUNTING_VAT_SOLD_ACCOUNT`
  (`sellsjournal.php:241-294`). En dev : aucun compte sur `c_tva`, le 8,5 % est
  **inactif**, `ACCOUNTING_VAT_SOLD_ACCOUNT` absent.
- **Types de paiement** : `Paiement::create` et `PaymentVarious::create` exigent un code
  `c_paiement`. Actifs en dev : VIR, PRE, LIQ, CB, CHQ (VAD inactif).
- **Un tiers supprimé à la main** : `Facture::create` accepte un `fetch` qui rend 0
  (l.541-547) → facture orpheline, jamais reprise par le journal, **sans erreur**.
- **Arrondis** : saisie TTC → HT = TTC/(1+taux) arrondi, TVA = TTC − HT : **même formule
  que TiBillet**. Mais `update_price` recalcule depuis le PU HT (5 décimales) et peut
  corriger un centime sur une **grosse quantité** (ex. 999 × 0,64 € à 5,5 %).
- **Coût** : ~40 à 60 requêtes par facture payée (estimé, à mesurer), plus un PDF par
  paiement si on ne le coupe pas. Tâche cron : 600 s au plus par défaut
  (`MAIN_CRON_EXEC_TIME_LIMIT`).

## 4. Décisions proposées (à valider)

| # | Sujet | Proposition | Pourquoi |
|---|---|---|---|
| D0 | Quand | **Une fois par jour, depuis Dolibarr**, jamais en temps réel : la tâche planifiée du module (heure réglable, **06:00 par défaut**, après la clôture J automatique de TiBillet à fermeture + 2 h) ou le bouton de la page. Seules les J clôturées sont lues | Décision du mainteneur (2026-10-16). TiBillet ne dépend pas de Dolibarr (R2) |
| D1 | Unité d'import | **La J clôturée**, comme le mode écritures. Le module suit les J par `numero_sequentiel` (`after_number`) | Les ventes d'une J sont scellées et ne changent plus. Même curseur, même rattrapage qu'en 06-B. Une CORRECTION est encaissée avant que la J existe : au moment de l'import, le « payé comment » est définitif |
| D2 | Route | **`GET /api/v2/closures/<uuid>/sales/`**, une action de plus sur `ClosureViewSet`, à côté de `entries` et `fec`. Pas de nouvelle route racine, `/sales/` n'est pas touchée | Réutilise le droit, les refus (`not_exportable`, mise en service) et le curseur de 06-A |
| D3 | Facture | **Une facture Dolibarr par vente TiBillet** (nature VENTE, statut REGLEE, en euros), `ref_ext` = uuid de la vente, numéro TiBillet dans la note | Traçable : une facture = un ticket. Un avoir pointe sur sa facture. Quantités petites : pas de risque de centime. C'est aussi ce que fait TakePOS |
| D4 | Acheteur | **`Vente.client` seul**, sinon **client de passage**. Jamais `Vente.carte.user` lu à l'import | Les fabriques recopient déjà `carte.user` dans `client` au moment de la vente. Lire la carte **aujourd'hui** donnerait une vente anonyme d'hier à celle ou celui qui a pris la carte depuis |
| D5 | Tiers d'un acheteur | Retrouvé **par e-mail** (Q3), sans majuscules, dans l'entité ; plusieurs → le plus ancien ; aucun → créé : nom = l'e-mail (Q4), e-mail, particulier (`TE_PRIVATE`), client, `ref_ext` = `tibillet:user:<uuid>`. Jamais modifié ensuite | Choix du mainteneur : l'e-mail est la clé. Le lieu peut compléter la fiche à la main sans qu'on l'écrase. Pas d'index sur `email` : une requête par vente, acceptable la nuit |
| D6 | Client de passage | **Un tiers « Client de passage TiBillet »** créé par le module (`ref_ext = tibillet:client-de-passage`), son id dans `TIBILLET_TIERS_DE_PASSAGE`. Le lieu peut en choisir un autre sur la page du module | Comme `CASHDESK_ID_THIRDPARTY` de TakePOS |
| D7 | Lignes | Seules les lignes **vendues** (`est_une_vente_pour_la_comptabilite`) vont dans la facture, au **produit du tarif** (06-C), **liées d'avance** au compte publié par TiBillet (`fk_code_ventilation`) | Le comptable n'a rien à « lier ». Une ligne non liée bloquerait toute la facture |
| D8 | Montant d'une ligne | Saisie **TTC**. Quantité × prix unitaire si Dolibarr retombe exactement sur le `total_ttc` de TiBillet ; sinon (offert partiel, poids, écart) **une ligne de quantité 1** au `total_ttc`, la vraie quantité dans le libellé. Après validation : total TTC Dolibarr = total TiBillet au centime, sinon la vente est refusée | Le centime de TiBillet fait foi (il est scellé dans la J) |
| D9 | Jetons cadeau | La part payée en jetons (`part_en_jetons`) devient **une ligne à part**, TVA 0, compte 707900 | C'est ce que fait le FEC (D26 du chantier 05) |
| D10 | Paiements | Un **paiement Dolibarr par compte de trésorerie** (règlements **nets**, avec **toutes** les CORRECTION dérivées, quelle que soit leur J : `reglements_nets_de_la_vente`). Offert (`NA`) : pas de paiement (la ligne est déjà nette). La facture finit **payée** | Comme TakePOS |
| D11 | Comptes bancaires | **Un compte bancaire Dolibarr par compte de trésorerie publié** par TiBillet (`compte_pour_reglement` : espèces 530, CB 512…, monnaie locale 419100, monnaie d'un voisin 419200), créé par le module s'il manque, avec ce compte (`account_number`) et le journal BQ (`fk_accountancy_journal`). 530 = compte de caisse (type 2), les autres = compte courant. Le lieu peut relier un compte à une autre banque ; la page **refuse une banque de caisse** pour autre chose que les espèces | Mêmes comptes que le FEC, monnaies voisines comprises. Un compte de caisse n'accepte que `LIQ` (`account.class.php:670`) |
| D12 | Recharges, vidages et autres mouvements | **Recharge = virement interne** de la banque de la monnaie (419100) **vers** la banque du moyen (caisse, CB…) ; **vidage** = l'inverse (Q11). Comme `compta/bank/transfer.php` : deux `Account::addline` (l.188, 194), en `LIQ` si l'un des comptes est une caisse (l.183), reliés par `add_url_line(…, 'banktransfert')` (l.201, 207). Le journal de banque passe par `ACCOUNTING_ACCOUNT_TRANSFER_CASH` (58), soldé à chaque mouvement : net = D banque du moyen / C 419100, comme le FEC. **Recharge offerte** : paiement divers en sortie sur la banque de la monnaie, contrepartie 623400. **Jetons repris** : paiement divers en entrée sur la banque des jetons, contrepartie 623400. **Écarts d'encaissement** : paiement divers, contrepartie 758 / 658 (Q5). **Pas de facture** | Sinon l'argent des recharges n'entre jamais dans Dolibarr. Résultat compte par compte = FEC, et le solde de la banque de la monnaie a un sens |
| D13 | Remboursement | Une vente AVOIR → un **avoir** Dolibarr sur le même tiers, `fk_facture_source` = facture de la vente liée si elle est dans Dolibarr. Paiement **négatif** par moyen | La vente liée peut être dans une J plus ancienne, voire d'avant le mode « ventes » : l'avoir reste alors seul |
| D14 | Une vente à moitié recharge | TiBillet **répartit** les règlements : les recharges sont payées en premier par les moyens en euros réels (espèces, CB, chèque, Stripe), dans l'ordre des règlements ; le reste paie la facture. Il publie les deux parts | Un règlement n'est relié à aucune ligne. La règle vit en Python, une seule fois |
| D15 | Écartées | Ventes en points (`unite` ≠ EUR, comme le FEC), ventes CORRECTION (déjà comptées dans les nets), ventes **sans montant** : aucune ligne à facturer avec un `total_ttc` ≠ 0 **et** aucun mouvement. Une ligne à 0 € (bière offerte) ne va pas dans la facture. Lignes « écart d'encaissement » : paiement divers (Q5) | |
| D16 | Tout ou rien | **Une transaction par vente.** Une table du module retient les ventes importées (index unique sur l'uuid). Une J est marquée importée quand toutes ses ventes le sont. Si le temps manque, la nuit suivante reprend à la vente suivante. **Une vente refusée arrête tout le passage** (pas seulement sa J) ; la nuit suivante reprend **à cette vente** | Une J de festival peut compter des milliers de ventes : une seule transaction serait trop longue (600 s). Passer à la J suivante numéroterait ses factures avant celles de la J bloquée |
| D17 | Une J, un mode | La table des J importées note le **mode** (`ecritures` / `ventes`). Une J déjà importée dans un mode n'est **jamais** importée dans l'autre. Au passage en mode ventes, l'import part de la **première J non importée** | Garde anti-double-compta au niveau de la journée, pas seulement du réglage |
| D18 | Vitesse | Pendant le passage, **en mémoire seulement** : `MAIN_DISABLE_PDF_AUTOUPDATE=1` (pas de PDF par paiement). Pas de limite par défaut : le passage suit la pagination de TiBillet jusqu'au bout. La constante facultative `TIBILLET_VENTES_PAR_PASSAGE` coupe le passage (la suite au passage suivant, et la page le dit) pour un serveur qui tue PHP trop tôt | Le PDF est le plus lent. Ne change pas le réglage du lieu. Révisée le 2026-10-16 : 2000 par défaut était trop prudent (~22 ms par vente mesurées, 2000 ventes ≈ 45 s ; une J de 10 000 ventes aurait mis 5 nuits). Sous Linux, `max_execution_time` ne compte pas l'attente de la base |
| D19 | Droits | Pour `/closures/<uuid>/sales/` : `comptabilite` **et** `sale` sur la clé, vérifiés dans l'action. `get_apikey_valid` n'est pas touché (B1 de 06-C) | Elle publie des données personnelles (nom, e-mail) : un droit de plus que les écritures |
| D20 | Contrôles au démarrage | « Tester la connexion » en mode ventes vérifie aussi : modules Factures, Tiers, Banque actifs ; `ACCOUNTING_ACCOUNT_CUSTOMER`, `ACCOUNTING_VAT_SOLD_ACCOUNT` et `ACCOUNTING_ACCOUNT_TRANSFER_CASH` remplis ; un taux de TVA **actif** pour chaque taux du catalogue (D21) ; les codes de paiement de D22 actifs, sans `accountancy_code` ; `FAC_FORCE_DATE_VALIDATION`, `INVOICE_CHECK_POSTERIOR_DATE` et `STOCK_CALCULATE_ON_BILL` **éteints** ; l'utilisateur du cron a `facture->creer` | Chacun casse l'import ou change les dates |
| D21 | Comptes de TVA | `sales/` publie par ligne `vatAccountingAccount` (`compte_de_tva_pour_taux`). Le module écrit ce compte dans `c_tva.accountancy_code_sell` (taux et pays du lieu) et **active** le taux s'il est inactif (8,5 % à La Réunion) | Sinon Dolibarr range toute la TVA dans un seul compte, ou refuse d'écrire le journal. Le FEC a un compte par taux |
| D22 | Types de paiement | Table fixe : espèces → `LIQ`, CB au terminal → `CB`, chèque → `CHQ`, virement → `VIR`, Stripe (carte, SEPA, abonnement) → `VAD` (activé par le module), monnaies et jetons (LE, LG, SF) → un code **`TIB`** créé par le module (« Monnaie TiBillet »). Le compte comptable reste celui de la **banque** (D11) | `Paiement` et `PaymentVarious` exigent un code ; un `accountancy_code` sur le code remplacerait le compte de la banque |
| D23 | Date | Factures, paiements et paiements divers datés de l'**`accountingDate` de la J**, à midi (convention du module) | Identique au FEC : une soirée qui passe minuit reste dans le même mois de TVA. Un virement rattrapé n'est pas daté dans le passé |
| D24 | Numéro déjà pris | Si `validate` ou `Paiement::create` échoue sur l'index unique de la référence (un humain a validé au même instant), le module **réessaie une fois** la vente | `MAX+1` sans verrou (`mod_facture_terre.php:232`) |

## 5. Côté TiBillet

### 5.1 `GET /api/v2/closures/<uuid>/sales/?after_number=<n>&limit=<m>`

- Mêmes refus que `entries` : 404 `not_exportable` (J reprise, avant la mise en service,
  pas de plage de ventes). Droit (D19) : 403 si `comptabilite` ou `sale` manque.
- Les ventes **REGLEE**, `unite="EUR"`, `numero` dans la plage de la J et `> after_number`,
  triées par `numero`, `limit` 500 par défaut (1000 au plus). `nextAfterNumber` dans la
  réponse, vide à la fin. `select_related` / `prefetch_related` : pas de N+1.
- Rendu sous `translation.override("fr")` (comme le catalogue). Montants en **centimes**
  (`"amountUnit": "cent"`, comme `entries`).
- Pour chaque vente (vocabulaire schema.org `Order`, détail des noms en code) :
  - `identifier` (uuid), `orderNumber` (numéro de vente), `orderDate`
    (`datetime_encaissement`), nature (`sale` / `refund` / `card_emptying`), origine,
    point de vente, vente liée (uuid + numéro) pour un avoir ;
  - `customer` : `null` (client de passage) ou `{identifier (uuid user), email}` (D4,
    Q4 : rien d'autre) ;
  - `orderedItem` : les lignes **à facturer** (D7, D9) : `priceIdentifier` (uuid du tarif =
    `ref_ext` du produit Dolibarr), libellé « Produit — Tarif », quantité, prix unitaire
    TTC, `totalTTC`, `totalHT`, `totalVAT`, `vatRate`, `vatAccountingAccount` (D21),
    `accountingAccount` (ou
    `accountingAccountError` : la vente est alors refusée côté module, avec la phrase) ;
  - `invoicePayments` : moyen (code + libellé), montant, compte de trésorerie
    (D10, D11, D14) ;
  - `otherMovements` : recharges, vidages, recharges offertes, jetons repris, écarts…
    (D12) : moyen, montant signé, compte de trésorerie, compte de contrepartie, libellé ;
  - contrôle publié : Σ lignes = Σ `invoicePayments` et Σ mouvements = Σ règlements
    restants, **offert des recharges compris**. **Si ce n'est pas vrai, TiBillet lève une erreur nommée** (la J n'est pas
    publiable, comme `EcritureDesequilibree`).
- Fonctions nouvelles dans `comptabilite/` (FALC, testées seules) :
  `repartir_les_reglements(vente)` (D14), `lignes_a_facturer(vente)` (D7, D9),
  `mouvements_hors_facture(vente)` (D12). Elles reprennent les règles de
  `comptabilite/ventilation.py` sans les recopier (même source que le FEC).

### 5.2 Docs

`api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md` (section comptabilité), CHANGELOG.

## 6. Côté module Dolibarr

### 6.1 Le passage de la nuit (mode ventes)

1. Catalogue (06-C), **avant** les ventes : un tarif vendu doit exister.
2. `/api/v2/closures/?after_number=<dernière J terminée>` → pour chaque J, dans l'ordre :
   `/closures/<uuid>/sales/?after_number=<dernière vente importée>` page après page.
3. Pour chaque vente, **dans une transaction** :
   - déjà dans `llx_tibillet_vente_importee` → on passe ;
   - tiers (D4-D6), vérifié vivant (D5) ;
   - produit introuvable pour un `priceIdentifier` → la vente est **refusée** (le
     catalogue n'a pas pu le créer : sans compte, par exemple) ;
   - facture ou avoir : `create`, `addline` (TTC, `fk_code_ventilation`) ; le choix
     quantité × prix ou quantité 1 (D8) se fait **avant** `addline` avec
     `calcul_price_total` ; `validate` (date : D23) ; contrôle du centime **après**
     `validate` (`update_price` peut encore corriger la TVA) ;
   - un `Paiement` par moyen + `addPaymentToBank`, `setPaid` ;
   - un virement interne par recharge ou vidage, un `PaymentVarious` par autre
     mouvement (D12) ;
   - ligne dans `llx_tibillet_vente_importee` ; `commit`.
   - Échec → `rollback`, erreur notée avec le numéro de vente et la phrase, **arrêt du
     passage** (D16).
4. J terminée → ligne dans `llx_tibillet_cloture_importee` avec `mode='ventes'` (D17).
5. Résumé du passage sur la page : J importées, factures, avoirs, tiers créés, paiements
   divers, ventes refusées (avec la phrase), reste à faire.

### 6.2 Les tables

- **`llx_tibillet_vente_importee`** (neuve) : `vente_uuid`, `numero_vente`,
  `cloture_uuid`, `fk_facture` (NULL si pas de facture), `date_import`, `entity` ; index
  unique `(vente_uuid, entity)`.
- **`llx_tibillet_cloture_importee`** : une colonne `mode` (défaut `ecritures`).

### 6.3 La page du module (mode ventes)

Tiers de passage, compte bancaire par moyen (D11, une liste déroulante par moyen vu),
nombre de ventes par passage (D18), état de la dernière nuit. Bouton « Importer les
ventes maintenant ».

## 7. Tests

### TiBillet (`tests/pytest/test_api_v2_ventes_comptables.py`, schéma dédié)

Droit (`comptabilite` seul → 403 ; + `sale` → 200) ; J non exportable → 404 ; pagination
et `after_number` ; vente espèces sans client → `customer: null` ; vente avec client →
ce user ; vente anonyme dont la carte est liée **après** → `customer: null` ; recharge
offerte → mouvement 623400 ; jetons repris → mouvement 623400 ; deux monnaies → deux
comptes de trésorerie ; ligne → `vatAccountingAccount` du taux ; vente en ligne → le client ; ligne au tarif, au compte et au taux de TiBillet ;
jetons cadeau → ligne 707900 à part ; offert partiel ; vente bière + recharge payée CB →
facture bière + mouvement recharge ; vente corrigée espèces → CB → un paiement CB ; avoir
→ vente liée ; vente en points absente ; CORRECTION absente ; somme contrôlée.
Mutations visées : repli sur `carte.user` ; moyen lu sur la ligne ; correction
ignorée ; recharge dans la facture ; recharge offerte oubliée.
**Test d'égalité avec le FEC** : pour une J de démo, Σ par compte (journal des ventes +
banque reconstitués depuis `sales/`) = Σ par compte du FEC de la même J.

### Module (`scripts/essai.php`, mode ventes, contre le lieu de dev)

Une J réelle de dev (ventes de démo : bar espèces/CB, cashless, billets, adhésion, avoir) :
une facture par vente, payée, liée d'avance ; Σ par compte (factures, paiements,
virements internes, paiements divers) = FEC de la J ; solde de la banque de la monnaie =
− monnaie encore sur les cartes ; tiers créés une fois ; second passage → rien ; coupure au milieu (limite à
2 ventes) → reprise à la vente suivante ; vente refusée → J arrêtée, rien d'écrit pour
elle ; J déjà importée en écritures → jamais en ventes ; le journal des ventes Dolibarr
s'écrit sans ligne à lier, avec un compte de TVA par taux ; tiers supprimé à la main →
recréé ; banque de caisse reliée à la monnaie → refusée. **Mesurer** le temps par vente
(D18) **et** le bouton « Écrire » du journal des ventes sur une grosse J (page web,
`max_execution_time`).

## 8. Hors de cette fiche

- Module **Adhérents** de Dolibarr (date de fin de cotisation) : les adhésions sont des
  factures comme le reste. Plus tard si un lieu le demande.
- Stock, PDF des factures, envoi des factures par e-mail.
- Lieux encore en **LaBoutik V1** : leurs ventes de bar ne sont pas dans Lespass (seules
  les adhésions reviennent par `fedow_connect/views.py:113`). Rien à importer pour elles.
- `/api/v2/sales/` (TODO `API-v2-ventes-reglements.md`) : reste à part.

## 9. Questions au mainteneur

| # | Question | Proposition |
|---|---|---|
| Q1 | Une facture **par vente**, même pour le client de passage ? | ✅ **Tranché (2026-10-16)** : une facture par vente. On **copie le comportement de TakePOS** (un ticket = une facture, tiers générique, une banque par mode, enchaînement `validate` → `Paiement` → `addPaymentToBank` → `setPaid`), sans `module_source='takepos'` |
| Q2 | Recharges, vidages, recharges offertes et jetons repris ? | ✅ **Tranché (2026-10-16)** : **pas de facture**, des mouvements de banque (D12). Q11 a précisé : recharges et vidages en **virements internes** ; recharge offerte et jetons repris en **paiements divers** (623400) |
| Q3 | Un tiers déjà dans Dolibarr avec le même e-mail ? | ✅ **Tranché (2026-10-16)** : **l'e-mail est la clé, toujours**. Le module cherche le tiers par e-mail (sans tenir compte des majuscules, dans l'entité) ; plusieurs → le plus ancien (plus petit rowid) ; aucun → il le crée. Conséquences : D5 et la table `llx_tibillet_tiers` sont revues (§6.2) ; un user qui change d'e-mail dans TiBillet aura un autre tiers |
| Q4 | Données de l'acheteur envoyées ? | ✅ **Tranché (2026-10-16)** : **l'e-mail seul** (et l'uuid du user). Le tiers créé porte l'e-mail comme nom |
| Q5 | Écarts d'encaissement (Stripe, QR, tireuse) ? | ✅ **Tranché (2026-10-16)** : **paiement divers**, contrepartie 758 (en plus) ou 658 (en moins). La facture garde le prix du panier |
| Q6 | Retour de consigne ? | ✅ **Tranché (2026-10-16)** : **ligne d'avoir au produit Dolibarr du gobelet**. TiBillet publie le `priceIdentifier` du **premier tarif en euros** du gobelet (`consigne_remboursee`), dans l'ordre du catalogue (`order`, puis `uuid`), archivés compris s'il n'y a qu'eux. Montant, taux et compte : ceux de la ligne TiBillet |
| Q7 | Droit de la clé ? | ✅ **Tranché (2026-10-16)** : **`comptabilite` + `sale`**, vérifiés dans l'action (D19). La clé Dolibarr a donc Produits + Comptabilité + Ventes |
| Q8 | Comptes bancaires ? | ✅ **Tranché (2026-10-16)** : **créés par le module s'ils manquent** (D11), modifiables ensuite sur la page |
| Q9 | Date des factures ? | ✅ **Tranché (2026-10-16)** : **la date comptable de la J**, à midi (D23), comme le FEC |
| Q10 | Le module touche-t-il aux réglages de Dolibarr (VAD, code `TIB`, taux, comptes de TVA) ? | ✅ **Tranché (2026-10-16)** : **oui**, il vérifie et règle **automatiquement** ce qui manque, et la **page de configuration** liste ce qu'il a fait et ce qui manque encore. Aucun taux n'est obligatoire en soi : il n'active que les taux **utilisés par le catalogue** (le 8,5 % seulement si un article l'a). Il ne modifie jamais un compte de TVA déjà posé par le lieu |
| Q11 | Solde de la banque « monnaie locale » ? | ✅ **Tranché (2026-10-16)** : **virements internes** pour les recharges et les vidages (D12). Le solde de la banque de la monnaie devient juste : il vaut, en négatif, la monnaie encore sur les cartes |

## 10. Relecture Fable (2026-10-15) — ce qui a été appliqué

- **Bloquant B1** (TVA : un seul compte dans Dolibarr, journal non écrit en dev) → D21,
  D20, test.
- **Bloquant B2** (recharge offerte et jetons repris : 419100 et 623400 s'écartent du
  FEC) → D12 complétée, contrôle §5.1, tests.
- C1 (une correction peut tomber dans la J suivante) → §3 et D1/D10 réécrits : nets avec
  toutes les corrections. *Hors 06-D* : fermer cette fenêtre dans la route de correction
  (verrou des ventes) — à noter au chantier 05.
- C2 (une banque par compte de trésorerie, pas par moyen) → D11. C3 (codes de paiement,
  banque de caisse) → D22, D11. C4 (date de la J) → D23, Q9. C5 (tiers supprimé) → D5.
  C6 (pas de repli `carte.user`) → D4. C7 (une vente refusée arrête le passage) → D16.
  C8 → D20.
- Suggestions reprises : S1 → D24 ; S2 → Q6 ; S3 → D15 ; S4 → Q11 ; S5, S6 → §6.1 et §7 ;
  S7 → §3.

## 11. Tests, mutations et import réel (2026-10-16)

- **Lespass** : `tests/pytest/test_ventes_a_facturer.py` (15 tests), `test_api_v2_ventes_comptables.py`
  (10), `test_fec_equilibre.py::test_ventes_a_facturer_egales_au_fec_compte_par_compte` (la
  découpe = le FEC, compte par compte, sur le scénario complet). Mutations tuées : 15.
  Suite complète : 3916 passed, 0 failed.
- **Module** : `scripts/essai.php`, essais 22 à 36 (réglages, banques, codes de paiement,
  tiers par e-mail, factures payées et liées, virements, avoirs, paiement divers, centime
  faux refusé, second passage, limite, réimport refusé, clôture en partie en factures,
  droit « Ventes »), réponse de TiBillet imitée. « TOUT EST OK ». Mutations tuées : 14.
- **Import réel** de la J n° 2 du lieu `lespass` (267 ventes, 254 factures) : ~6 s, et
  **Dolibarr = FEC compte par compte** (53, 5121, 5171, 4191, 6234, 706, 707, 756, 445711,
  445712).
- **Chrome** : facture payée, ligne liée ; journal des ventes sans ligne à lier ; journal de
  banque complet ; le bouton « Écrire » du journal de banque exigeait un compte fournisseur
  général → posé par le module.
- **Trouvé en route et corrigé** : le fût est une vente (la tireuse le vend au litre), à tort
  écarté par 06-C ; « Réimporter » une J en mode ventes ; J en partie en factures repassée en
  écritures ; compte posé sur un mode de paiement ; retour de consigne sans gobelet (500 →
  409) ; échappement des messages de la page.
- **Écarts au plan** (journal de bord) : produit absent → ligne libre au bon compte (et non
  vente refusée) ; D24 codé, non testé (course impossible à provoquer) ; contrat sans
  libellés de comptes (le module lit `/api/v2/accounts/`).
- **Mineurs reportés** (relecture Fable) : compte lu pour un hors-CA à 0 € ; caches gardés
  après un rollback D24 ; ordre de répartition différent du texte de D14 (compta juste) ;
  tiers sans filtre client/actif ; facture à 0 € non soldée ; N+1 consigne / virement reçu ;
  demi-centime et PHP 8.4 ; essais manquants (« Écrire », D24, tiers supprimé, avoir sur la
  route).
