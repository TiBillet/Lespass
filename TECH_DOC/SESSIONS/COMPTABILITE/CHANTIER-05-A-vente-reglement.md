# Chantier 05-A — Tables `Vente` et `Reglement`, service de vente

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D2 à D6, D18, D21, R1
> Effort : 3 j — Dépend de : rien (livrée après A′, ordre du §6 du tronc). **Migration : oui.**
> Personne n'appelle encore ce code à la fin de la fiche : aucun comportement ne change.
> Les producteurs actuels qui ne passent pas `vat` gardent la TVA par défaut (§2).

## 1. Ce que livre la fiche

1. Les tables `Vente` et `Reglement`, les champs entiers de `LigneArticle` (§3 du tronc)
   et la FK `Paiement_stripe.vente`.
2. **Un seul point d'entrée** pour écrire une vente : `BaseBillet/services_vente.py`.
3. L'empreinte chaînée de la vente et sa vérification.
4. Une fabrique de test `tests/pytest/fabriques_vente.py`, avec l'assistant
   `verifier_egalites(vente)` (§6).
5. Les contraintes de base et la garde d'immutabilité d'une vente `REGLEE` (§2).

## 2. Modèles

`Vente` et `Reglement` dans un module `BaseBillet/models_vente.py`, importé par
`BaseBillet/models.py` (qui dépasse 4 000 lignes). Champs exacts : §3 du tronc. Les FK
vers `Paiement_stripe`, `laboutik.PointDeVente`, `CarteCashless` sont écrites en
**chaînes** (`"BaseBillet.Paiement_stripe"`…) : sinon import circulaire.

- `Vente.numero` : `PositiveIntegerField(null=True, blank=True, unique=True)` (Postgres
  accepte plusieurs NULL sous `unique`).
- `Vente.nature`, `Vente.statut` : `TextChoices`, libellés FR (`_()`).
- `Vente.unite` : `CharField(max_length=36, default="EUR")`.
- `Vente.idempotency_key` : `CharField(null=True, blank=True)` +
  `UniqueConstraint(fields=["idempotency_key"], condition=Q(idempotency_key__isnull=False))`.
- Montants : `IntegerField` (centimes signés). Aucun `DecimalField` pour de l'argent.
- `LigneArticle.vente` : `ForeignKey(Vente, null=True, blank=True, on_delete=PROTECT,
  related_name="articles")`.
- `LigneArticle.total_catalogue`, `part_offerte`, `total_ttc`, `total_tva` :
  `IntegerField(default=0)`. `source_offert` : `CharField` à choix (`OFFRIR`, `JETONS`),
  vide par défaut. `cout_achat` : `IntegerField(null=True)` (vide = prix d'achat
  inconnu, D21).
- **Contraintes de base** (`Meta.constraints`) : sur `LigneArticle`,
  `total_ttc = total_catalogue − part_offerte` et `total_ht + total_tva = total_ttc` ;
  sur `Reglement`, `montant <> 0`. Un producteur qui contourne le service est refusé
  par Postgres. **La 2ᵉ contrainte ne vaut que pour une ligne rattachée à une vente**
  (`vente IS NULL OR …`) jusqu'à la fiche H, qui rend `vente` obligatoire : des lignes
  existantes portent un `total_ht` écrit par le chantier 04-B (SUIVI §4).
- **Garde d'immutabilité** : une fois la vente `REGLEE`, `Vente.save()` refuse toute
  modification ; `Reglement.save()` refuse toute modification ; `LigneArticle.save()`
  refuse un changement de `amount`, `qty`, `vat`, `total_*`, `part_offerte`,
  `pricesold`, `vente` (les statuts, `sended_to_laboutik`, `metadata` et les FK
  `reservation` / `membership` / `booking` restent libres : la machine à statuts et les
  tâches Celery écrivent encore ces champs). Exception explicite en français.
  `.update()` contourne `save()` : c'est l'empreinte qui couvre ce cas (§5).
