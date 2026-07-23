# E2E : recharge au comptoir, recompense au scan, et fin des fails silencieux
# / E2E: counter top-up, scan reward, and the end of silent skips

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** Deux parcours E2E contre les services reels — la recharge cashless au
point de vente, et la recompense en monnaie versee au scan d'un billet — plus la
suppression des onze `pytest.skip` qui pouvaient faire disparaitre un test E2E du rapport.
/ Two E2E journeys against the real services — the POS cashless top-up and the currency
reward paid on ticket scan — plus the removal of the eleven `pytest.skip` calls that could
make an E2E test vanish from the report.

**Pourquoi / Why :** Le chemin de la recompense au scan verse de l'argent reel et traverse
trois couches dont **deux avalent leurs exceptions** : un versement rate n'apparait nulle
part. Et la recharge au comptoir n'avait aucun test de bout en bout — c'est pourtant le
geste le plus frequent d'une caisse cashless.
/ The reward path moves real money through three layers, two of which swallow their
exceptions: a failed transfer is visible nowhere.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_parcours_fedow_reel.py` | 1 `skip` → `fail` ; **soumission Stripe reparee** (voir plus bas) |
| `tests/e2e/test_explorer_adresse_dupliquee.py` | 3 `skip` → `fail` |
| `tests/e2e/test_explorer_markers_per_pa.py` | 1 `skip` → `fail` |
| `tests/e2e/test_explorer_ux_pills_tags.py` | 3 `skip` → `fail` |
| `tests/e2e/test_membership_fix_solidaire.py` | 3 `skip` → `fail` |
| `tests/e2e/test_parcours_fedow_reel.py` | 1 `skip` → `fail` |

### Fichiers ajoutes / Added files

| Fichier / File | Contenu / Content |
|---|---|
| `tests/e2e/test_recharge_pos_puis_qrcode.py` | La frontiere entre les deux moteurs de monnaie, mesuree |
| `tests/e2e/test_recompense_au_scan_puis_qrcode.py` | Versement au scan d'un billet, depense, non-rejeu |
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | Versement au paiement d'une adhesion, depense |
| `tests/e2e/test_renouvellement_adhesion_recurrente.py` | Echeance mensuelle sur horloge Stripe : vente, recompense, comptabilite |

### Fixtures ajoutees / Added fixtures

| Fixture (`tests/e2e/conftest.py`) | Role |
|---|---|
| `instant_serveur` | L'heure du serveur, pour ancrer la borne basse d'une fenetre comptable |
| `rapports_comptables` | Les deux rapports (caisse + en ligne) depuis un instant donne |
| `rapports_qui_voient_la_ligne` | Dans lequel des deux rapports une ligne precise entre |

---

## Plus de fail silencieux

Onze `pytest.skip` pouvaient retirer un test E2E du rapport : conteneur injoignable, cache
SEO vide, tarif absent, champ disparu de l'admin, tenant sans monnaie locale. Tous rendent
desormais le test **rouge**, avec un message qui dit quoi relancer pour reparer
l'environnement.

Le cas le plus parlant est `test_membership_fix_solidaire.py` : il ignorait le test quand le
champ `manual_validation` etait absent du formulaire d'admin. Or c'est **exactement la
regression qu'il surveille**. Il se taisait donc precisement le jour ou il aurait du parler.

**Le seul skip conserve** est celui de `stripe listen` (marqueur `stripe_listen` +
`pytest_terminal_summary` dans `tests/e2e/conftest.py`). Il est legitime parce qu'il ne se
tait pas : il affiche un encadre rouge nommant chaque test non joue. C'est le modele a
suivre pour tout futur skip conditionnel.

/ Eleven skips could remove an E2E test from the report; all are now failures with an
actionable message. The only skip kept is the `stripe listen` one, which reports loudly.

---

## Ce que la recharge au comptoir a revele : deux moteurs de monnaie qui ne se voient pas

`test_recharge_pos_puis_qrcode.py` devait verifier qu'une recharge au point de vente rendait
la monnaie depensable par QR code. **Elle ne l'est pas**, et c'est structurel :

| | Recharge au comptoir | Paiement par QR code |
|---|---|---|
| Vue | `_executer_recharges` (`laboutik/views.py`) | `valid_payment` (`BaseBillet/views.py`) |
| Moteur | `fedow_core` — **local** | `fedow_connect` — Fedow **distant** |
| Appel | `TransactionService.creer_recharge` | `FedowAPI.transaction.to_place_from_qrcode` |
| Monnaie du tenant | `fedow_core.Asset` « Monnaie locale » | `AssetFedowPublic` « MonaLocalim » |

Le **portefeuille** est commun : il porte le meme uuid des deux cotes, parce que
`_obtenir_ou_creer_wallet` rend `carte.user.wallet`, miroir du portefeuille Fedow. Ce sont
les **monnaies** qui different, et rien ne les relie : `Product.asset` est une cle etrangere
vers `fedow_core.Asset`, jamais vers `AssetFedowPublic`.

Le point de vente sait **debiter** le Fedow distant (cascade `_debiter_legacy`). Il n'a
aucun chemin pour le **crediter**.

**Consequence concrete :** un adherent charge 5 € sur sa carte au comptoir. Il scanne
ensuite un QR code de 5 € : l'ecran lui annonce un solde de 0 € et refuse le paiement. Son
argent existe, mais pas la ou on le lui demande.

Le test **mesure** cet ecart plutot que de le contourner : il verifie que le moteur local a
bien credite 500 centimes, que la trace comptable est correcte, que le Fedow distant n'a
rien vu, et que le paiement est refuse. **Il deviendra rouge le jour ou les deux moteurs
convergeront** — c'est son role, et le fichier le dit en tete.

Non corrige ici : faire converger les moteurs est une decision d'architecture (phase
d'import du Fedow legacy vers `fedow_core`), pas un correctif de session de tests.

/ The counter top-up credits the LOCAL engine; the QR code payment debits the REMOTE Fedow.
The wallet is shared, the currencies are not. Money loaded at the counter cannot be spent
online. The test measures the gap and will turn red when the engines converge.

---

## La recompense au scan : le mecanisme fonctionne, mais il echoue en silence

`test_recompense_au_scan_puis_qrcode.py` couvre un chemin qui n'avait **aucun test** :

    Price.reward_on_ticket_scanned   le declencheur
    Price.fedow_reward_asset         la monnaie versee (AssetFedowPublic)
    Price.fedow_reward_amount        le montant, en unites

    signals.py  transition NOT_SCANNED → SCANNED  →  check_reward
      → tasks.py  refill_from_lespass_to_user_wallet_from_ticket_scanned
        → fedow_connect  refill_from_lespass_to_user_wallet

Verifie contre le **vrai Fedow** : le versement part, le montant est exact, la depense par
QR code debite bien, et un second scan ne reverse pas.

**Ce que le test protege.** `check_reward` (`signals.py`) et la tache (`tasks.py`)
enveloppent chacun leur corps dans `except Exception` + `logger.error`. Un versement qui
echoue — Celery arrete, portefeuille du lieu vide, refus du Fedow — ne produit **aucune**
erreur visible : le billet passe scanne, l'adherent croit etre credite, et il ne l'est pas.
Seule la relecture du solde **sur le Fedow** peut le detecter.

**Une contrainte non ecrite, verrouillee par une fixture.** La monnaie de recompense doit
etre de categorie `FED` ou `TLF` : ce sont les deux seules que `valid_payment` sait traduire
en moyen de paiement comptable. Une recompense en monnaie temps (`TIM`) ou cadeau (`TNF`)
serait creditee, puis **debitee au paiement sans qu'aucune vente ne soit enregistree en
face** (cf. `CHANGELOG/2026-07-22-qrcode-flux-complet-et-deux-500.md`). La fixture
`monnaie_de_recompense` echoue si la categorie n'est pas encaissable.

### Etat du seed : robuste pour l'adhesion, fragile pour le scan

Les deux mecanismes ne sont pas seedes de la meme facon.

**L'adhesion (`fedow_reward_enabled`) est complete et fonctionne.** Verifie en execution
reelle sur le tenant `lespass` : une cotisation « Caisse de sécurité sociale alimentaire /
Souscription mensuelle » reglee au comptoir credite bien 100 MonaLocalim sur le
portefeuille Fedow, la ligne passe `VALID` et porte sa metadata `fedow_reward`. C'est
desormais verrouille par `test_adhesion_recompense_puis_qrcode.py`.

**Le scan (`reward_on_ticket_scanned`) l'est a moitie en base** : trois tarifs portent le
drapeau avec `fedow_reward_asset` a `None`.

```
Inscription bénévolat — Bricolage et réparations / Tarif gratuit
Inscription bénévolat — Peinture et décoration   / Tarif gratuit
Inscription bénévolat — Jardinage et plantation  / Tarif gratuit
```

L'asset vise (`MTemps`) est pourtant bien declare dans le seed (`demo_data_v2` l.1269). La
difference tient a **une asymetrie de lecture entre les deux endroits du seed** :

```python
# l.2292 — adhesion : cherche en base, PUIS dans le dict du run. Robuste.
asset_obj = AssetFedowPublic.objects.filter(name=asset_name).first() or assets_by_name.get(asset_name)

