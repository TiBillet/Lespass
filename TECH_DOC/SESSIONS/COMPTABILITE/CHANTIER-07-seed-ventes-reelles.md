# Chantier 07 — Seed de démo : des ventes réelles, comme en production

> Hub permanent de l'app `comptabilite/`. Contexte global : [`INDEX.md`](INDEX.md).
> Remplace la stratégie technique du chantier 02
> ([`CHANTIER-02-demo-data-ventes.md`](CHANTIER-02-demo-data-ventes.md)) : les cas
> métier restent, la façon de les écrire change.
>
> **Date :** 2026-11-12
> **Statut :** ✅ codé le 2026-11-12 (non commité), tests ciblés verts.
> **Migration :** aucune.

## 1. Contexte

Le seed des ventes de démo (`Administration/management/commands/_demo_data_v2_ventes.py`,
appelé par `demo_data_v2`) date d'avant le chantier 05 « montants entiers ». Il créait
les `LigneArticle` directement (`LigneArticle.objects.create`), sans `Vente` ni
`Reglement`, avec une date forcée à « hier 14 h ».

Depuis le chantier 05, tout le comptable lit les **ventes** :
`comptabilite/rapport.py` (`RapportDesVentes`) ne voit que les articles des ventes
réglées (`statut=REGLEE`, `unite="EUR"`, natures VENTE et AVOIR,
`hors_chiffre_affaires=False`). Constat en dev sur `lespass` le 2026-11-12 : 37 articles
sur 48 n'ont pas de vente. Ils sont invisibles pour les rapports, les clôtures, le FEC
et l'API comptable.

En production, la reprise (`BaseBillet/reprise_des_ventes.py`, fiche
[`CHANTIER-05-R-reprise-ventes.md`](CHANTIER-05-R-reprise-ventes.md)) a donné une vente
à toutes les anciennes lignes, puis les clôtures automatiques (`comptabilite/tasks.py`)
ont créé les J, H, M et A. Le dev doit ressembler à ça.

## 2. Cible

1. Chaque vente du seed passe par le **vrai chemin** de `BaseBillet/services_vente.py` :
   `ouvrir_vente`, `ajouter_article` (montants par `calculer_montants_article`,
   `hors_chiffre_affaires` figé depuis le produit), `ajouter_reglement`,
   `encaisser_vente(vente, datetime_encaissement=...)`. Les avoirs passent par
   `ecrire_la_vente_d_avoir_d_une_ligne` et `ecrire_la_vente_d_avoir_d_une_vente`.