- `LigneArticle.hors_chiffre_affaires` : `BooleanField(default=False)`. Liste exacte des
  cas vrais (figée à la vente, un changement ultérieur du produit ne change rien) :
  `Product.methode_caisse` ∈ {`RE` recharge euros, `RC` recharge cadeau, `TM` recharge
  temps} **ou** `categorie_article = RECHARGE_CASHLESS` (recharge API v2,
  `api_v2/views.py` ~l.964, sans `methode_caisse`), **ou** un des deux produits système
  « Écart d'encaissement » (D26, fiche D). Relire `BaseBillet/models.py` ~l.1363-1398
  au démarrage. **`VR` (« Virement pot central ») et `FD` (« Fidélité ») sont aussi hors
  chiffre d'affaires** (mainteneur, 2026-09-29) : hors CA ne veut pas dire invisible, ils
  restent dans le Z et le FEC avec leur compte (fiche E).
- `Reglement.vente` : `related_name="reglements"`, `on_delete=PROTECT`.
- `Reglement.fedow_transaction_uuid` : `UUIDField(null=True)` — pas de FK
  (`fedow_core` en SHARED_APPS, `Reglement` en TENANT_APPS).
- `Commande.vente` (`BaseBillet`) et `CommandeSauvegarde.vente` (`laboutik`) : FK
  nullable vers `Vente`. `BaseBillet` pointe déjà vers `laboutik`
  (`LigneArticle.point_de_vente`, `BaseBillet/models.py` ~l.3749 ; `Vente.point_de_vente`
  aussi) : la FK `CommandeSauvegarde.vente` est donc dans une **migration `laboutik`
  à part**, qui dépend de la migration `BaseBillet` de `Vente`. Chaque fichier de
  migration ne dépend que dans un sens : pas de cycle.
- `Paiement_stripe.montant_encaisse` : `IntegerField(null=True)` — rempli en fiche D.
- `Paiement_stripe.moyen` : `CharField` à choix (`SN`, `SP`, `SR`), nullable — voir T1
  (« Machine à états », fin de fiche). La fiche D le lit dès D-1.