# l.2493 — scan : lit UNIQUEMENT le dict du run courant.
time_asset = assets_by_name.get('MTemps')
```

`assets_by_name` n'est peuple que par les assets **(re)crees via l'API Fedow pendant ce
run** ; un appel Fedow qui echoue est journalise en `warning` (l.2231) et le dict reste
vide. La version « adhesion » retombe alors sur la base ; la version « scan » abandonne.

Piste, non traitee ici : aligner l.2493 sur le motif de l.2292.

**Correction d'une affirmation erronee** d'une version precedente de ce document : l'echec
n'a **pas** lieu dans le `except Exception` qui entoure la configuration du tarif (l.2506).
Celui-la n'attrape rien ici. Le point fragile est en amont, dans la construction du dict.

**Ce qui reste vrai dans les deux cas** : la tache exige les **trois** champs ensemble
(`reward_on_ticket_scanned and fedow_reward_asset and fedow_reward_amount`). Avec un asset
nul, le mecanisme est **inerte sans aucun signal** — et un gestionnaire qui coche la case
dans l'admin sans choisir de monnaie tombe exactement dans cet etat. Une validation qui
refuserait un tarif a moitie configure serait utile.

*(Note : `MTemps` est de categorie `TIM` — non encaissable par QR code. La recompense en
monnaie temps repond a un autre usage que le pouvoir d'achat.)*

/ The membership mechanism is fully seeded and verified working. The scan one has three
prices with a NULL asset, because of an asymmetry: the membership branch falls back to a DB
lookup, the scan branch reads only the current run's dict. Correction of an earlier claim in
this document: the failure is NOT in the swallowed exception around the price configuration.

---

## Verification par mutation / Mutation testing

Chaque test a ete vu **echouer** sur une regression volontaire, puis le code de production a
ete restaure a l'identique (verifie : aucune trace dans `git diff`).

| Mutation | Fichier | Assertion qui tombe |
|---|---|---|
| `montant_en_centimes=total_centimes` → `1` | `laboutik/views.py` | le moteur local credite 1 au lieu de 500 |
| `point_de_vente=point_de_vente` → `None` | `laboutik/views.py` | la recharge sort du ticket Z du comptoir |
| garde d'idempotence neutralisee | `BaseBillet/tasks.py` | un second scan reverse : 50 → 250 |
| `.delay()` du signal neutralise | `BaseBillet/signals.py` | aucun versement : 0 → 0, attendu 200 |
| `already_sent = False` → `True` | `BaseBillet/tasks.py` | adhesion : aucun versement, 0 → 0, attendu 10000 |
| `ORIGINES_ENCAISSEES_PAR_LE_LIEU` sans `LABOUTIK` | `laboutik/reports.py` | le ticket de caisse ne voit plus les especes : 0 au lieu de 500 |
| `.delay()` de la recompense neutralise | `BaseBillet/triggers.py` | renouvellement : vente OK, mais solde 0 au lieu de 10000 |
| `'subscription_cycle'` → valeur inconnue | `ApiBillet/views.py` | renouvellement : aucune vente enregistree |

Deux rappels qui ont chacun coute un faux resultat :

- une mutation dans `tasks.py` n'a **aucun effet** tant que `lespass_celery` n'est pas
  redemarre — sans quoi le test reste vert et on conclut a tort qu'il ne prouve rien ;
- **si une mutation tombe sur une assertion differente de celle qu'elle vise, ne pas
  conclure.** La mutation « pas de recompense » a d'abord fait echouer le test sur « aucune
  vente » : `stripe listen` etait mort entre-temps. La mutation n'avait rien prouve. Les deux
  mutations du renouvellement ont ete rejouees, CLI actif, avant d'etre inscrites ici.

---

## Ce que la suite complete a corrige dans le test lui-meme

`test_recharge_pos_puis_qrcode.py` a ete **vert en isolation pendant toute son ecriture**,
puis rouge des son premier passage en suite E2E complete :

```
Product.MultipleObjectsReturned: get() returned more than one Product -- it returned 2!
```

Le helper de lecture des soldes cherchait « le » produit de recharge euros par sa methode de
caisse. Or le signal `post_save` d'`Asset` cree un produit « Recharge {nom} » **et le
rattache au point de vente cashless** : tout test qui laisse derriere lui un asset TLF en
fabrique un second. Les tests controlvanne laissent `[vc_test] TLF`.

Deux endroits corrigés, pour la meme raison :

- le helper de solde recoit desormais l'uuid de la monnaie **en parametre** au lieu de la
  redeviner a chaque appel ;
- la fixture `comptoir` filtre sur `asset__name='Monnaie locale'` au lieu d'un `.first()`
  sans `order_by`, qui rendait un produit dependant de l'ordre de la base (PIEGES 9.97).

Aucun code de production en cause : c'etait le test qui etait fragile. Le motif est
documente en `tests/PIEGES.md` 12.13.bis, parce que le symptome — vert seul, rouge en suite
— coute cher a diagnostiquer.

/ The file was green in isolation and red on its first full-suite run: it looked up "the"
euro top-up product by payment method, but the Asset post_save signal creates one per TLF
asset and attaches it to the cashless POS. Test-side fix; no production code involved.

---

## Les deux mecanismes de recompense, desormais couverts

Ils partagent le meme trio de champs `fedow_reward_*` et le meme appel au Fedow, mais pas le
meme declencheur. Chacun a maintenant son fichier.

| | Recompense au scan | Recompense a l'adhesion |
|---|---|---|
| Drapeau | `Price.reward_on_ticket_scanned` | `Price.fedow_reward_enabled` |
| Declencheur | billet NOT_SCANNED → SCANNED | ligne d'adhesion CREATED → PAID |
| Chemin | `signals.py` → `check_reward` | `signals.py` → `trigger_A` (`triggers.py`) |
| Tache | `..._from_ticket_scanned` | `..._from_price_solded` |
| Garde de non-rejeu | `ticket.metadata['rewarded_from_ticket_scanned']` | `ligne.metadata['fedow_reward']` |
| Test | `test_recompense_au_scan_puis_qrcode.py` | `test_adhesion_recompense_puis_qrcode.py` |

Le second couvre le cas d'usage cite en tete : **on adhere, et l'adhesion cree du pouvoir
d'achat**. Le paiement passe par la vraie route du gestionnaire
(`/memberships/<pk>/ajouter_paiement/`), celle qu'il emprunte quand une cotisation est
reglee au comptoir en especes.

**Un signal de diagnostic, exploite par le test.** `trigger_A` passe la ligne de vente a
`VALID` en toute derniere instruction. Une ligne d'adhesion restee a `PAID` est donc le
symptome visible d'un trigger interrompu en chemin — le seul, puisque l'exception est avalee
a trois niveaux (`TRIGGER_LigneArticlePaid.__init__`, `trigger_A` autour de
`fedowAPI.membership.create`, et la tache). Le test l'assert explicitement.

## Le renouvellement recurrent : la recompense est bien reversee a chaque echeance

`test_renouvellement_adhesion_recurrente.py` repond a la question ouverte par le fichier
precedent : **une caisse de securite sociale alimentaire promet un pouvoir d'achat
RECURRENT.** Si la premiere cotisation credite et pas les suivantes, l'adherent paie tous les
mois pour ne recevoir qu'une fois — sans qu'aucune erreur ne le signale.

Le test fait passer un mois avec une **horloge de test Stripe**
(`stripe.test_helpers.TestClock`) avancee de 32 jours. Stripe emet alors reellement
l'echeance suivante, avec `billing_reason='subscription_cycle'` — l'evenement exact que
`Webhook_stripe` attend. La facture, le prelevement et l'evenement sont ceux de Stripe : pas
de faux webhook fabrique a la main.

Verifie a chaque echeance : une `LigneArticle` unique (`origine=WEBHOOK`, `moyen=STRIPE_RECURENT`,
`statut=VALID`, montant de la cotisation), la recompense reversee sur le **vrai Fedow**, sa
trace dans la metadata de la ligne, et le classement comptable.

**Deux pieges payes en l'ecrivant :**

1. **Un client Stripe sans moyen de paiement fait echouer chaque echeance** en
   `invoice.payment_failed`, jusqu'a suppression de l'abonnement. Il faut attacher une carte
   de test ET la designer comme moyen par defaut de facturation.
2. **La PREMIERE facture ne declenche rien** : elle porte `billing_reason='subscription_create'`,
   que le webhook ignore volontairement (l'adhesion initiale est traitee par le retour de
   paiement). Seul le deuxieme cycle est un renouvellement — conclure sur la premiere facture
   ferait croire a une regression inexistante.

/ The renewal reverts the reward at every due date, verified on a real Stripe billing cycle
driven by a test clock. Two traps: a customer with no default payment method fails every due
date, and the FIRST invoice is a `subscription_create`, deliberately ignored by the webhook.

---

## Ce que la comptabilite voit de chaque parcours

Chacun des quatre tests verifie desormais **ou atterrit l'argent**, et pas seulement que la
`LigneArticle` existe. Une vente parfaitement enregistree peut n'entrer dans **aucun** des
deux rapports — c'est ce qui est arrive aux remboursements de carte et aux ventes de tireuse.

| Parcours | Ticket de caisse | Cloture en ligne | Versement de recompense |
|---|---|---|---|
| Recharge au comptoir | **oui** — especes, section recharges, solde de caisse | non | — |
| Recompense au scan | non | la depense QR code seule | **aucune ecriture** |
| Adhesion payee a la main | non (origine `ADMIN`) | cotisation + depense | **aucune ecriture** |
| Renouvellement Stripe | non | la cotisation | **aucune ecriture** |

**Le constat qui traverse les trois derniers : le VERSEMENT d'une recompense ne laisse
aucune ecriture comptable.** Le lieu emet de la monnaie locale — donc une dette envers
l'adherent, a honorer chez ses producteurs — et rien ne l'enregistre cote Lespass. Les seules
traces sont la metadata de la ligne d'origine et la transaction cote Fedow.

L'asymetrie saute aux yeux au comptoir : une recharge **cadeau** au point de vente, elle,
ecrit bien une `LigneArticle` a moyen de paiement « offert ». Les trois tests verrouillent ce
constat ; ils deviendront rouges si une contrepartie est ajoutee — ce qui sera le signal de
verifier ce qu'elle vaut, pas une regression.

Non tranche ici : faut-il une ecriture ? C'est une question comptable (quelle contrepartie
pour une emission de monnaie locale ?), pas technique.

---

## Deux pieges de mesure, trouves en ecrivant ces assertions

Ils ont chacun produit un faux resultat avant d'etre compris. Tous deux documentes dans
`tests/PIEGES.md` (12.13.ter et 12.13.quater).

**1. Une fenetre comptable glissante rend tout delta faux.** Mesurer avant, mesurer apres,
soustraire : entre les deux, la borne basse avance aussi, de vieilles lignes sortent par la
gauche pendant que la vente entre par la droite, et les deux mouvements se compensent. Le
delta valait 0 alors que la vente etait parfaitement comptabilisee. Corrige en ancrant la
borne basse a un instant fixe (`instant_serveur()`) : la fenetre ne contient plus que ce que
le test produit, et les montants deviennent **exacts** au lieu d'etre des ecarts.

**2. Un total exact sur le rapport EN LIGNE n'est pas fiable.** Ses lignes arrivent par
webhook Stripe, donc en differe : le webhook d'un test tombe pendant le test suivant. Un
renouvellement attendu a 100 relevait 200, et un test voisin qui passait seul echouait en
suite. Le rapport de **caisse**, lui, n'a aucune source asynchrone et reste assertable au
centime. Corrige avec `rapports_qui_voient_la_ligne` : on ne demande plus « le total
vaut-il X ? » mais « **cette ligne-la** est-elle vue par ce rapport ? » — deterministe, et
c'est la vraie question metier.

---

## Le bouton « Pay » de Stripe qui ignorait le clic

`test_recharge_federee_par_carte_bancaire` (ecrit la veille) s'est mis a echouer sans
qu'aucun code de paiement n'ait bouge — y compris lance seul.

Le symptome menait au mauvais endroit : timeout de navigation en attente de **quitter**
`checkout.stripe.com`. On soupconne l'URL de retour, le webhook, le Fedow. Un diagnostic pas
a pas a montre autre chose :

- le formulaire est **entierement rempli** (montant, carte, nom, pays — capture a l'appui) ;
- le bouton est `enabled`, et le clic lui donne bien le **focus** (contour bleu visible) ;
- **aucune requete reseau ne part**, aucun message d'erreur, aucune entree de console.

Le clic n'atteignait donc pas le handler React. La parade : reessayer en alternant `click()`
et `dispatch_event('click')` jusqu'a ce que la page quitte Stripe — meme parade que celle
deja appliquee a l'accordeon des moyens de paiement dans `fill_stripe_card`.

Un `dispatch_event` **seul** ne suffit pas : le premier `click()` et l'attente qui le suit
sont necessaires, le temps que le formulaire React finisse de se valider.

Effet secondaire agreable : le fichier passe de ~2 min a **~47 s**, verifie sur deux runs
consecutifs.

**La regle a retenir** (documentee en `PIEGES.md` 12.14) : sur un front tiers, un clic qui ne
produit **aucune requete** n'est pas un probleme d'application — c'est le handler qui n'a pas
ete atteint. Chercher du cote de l'evenement, pas du cote du serveur.

### Et payer sans passer par le front ? Non, pas pour un Checkout heberge

La question s'est posee : pourrait-on confirmer le paiement par l'API et se passer du
navigateur ? Mesure faite :

```
SESSION_TROUVEE_SUR= compte_racine status=open montant=4377 pi=None mode=payment
```

`payment_intent` vaut **`None`** tant que le formulaire n'a pas ete soumis — Stripe le cree
A la soumission. Il n'y a donc rien a confirmer. La voie est fermee pour les paiements
uniques passant par un Checkout heberge.

Deux enseignements conserves en `PIEGES.md` 12.15 :

- **les abonnements, eux, se pilotent entierement par l'API** (creation, horloge, echeances,
  prelevement) — c'est pourquoi `test_renouvellement_adhesion_recurrente.py` ne touche jamais
  un navigateur, et tourne en ~50 s ;
- **le checkout fabrique par Fedow vit sur le compte RACINE**, pas sur le compte Connect du
  lieu : le chercher sur le Connect repond « No such checkout.session ».

---

## Ce qui reste a couvrir / Still uncovered

- La convergence des deux moteurs de monnaie (voir plus haut) — **hors sujet pour
  l'instant** : la phase est volontairement hybride, et c'est cet etat hybride que les tests
  decrivent.
- L'ecriture comptable d'un versement de recompense (voir le tableau ci-dessus) : question
  ouverte, pas un manque de test.
- L'echec d'une echeance (`invoice.payment_failed`) : que devient l'adhesion quand la carte
  de l'adherent est refusee ? Rencontre par accident en ecrivant le test du renouvellement,
  jamais teste volontairement.

---

## Comment tester (a la main) / Manual test

### Test 1 — la recharge au comptoir n'est pas depensable en ligne

1. Ouvrir la caisse sur le point de vente « Cashless », avec la carte primaire.
2. Recharger 5 € sur une carte client rattachee a un adherent, en especes.
3. Se connecter avec cet adherent, aller sur `/my_account/balance/`.
4. La monnaie apparait bien dans le tableau, avec le badge « Local ».
5. Faire generer un QR code de 5 € et le scanner avec ce compte : l'ecran annonce un solde
   de 0 € et refuse. C'est le comportement decrit ci-dessus, pas une panne.

### Test 2 — la recompense au scan

1. Dans l'admin, sur un tarif de billet : cocher « recompense au scan », choisir la monnaie
   **MonaLocalim** et un montant. Les trois champs sont obligatoires ensemble.
2. Reserver une place avec un compte de test, puis scanner le billet depuis l'admin.
3. Sur `/my_account/balance/` de ce compte : le solde a augmente du montant.
4. Rescanner le meme billet : le solde ne bouge plus.

Si le solde ne bouge pas au point 3, regarder **les logs de `lespass_celery`** : ni l'ecran
ni le billet ne signalent l'echec.

```bash
docker logs --tail 100 lespass_celery | grep -i "TICKET SCANNED\|check_reward"
```

### Tests automatiques

L'ordre compte : les E2E creent de VRAIES ventes QR code dans le tenant, qu'un test pytest
comptant large peut ramasser. Lancer pytest **apres**.

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/e2e/ -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Le parcours de la recompense dure ~1 min 30 : il attend deux fois un versement Celery, et la
seconde attente doit aller a son terme pour que la non-regression signifie quelque chose.

**Prerequis** : le serveur de developpement tourne, Celery tourne, le Fedow est joignable, et
le portefeuille du lieu detient assez de MonaLocalim pour payer les versements.