2. Les ventes sont **réparties sur les 24 derniers mois complets** (le mois en cours
   n'en a pas). Chaque mois reçoit le même programme, à chiffres ronds : **1 000,00 €
   de chiffre d'affaires par mois**.
3. Après les ventes, le seed crée les **clôtures des périodes finies** (J, H, M, A), avec
   le code des clôtures automatiques, jour après jour, comme la tâche horaire l'aurait
   fait.
4. **Idempotence** : relancer le seed ne double rien. Le **reset** (`--reset-sales`)
   efface toutes les ventes et clôtures du lieu, sous garde-fou `DEBUG` + `TEST`, après
   un passage à blanc.

## 3. Le programme d'un mois

Deux journées par mois, le 6 et le 20 (jours qui existent dans tous les mois, et
toujours finis : ce sont des mois passés). Heure du lieu (`Configuration.fuseau_horaire`).

### Le 6 — soirée concert

| Heure | Vente | Moyen | Origine | CA (€) |
|---|---|---|---|---:|
| 10:00 | 10 billets « Plein » à 20 € (TVA 5,5 %) | SF | LP | 200 |
| 11:00 | 5 billets « Réduit » à 16 € (TVA 5,5 %) | SN | LP | 80 |
| 12:00 | 2 billets « Offert » (produit gratuit, 0 €) | — (aucun règlement) | LP | 0 |
| 13:00 | 1 atelier à prix libre payé 0 € | — (aucun règlement) | LP | 0 |
| 14:00 à 14:35 | 8 adhésions à 25 € (une vente chacune) | SF | LP | 200 |
| 15:00 | 1 adhésion à prix libre payée 0 € | — (aucun règlement) | LP | 0 |
| 16:00 | Recharge cashless en ligne (`R`) 20 € | SN | LP | hors CA |
| 16:30 | Recharge fédérée en ligne (`E`) 10 € | SF | LP | hors CA |
| 19:00 | Caisse Bar : 20 bières à 5 € (TVA 20 %), monnaie locale | LE | LB | 100 |
| 20:00 | Caisse Bar : 10 cocas à 3 € (TVA 10 %) | CC | LB | 30 |
| 20:30 | Caisse Bar : 4 vins rouges à 5 € + 10 chips à 2 € | CA | LB | 40 |
| 21:00 | Caisse Bar : 5 sandwichs à 8 €, payés en jetons cadeau (hors TVA, D8 bis) | LG | LB | 40 |
| 22:00 | Caisse Bar : 1 café offert (OFFRIR, règlement FREE de 2 €) | NA | LB | 0 |
| 22:30 | Caisse Bar : 5 chips à 2 € | CA | LB | 10 |
| 22:45 | Caisse Cashless : 3 recharges de 10 € en espèces (`RE`) | CA | LB | hors CA |
| 23:00 | Avoir d'un billet « Plein » de 10:00, remboursé par virement (comme à l'admin) | TR | AD | −20 |
| 23:15 | Avoir total de la vente de 22:30 (erreur de caisse) | CA | AD | −10 |

### Le 20 — journée atelier et adhésions

| Heure | Vente | Moyen | Origine | CA (€) |
|---|---|---|---|---:|
| 10:00 | 4 ateliers « Normal » à 30 € (TVA 10 %), saisis à l'admin | CC | AD | 120 |
| 10:30 | 2 ateliers « Solidaire » à 10 € (TVA 10 %), saisis à l'admin | CA | AD | 20 |
| 11:00 | Adhésion soutien 50 € | CH | AD | 50 |
| 11:30 | Adhésion par virement 100 € | TR | AD | 100 |
| 12:00 | Adhésion 30 € par prélèvement SEPA | SP | LP | 30 |
| 12:30 | Échéance d'adhésion mensuelle 10 € | SR | WK | 10 |

**Total du mois : 1 000,00 € de CA** (30 ventes, dont 2 avoirs ; 31 articles). Le 6 : 24 ventes, 670 € ; le 20 : 6 ventes, 330 €. Hors CA : 60 € de
recharges encaissées. Offert : 2 € (le café).

Les produits « en ligne » sont des produits `[DEMO] …` créés par le seed (préfixe gardé
pour le reset). Les produits de caisse sont ceux de `create_test_pos_data` (Bière, Coca,
Vin rouge, Chips, Sandwich, Café, « Recharge Monnaie locale ») : leur catégorie de
caisse a le compte 707000, le FEC de la J ne manque d'aucun compte. Un produit ou un
point de vente absent : le cas est sauté et dit en sortie (la somme du mois n'est alors
plus 1 000 €).