- `Paiement_stripe.vente` : `ForeignKey(Vente, null=True, blank=True, on_delete=PROTECT,
  related_name="paiements_stripe")` — la **vente d'origine** du paiement (R5), posée en
  fiche D à l'ouverture du checkout. Les ventes `AVOIR` d'un remboursement Stripe ne
  sont **pas** rangées ici (elles pointent vers la vente d'origine par `vente_liee`).
- `Vente.operateur` : FK nullable vers `TibilletUser` (l'utilisateur de la carte
  primaire) ; `Vente.carte` : FK nullable vers `CarteCashless`.

**`LigneArticle.save()` (`BaseBillet/models.py` ~l.3884-3895)** remplace aujourd'hui
une TVA nulle par celle du produit ou de la configuration (sauf FREE / NM). Une
recharge payée en CB serait écrite à 20 % alors que sa TVA calculée vaut 0.

Le champ `vat` a `default=0` (~l.3678) : il ne vaut jamais `None`, et une trentaine de
producteurs actuels **ne passent pas** `vat` (`validators.py` ~l.412, ~l.437, ~l.974,
~l.1144, `services_commande.py` ~l.216, crowds, booking, `signals.py` ~l.502,
`fedow_connect/views.py` ~l.97…) : ils comptent sur ce défaut. On ne touche donc **ni
au champ ni à la règle** pour eux. `ajouter_article` pose un marqueur sur l'instance
avant l'INSERT (`ligne._tva_explicite = True`) ; `save()` saute le défaut quand ce
marqueur est présent. Résultat : un 0 passé par le service est respecté, tout le reste
se comporte comme aujourd'hui.

## 3. Le service (`BaseBillet/services_vente.py`)

Fonctions explicites, pas de classe à état caché, docstrings FALC (LOCALISATION, FLUX).

| Fonction | Rôle |
|---|---|
| `calculer_montants_article(prix_unitaire, quantite, taux_tva, part_offerte=0, prix_achat=0, total_catalogue_impose=None, quantite_pour_cout=None)` | **La seule formule d'argent du projet** (§2 du tronc). Renvoie un dict d'entiers : `total_catalogue`, `part_offerte`, `total_ttc`, `total_ht`, `total_tva`, `cout_achat` (None si `prix_achat == 0`). `total_catalogue_impose` : l'argent réel d'une « part » pendant la **transition** (fiches B, C) ; **retiré en fiche H**. `quantite_pour_cout` : la quantité réelle servie, dans l'unité du prix d'achat (kg, L, pièces), quand `quantite` ne l'est pas (vente au poids avec `qty = 1`, part de cascade ou de tirage) ; `None` → `quantite`. Refuse `part_offerte` hors de `[0, total_catalogue]` (même signe pour un avoir). |
| `ouvrir_vente(origine, nature, unite="EUR", point_de_vente=None, operateur=None, client=None, carte=None, vente_liee=None, idempotency_key=None)` | crée la vente `EN_ATTENTE` ; une clé déjà connue renvoie la vente existante |
| `ajouter_article(vente, pricesold, quantite, prix_unitaire, taux_tva, part_offerte=0, source_offert="", prix_achat=0, offert_en_totalite=False, total_catalogue_impose=None, quantite_pour_cout=None, hors_chiffre_affaires=False, **champs_de_la_ligne)` | crée la `LigneArticle` en **un seul INSERT** avec tous ses montants et `vat` (marqueur `_tva_explicite`, §2) ; `champs_de_la_ligne` = champs historiques (`payment_method`, `asset`, `status`, `reservation`…) posés pendant la transition. **Règle « offert à montant non nul »** (§2 du tronc) : si `offert_en_totalite=True` (ou, pendant la transition seulement, si `payment_method == FREE` — sucre retiré en H) et le total catalogue ≠ 0, pose `part_offerte = total_catalogue`, `source_offert = OFFRIR`, et ajoute le règlement `FREE` du même montant |
| `ajouter_reglement(vente, moyen, montant, asset=None, carte=None, wallet=None, fedow_transaction_uuid=None, paiement_stripe=None, reference_externe="")` | `montant` doit être un `int` non nul (refus d'un `Decimal`, d'un `float`, de 0) |
| `encaisser_vente(vente)` | §4 |
| `annuler_vente(vente)` | `EN_ATTENTE` → `ANNULEE`, sans numéro, **sans retour arrière**. Seuls Stripe `CANCELED` et SEPA refusé l'appellent (fiche D) ; une session expirée ou une recharge échouée restent `EN_ATTENTE` |

**Le service n'ajoute aucun `save()` sur une ligne.** Les déclencheurs (Fedow, e-mails,
envoi à l'ancien LaBoutik) partent sur une **transition de statut** faite par un
`save()` (`CREATED → PAID`, `CREATED → CREDIT_NOTE`…), jamais à la création
(`BaseBillet/signals.py` ~l.405 : `_state.adding` → rien). Plusieurs producteurs en
dépendent (`signals.py` ~l.502-513, `validators.py` ~l.1153, `admin_tenant.py`
~l.2098, `PaiementStripe/utils.py` ~l.99) : **ils gardent leur transition**, telle
quelle. Le service, lui, écrit la ligne à sa création, puis ne la touche plus que par
`.update()` (une transition `PAID → PAID` en trop relancerait les déclencheurs,
`signals.py` ~l.341).

Constantes uniques : `MOYENS_OFFERTS = [LG, FREE]` (FREE vaut `"NA"` en base) ;
moyens hors encaissement pour les rapports : `MOYENS_OFFERTS + [NM]`.
`unite != "EUR"` (points) → `taux_tva` doit valoir 0.

## 4. `encaisser_vente(vente)` — le cœur

```
with transaction.atomic():          # savepoint si le producteur a déjà une transaction
  1. Verrou du lieu :  SELECT pg_advisory_xact_lock(hashtext('vente-<schema_name>'))
  2. Relire la vente sous verrou (select_for_update) :
       déjà REGLEE → la renvoyer telle quelle (idempotence : webhook + retour Stripe)
       ANNULEE     → refus
  3. Vérifier les deux égalités (relues en base) :
       Σ reglements.montant                          == Σ articles.total_catalogue
       Σ reglements.montant (moyen ∉ MOYENS_OFFERTS) == Σ articles.total_ttc
     Sinon : lever EgaliteDeVenteRompue (message FR avec les deux sommes).
  4. numero = (plus grand numero du lieu) + 1 ; datetime_encaissement = now()
     totaux de la vente = sommes des articles (5 champs)
     statut = REGLEE    # AVANT le calcul : le statut fait partie du message
     previous_hmac = hmac_hash de la vente numero − 1 ("" pour la première)
     hmac_hash = calculer_hmac_vente(vente, cle, previous_hmac)
     save()
```

- Le verrou `pg_advisory_xact_lock` est tenu jusqu'au **COMMIT le plus extérieur**. Les
  vues du projet tournent en autocommit (`ATOMIC_REQUESTS` non défini dans
  `TiBillet/settings.py`) : sans le `atomic()` interne, le verrou serait relâché à la
  fin de sa propre requête et deux encaissements simultanés feraient une
  `IntegrityError` sur `numero`. Exception : les vues d'ajout / modification de l'admin
  Django sont déjà dans un `atomic()` ; le verrou y est tenu jusqu'à la fin de la
  requête admin (acceptable : l'admin n'est pas la caisse).
- **Encaisser en dernier** dans la transaction du producteur, après tout appel réseau
  et tout déclencheur qui appelle Fedow en HTTP (adhésion admin : `signals.py` ~l.502,
  PIEGES 13.2). Sinon le verrou du lieu bloque toute la caisse pendant la latence.
- Une vente `EN_ATTENTE` ou `ANNULEE` ne consomme **aucun** numéro.
- Une vente **sans article** est refusée, sauf `VIDAGE_CARTE` et `CORRECTION` (leurs
  règlements s'annulent).
- Une vente **sans règlement** n'est acceptée que si Σ `total_catalogue` = 0 (vente
  gratuite).

## 5. L'empreinte (`laboutik/integrity.py`)

`calculer_hmac_vente(vente, cle, previous_hmac)` — l'ancienne `calculer_hmac` (par
ligne) reste jusqu'à la fiche H.