Avant d'écrire, le seed complète le plan comptable par défaut du lieu
(`charger_le_plan_comptable_par_defaut`, laboutik/plan_comptable.py : ajoute ce qui
manque, n'écrase rien). C'est ce qui relie la monnaie FED (`AssetFedowPublic`
STRIPE_FED_FIAT) au 467000 : sans ce lien, les règlements SF n'ont pas de compte et
l'export des J est refusé. Constat en dev le 2026-11-12 : `lespass` n'avait aucune
correspondance de monnaie.

## 4. L'ordre chronologique

Une vente reçoit son numéro et son empreinte chaînée **à l'encaissement**
(`encaisser_vente`). La chaîne est lue par numéro (`verifier_chaine_ventes`) ; une J
vérifie la chaîne sur la plage de ses numéros. Les ventes sont donc encaissées dans
l'ordre de leurs heures : mois du plus ancien au plus récent, le 6 puis le 20, heure par
heure. Les avoirs viennent après les ventes qu'ils annulent.

`timezone.now` est remplacé par l'heure de la vente le temps de l'écrire
(`unittest.mock.patch`, comme `_demo_data_v2_recap.py` le fait déjà pour une
annulation). C'est ce qui date aussi les champs `auto_now_add` (date de l'article, du
règlement, de création de la vente, de l'adhésion, de la réservation), et l'heure
d'encaissement des avoirs, que leurs fonctions prennent à « maintenant ».

Ensuite, dans `demo_data_v2`, les ventes d'hier (`seed_ventes_de_la_veille_par_le_moteur`)
et l'activité du récap (`_demo_data_v2_recap.py`) sont écrites **après** l'historique :
elles sont plus récentes, leurs numéros suivent. Leur garde change : elles ne
regardent plus « le lieu a une vente ou une J » (toujours vrai avec un historique),
mais « une vente est déjà encaissée depuis hier 0 h » ou « une J finit après hier 0 h ».

## 5. Les clôtures

`seed_clotures_demo(schema_name)` reproduit la tâche horaire, un jour après l'autre,
du jour de la première vente jusqu'à aujourd'hui :

1. le **filet J** du jour (`_creer_la_cloture_journaliere(seuil_du_filet=seuil du jour)`) :
   la J du service qui finit à ce seuil, s'il a des ventes ;
2. puis les **H, M, A** qui finissent à minuit ce jour-là
   (`_creer_la_cloture_d_une_periode`) : une période n'est clôturée qu'après le filet
   du jour où elle finit, elle porte donc les perpétuels de la J de sa dernière soirée ;
3. après la boucle, un **Z demandé** (`_creer_la_cloture_journaliere()`) pour les
   ventes encore hors J (celles d'hier si le seuil de ce matin n'est pas passé) :
   l'export comptable de la veille est disponible tout de suite.

Choix :
- les fonctions internes de `comptabilite/tasks.py` sont appelées directement. La tâche
  `generer_les_clotures_automatiques_du_lieu` ne convient pas : elle ne fait **qu'une
  J** par passage (de la dernière J au seuil courant, donc une J de 24 mois), elle est
  plafonnée à 12 clôtures H/M/A (`PLAFOND_DES_CLOTURES_CALENDAIRES_PAR_PASSAGE`), et elle
  envoie le récap du matin ;
- aucun e-mail : `demander_l_email_automatique_si_configure` n'est pas appelé ;
- **pas de J « reprise »** : elle refuserait le FEC de tout l'historique
  (`refus_du_fec_avant_la_mise_en_service`). Une J par journée de ventes est plus utile
  en dev (FEC, API comptable `journees_a_importer`) ;
- le seed est appelé **hors de toute transaction** : le temps 1 des clôtures est
  `atomic(durable=True)` et lève `RuntimeError` dans une transaction ouverte.

Résultat attendu pour 24 mois : 48 J (plus celle d'hier dans `demo_data_v2`), 48 H au plus,
24 M (une par mois, 1 000 € chacune), les A des années finies.

## 6. Aucun appel réseau

- Aucun `Paiement_stripe` : les règlements Stripe n'ont pas de paiement relié. L'avoir du
  billet est donc « remboursé par » un moyen de l'admin (virement), comme un avoir fait à
  la main dans l'admin (aucun appel à Stripe, D27).
- Pas de remboursement `REFUNDED` : il passe par `partial_refund_payment`, qui appelle
  Stripe. Il est remplacé par l'avoir d'un billet.
- Les avoirs sont d'origine ADMIN : la transition CREDIT_NOTE n'envoie rien à l'ancien
  LaBoutik (`ligne_article_credit_note`).
- Aucune transaction Fedow : les règlements cashless (LE, LG) portent l'uuid de la
  monnaie du lieu (`fedow_core.Asset` TLF, TNF), sans carte ni transaction. Les
  règlements SF (Stripe fédéré) portent la monnaie FED : c'est elle qui leur donne un
  compte (`compte_pour_reglement`) ; sans elle, l'export de la J est refusé.
- Les adhésions sont créées au statut ONCE (jamais ADMIN : un signal écrirait une vente
  de plus).

## 7. Idempotence et reset

- `seed_ventes_demo(reset=False)` n'écrit **rien** si le lieu a déjà une vente réglée ou
  une clôture : de nouvelles ventes datées du passé, encaissées après, casseraient
  l'ordre des numéros et n'entreraient dans aucune J.
- `seed_ventes_demo(reset=True)` (option `--reset-sales`) appelle
  `reinitialiser_les_ventes_du_lieu` deux fois : un **passage à blanc** (tout est compté
  puis annulé), puis le vrai. Garde-fou : `settings.DEBUG and settings.TEST`, sinon
  `RuntimeError` et rien n'est touché. Une seule transaction. Ce qui est effacé :
  toutes les clôtures du lieu, tous ses règlements, tous les articles qui ont une vente,
  toutes ses ventes (la chaîne est celle du lieu entier : en garder une partie ferait des
  trous de numéro), les impressions et corrections reliées, les anciennes lignes
  `[DEMO]` sans vente, les objets `[DEMO]` (réservations, adhésions, événements,
  produits), et les objets des personnes de démo (`demo-ventes@example.com`,
  `recap-*@example.com`) pour que la veille et le récap se réécrivent.
- Les clôtures sont toujours refaites par `seed_clotures_demo`, qui ne crée jamais deux
  fois la même période (unicité `(niveau, début, fin)`, filet déjà passé).

## 8. Tests

`tests/pytest/test_demo_data_ventes.py` (réécrit) : schéma dédié (`FastTenantTestCase`),
`create_test_pos_data`, seed sur **2 mois** (`nombre_de_mois=2`, pour la durée) :
- chaque article écrit par le seed a sa vente, réglée ;
- une clôture M par mois de ventes, au CA de 1 000,00 € ;
- les numéros suivent l'ordre des heures, la chaîne des ventes est saine, l'intégrité de
  chaque J est « OK » ;
- l'export comptable de chaque J (FEC, API) ne manque d'aucun compte ;
- tous les moyens et cas du programme sont présents (SF, SN, SP, SR, CC, CA, CH, TR, LE,
  LG, NA ; recharges hors CA ; avoirs) ;
- un second passage n'écrit rien (ni vente, ni clôture) ;
- le reset refuse hors `DEBUG` + `TEST`, le passage à blanc ne supprime rien, le vrai
  reset vide ventes et clôtures.

`tests/pytest/test_demo_ventes_de_la_veille.py` : un test de plus — les ventes d'hier
s'écrivent après un historique, et la J du filet de ce matin les reprend.

Chaque nouveau test est vérifié par mutation (vu en échec sur le code cassé exprès).

## 9. Hors périmètre

- Les 13 lignes de démo de `laboutik/management/commands/create_test_pos_data.py`
  (`UUID_TRANSACTION_DES_LIGNES_DE_DEMO`) restent sans vente : ce fichier sert à beaucoup
  de tests, il n'est pas touché ici. À traiter dans un chantier à part.
- Remboursements Stripe réels (`REFUNDED`), contributions crowdfunding, versements
  inter-lieux, vidage de carte, corrections de moyen de paiement, ventes en points :
  non écrits par le seed.
- Aucun e-mail de clôture, aucun récap n'est envoyé par le seed des clôtures.