Message = `json.dumps(donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` :

```python
donnees = {
    "format": 1,
    "uuid": str(vente.uuid),
    "numero": vente.numero,
    "datetime_encaissement": vente.datetime_encaissement.astimezone(timezone.utc).isoformat(),
    "nature": vente.nature, "origine": vente.origine, "unite": vente.unite,
    "statut": vente.statut,
    "point_de_vente": str(vente.point_de_vente_id or ""),   # décide le journal du FEC
    "vente_liee": str(vente.vente_liee_id or ""),
    "totaux": [total_catalogue, total_offert, total_ttc, total_ht, total_tva],
    "articles": [  # tries par uuid
        [uuid, pricesold_uuid, f"{qty:.6f}", amount, f"{vat:.2f}",
         total_catalogue, part_offerte, source_offert, total_ttc, total_ht, total_tva,
         hors_chiffre_affaires],
    ],
    "reglements": [  # tries par uuid
        [uuid, moyen, montant, asset_ou_vide, carte_ou_vide,
         fedow_transaction_uuid_ou_vide, reference_externe],
    ],
    "previous_hmac": previous_hmac,
}
```

Clé : `LaboutikConfiguration.get_solo().get_or_create_hmac_key()` (inchangée ; le
singleton existe pour tout lieu, `laboutik` est en TENANT_APPS).

`verifier_chaine_ventes(cle)` parcourt les ventes `REGLEE` par `numero` croissant et
renvoie les anomalies : empreinte fausse (article ou règlement modifié), maillon
cassé, trou de numéro, égalité rompue (relue en base). **Aucune exception tolérée.**

## 6. Fabrique de test (`tests/pytest/fabriques_vente.py`)

`fabriquer_vente_encaissee(origine, articles=[...], reglements=[...], nature=VENTE)`
passe **par le service** : une fabrique qui contourne le service rendrait les tests
aveugles aux égalités.

`verifier_egalites(vente)` : relit la vente en base et asserte les deux égalités du §2
du tronc et `Vente.total_* = Σ articles`. **Chaque test de fiche qui encaisse une
vente l'appelle à la fin** (B à H). Pendant la transition, il n'asserte pas le HT des
parts (±1 c, §5 du tronc).

## 7. Tests

Fichiers : `tests/pytest/test_montants_article.py` (formule seule, sans base) ;
`tests/pytest/test_vente_modeles.py` (modèles, base partagée : TVA, contraintes, `Paiement_stripe`) ;
`tests/pytest/test_vente_service.py` (**schéma dédié** : numérotation, chaîne,
altérations ; créer `LaboutikConfiguration` à la main).

Tests ajoutés pendant la fiche (SUIVI §4, sinon une règle n'était vue par aucun test) :
`test_paiement_stripe_moyen_sr_pose_a_la_creation_d_une_echeance`,
`test_hors_chiffre_affaires_calcule_depuis_le_produit_ou_force`,
`test_vente_sans_article_refusee_sauf_vidage_et_correction`,
`test_ouvrir_vente_meme_cle_rend_la_meme_vente`, `test_ajouter_a_une_vente_reglee_refuse`,
`test_ajouter_article_recopie_l_origine_de_la_vente`,
`test_annuler_vente_reglee_refusee_et_annulee_rendue_telle_quelle`,
`test_encaisser_refuse_un_offert_sans_reglement_de_trace`,
`test_empreinte_precedente_modifiee_signale_un_maillon_casse`.

| Test | Donnée → attendu |
|---|---|
| `test_trois_jus_a_350_font_1050_ht_875_tva_175` | 350 × 3, 20 % → 1050 / 875 / 175 |
| `test_fromage_0_350_kg_a_1290_arrondi_demi_haut` | 1290 × 0,350 = 451,5 → **452** |
| `test_part_offerte_300_sur_500_net_200_tva_sur_200` | → net 200, HT 167, TVA 33 |
| `test_avoir_moins_deux_biere_a_500` | −2 × 500, 20 % → −1000 / −833 / −167 |
| `test_taux_zero_ht_egal_net` | 0 % → HT = net, TVA 0 |
| `test_net_105_a_20_pourcent_ht_88_tva_17` | HT 87,5 → 88, TVA 17 (HT + TVA = net) |
| `test_net_111_a_20_pourcent_ht_93` | 92,5 → **93** (l'arrondi au pair de `calculer_total_ht` donne 92) |
| `test_cout_achat_fige_et_vide_si_prix_inconnu` | 3 × 120 → 360 ; prix 0 → `None` |
| `test_total_catalogue_impose_est_repris_tel_quel` | part LE 500 (qty 1,428571) → 500 |
| `test_part_offerte_superieure_au_total_refusee` | offert 600 sur 500 → refus |
| `test_reglement_decimal_ou_nul_refuse` | `Decimal("5.5")`, 0 → refus |
| `test_tva_zero_explicite_respectee_par_save` | recharge par `ajouter_article`, `vat=0` → relue 0 (aujourd'hui 20) |
| `test_create_sans_vat_garde_la_tva_du_produit` | `LigneArticle.objects.create(...)` sans `vat` → TVA du produit (comportement actuel inchangé) |
| `test_ajouter_article_ne_declenche_aucune_transition` | `ajouter_article(status=PAID)` : la fonction de transition de statut n'est **pas** appelée (création) ; le producteur qui fait ensuite `CREATED → PAID` la déclenche une fois |
| `test_offert_a_montant_non_nul_part_offerte_et_reglement_free` | `offert_en_totalite=True` sur 1500 → part offerte 1500, `OFFRIR`, règlement FREE 1500, égalités tenues ; même résultat avec `payment_method=FREE` (transition) |
| `test_contrainte_base_refuse_une_ligne_incoherente` | `LigneArticle.objects.create(total_catalogue=500, part_offerte=0, total_ttc=499)` → `IntegrityError` ; `Reglement(montant=0)` → `IntegrityError` |
| `test_vente_reglee_refuse_toute_modification_par_save` | sur une vente `REGLEE` : `reglement.montant = …; save()` → refus ; `ligne.amount = …; save()` → refus ; `ligne.status = VALID; save()` accepté |
| `test_cout_achat_sur_la_quantite_reelle` | vente au poids `qty = 1`, `quantite_pour_cout = 0,350`, prix d'achat 800 / kg → 280 |
| `test_paiement_stripe_vente_d_origine` | FK `Paiement_stripe.vente` posée, nullable |
| `test_hors_chiffre_affaires_fige` | changer `methode_caisse` du produit après la vente → la ligne ne change pas |
| `test_encaisser_refuse_si_reglements_differents_du_catalogue` | 1050 / 1049 → exception, rien en base (numéro vide, `EN_ATTENTE`) |
| `test_encaisser_refuse_si_argent_different_du_net` | offert 300 réglé en CB → refus |
| `test_encaisser_deux_fois_meme_numero` | 2ᵉ appel → même vente, même numéro |
| `test_encaisser_vente_annulee_refuse` | |
| `test_numeros_consecutifs_sans_trou` | 1, 2, 3 |
| `test_vente_annulee_ou_en_attente_ne_prend_pas_de_numero` | la réglée a le n° 1 |
| `test_premiere_vente_chainee_sur_vide_puis_suivante_sur_la_precedente` | |
| `test_alterer_une_vente_reglee_casse_la_chaine` (**10 cas** dans une boucle, chaque cas dans un point de sauvegarde annulé : `FastTenantTestCase` ne prend pas `parametrize`) | par `.update()` : `total_ttc` d'un article ; `montant` d'un règlement ; `vente_liee` ; `point_de_vente` → « empreinte fausse » à chaque fois |
| `test_supprimer_une_vente_laisse_un_trou_signale` | suppression par SQL brut (les FK `PROTECT` des articles et règlements bloquent la suppression d'une vente par l'ORM) |
| `test_supprimer_un_reglement_signale_egalite_rompue` | SQL brut (un `reglement.delete()` passerait aussi : `delete()` n'est pas gardé, seule l'empreinte et l'égalité le voient) |
| `test_vidage_de_carte_sans_article_encaisse` | +500 LE, −500 CA |
| `test_vente_gratuite_sans_reglement_encaissee` | article 0, aucun règlement |
| `test_vente_payante_sans_reglement_refusee` | article 500, aucun règlement → refus |
| `test_vente_en_points_refuse_une_tva` | |

Vus rouges : tous (module absent → `ImportError` noté), puis chacun contre un service
volontairement vide. `test_tva_zero_explicite_respectee_par_save` est rouge sur le
code actuel ; `test_create_sans_vat_garde_la_tva_du_produit` est vert avant et doit le
rester (non-régression, noté tel quel).

**Concurrence** : pas de pytest `transaction=True` (interdit). Vérification manuelle
documentée dans le CHANGELOG : script `manage.py tenant_command shell` lançant deux
threads d'encaissement, **chacun dans son `tenant_context`** → numéros distincts,
chaîne valide ; puis deux encaissements de la **même** vente → un seul numéro.

Mutations :

| Mutation | Test qui doit tomber |
|---|---|
| `ROUND_HALF_UP` → `ROUND_HALF_EVEN` | net 111 (le fromage 451,5 → 452 est pair : il ne voit que la troncature) |
| TVA calculée à part (`arrondi(net × taux / (100 + taux))`) | net 105 |
| retirer la 2ᵉ égalité | argent ≠ net |
| `numero = max + 1` → `count() + 1` | trou de numéro après suppression |
| retirer le `atomic()` interne ou le `select_for_update` | encaisser deux fois (script manuel) |
| retirer `"reglements"`, `"vente_liee"` ou `"point_de_vente"` du message HMAC | altérer une vente réglée (cas correspondant) |
| `previous_hmac` = "" toujours | chaînage |
| `save()` réapplique la TVA par défaut sur un 0 (marqueur ignoré) | TVA 0 explicite |
| défaut appliqué seulement si `vat is None` (sans marqueur) | create sans `vat` |
| règle « offert à montant non nul » retirée | offert à montant non nul |
| coût calculé sur `quantite` au lieu de `quantite_pour_cout` | coût sur la quantité réelle |
| retirer une `CheckConstraint` | contrainte de base |
| garde d'immutabilité retirée | modification par `save()` |

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-A-vente-reglement.md` (migration :
oui ; chaînes i18n : natures, statuts, sources d'offert).

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T1 | Ajouter `Paiement_stripe.moyen` (`SN` / `SP` / `SR`) : `SP` et `SN` posés par `update_checkout_status` (`BaseBillet/models.py` ~l.3557, ~l.3577), `SR` à la création du paiement d'une échéance (`PaiementStripe/views.py` `CreationPaiementStripe`, bloc facture, appelé par `new_entry_from_stripe_subscription_invoice`). C'est la **seule** source du moyen d'un règlement Stripe (fiche D) et du courriel « SEPA en attente » (`ApiBillet/views.py` ~l.1230, fiche H). Champ posé **en plus** de `LigneArticle.payment_method` jusqu'à H. | `test_paiement_stripe_moyen_sepa_pose_a_la_mise_a_jour` |
| T15 | `trigger_A` ne fait plus d'appel HTTP à Fedow (`BaseBillet/triggers.py` ~l.289-300 : récompense en Celery `on_commit`). Règle de §4 reformulée : « encaisser **après** la transition de statut de la ligne, dans la même `atomic` ». | — |
| T22 | Numéros de ligne décalés (`_executer_avec_cle_idempotence` ~l.4611, `_payer_par_nfc` ~l.7902, `_executer_paiement_complementaire` ~l.9139) : relire au démarrage. | — |
