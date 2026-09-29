# Chantier 05-A — Tables `Vente` et `Reglement`, service de vente

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D2 à D6, D18, R1
> Effort : 1,5 j — Dépend de : rien. **Migration : oui.**
> Personne n'appelle encore ce code à la fin de la fiche : aucun comportement ne change.

## 1. Ce que livre la fiche

1. Les tables `Vente` et `Reglement`, et les champs entiers de `LigneArticle` (§3 du tronc).
2. **Un seul point d'entrée** pour écrire une vente : `BaseBillet/services_vente.py`.
3. L'empreinte chaînée de la vente et sa vérification.
4. Une fabrique de test `tests/pytest/fabriques_vente.py`.

## 2. Modèles (`BaseBillet/models.py`)

Champs exacts : §3 du tronc. Précisions :

- `Vente.numero` : `PositiveIntegerField(null=True, blank=True)` +
  `UniqueConstraint(fields=["numero"], condition=Q(numero__isnull=False))`.
- `Vente.nature`, `Vente.statut` : `TextChoices` avec libellés FR (`_()`).
- `Vente.unite` : `CharField(max_length=36, default="EUR")` (uuid de la monnaie de
  points sinon).
- Montants : `IntegerField` (centimes signés). Pas de `DecimalField` pour de l'argent.
- `LigneArticle.vente` : `ForeignKey(Vente, null=True, blank=True,
  on_delete=PROTECT, related_name="articles")`.
- `LigneArticle.total_catalogue`, `part_offerte`, `total_ttc`, `total_tva` :
  `IntegerField(default=0)`. `source_offert` : `CharField` à choix (`OFFRIR`,
  `JETONS`), vide par défaut. `prix_achat_unitaire` : `IntegerField(null=True)`.
  `hors_chiffre_affaires` : `BooleanField(default=False)`, posé par `ajouter_article`
  (vrai pour un produit de recharge : `Product.methode_caisse` recharge euros /
  cadeau / temps — liste exacte à relire dans `BaseBillet/models.py` ~l.1363-1398).
  Figé : un changement ultérieur du produit ne change pas l'historique.
- `Reglement.vente` : `related_name="reglements"`, `on_delete=PROTECT`.
- `Reglement.fedow_transaction_uuid` : `UUIDField(null=True)` — pas de FK
  (`fedow_core` est en SHARED_APPS, `Reglement` en TENANT_APPS).
- `CommandeSauvegarde.vente` (`laboutik/models.py`) et `Commande.vente`
  (`BaseBillet/models.py`) : FK nullable vers `Vente` (utilisées en B et D).
- Aucune donnée existante n'est migrée (dev uniquement).

## 3. Le service (`BaseBillet/services_vente.py`)

Fonctions explicites, pas de classe à état caché. Chacune avec docstring FALC
(LOCALISATION, FLUX).

| Fonction | Rôle |
|---|---|
| `calculer_montants_article(prix_unitaire, quantite, taux_tva, part_offerte=0, total_catalogue_impose=None)` | **La seule formule d'argent du projet** (§2 du tronc). Renvoie un dict d'entiers : `total_catalogue`, `part_offerte`, `total_ttc`, `total_ht`, `total_tva`. `total_catalogue_impose` : utilisé pendant la transition pour une « part » dont l'argent réel est connu (§5 du tronc) ; retiré en fiche H. Refuse `part_offerte` hors de `[0, total_catalogue]` (même signe pour un avoir). |
| `ouvrir_vente(origine, nature, unite="EUR", point_de_vente=None, operateur=None, client=None, carte=None, vente_liee=None, idempotency_key=None)` | crée la vente `EN_ATTENTE` |
| `ajouter_article(vente, pricesold, quantite, prix_unitaire, taux_tva, part_offerte=0, source_offert="", prix_achat_unitaire=None, total_catalogue_impose=None, **champs_de_la_ligne)` | crée la `LigneArticle` avec ses montants entiers. `champs_de_la_ligne` = champs historiques (`payment_method`, `asset`, `status`, `reservation`…) que les producteurs posent encore pendant la transition |
| `ajouter_reglement(vente, moyen, montant, asset=None, carte=None, wallet=None, fedow_transaction_uuid=None, paiement_stripe=None, reference_externe="")` | crée le règlement ; `montant` doit être un `int` (refus d'un `Decimal` ou `float`) |
| `encaisser_vente(vente)` | voir §4 |
| `annuler_vente(vente)` | `EN_ATTENTE` → `ANNULEE`, sans numéro |

Règles posées par le service :

- `unite != "EUR"` (points) → `taux_tva` doit valoir 0 (refus sinon).
- Moyens « offert » : `MOYENS_OFFERTS = [LG, FREE]` (constante unique). Moyens
  « hors encaissement » pour les rapports : `MOYENS_OFFERTS + [NM]`.

## 4. `encaisser_vente(vente)` — le cœur

Appelée **dans** la transaction qui a créé la vente (`transaction.atomic()` du
producteur). Pas d'appel réseau pendant cette fonction.

```
1. Vérifier les deux égalités (§2 du tronc) :
     Σ reglements.montant                          == Σ articles.total_catalogue
     Σ reglements.montant (moyen ∉ MOYENS_OFFERTS) == Σ articles.total_ttc
   Sinon : lever EgaliteDeVenteRompue (message FR avec les deux sommes). Le producteur
   laisse remonter : l'atomic annule tout.
2. Prendre le verrou du lieu :
     SELECT pg_advisory_xact_lock(hashtext('vente-<schema_name>'))
3. Sous le verrou :
     numero = (plus grand numero du lieu) + 1   (1 pour la première)
     datetime_encaissement = timezone.now()
     totaux de la vente = sommes des articles (5 champs)
     previous_hmac = hmac_hash de la vente numero − 1 ("" pour la première)
     hmac_hash = calculer_hmac_vente(vente, cle, previous_hmac)
     statut = REGLEE
     save()
```

- Le verrou est libéré au COMMIT : le numéro et l'ordre de la chaîne sont les mêmes.
- Une vente `EN_ATTENTE` ou `ANNULEE` ne consomme **aucun** numéro.
- Une vente sans article et sans règlement est refusée (sauf `VIDAGE_CARTE` et
  `CORRECTION`, dont les règlements s'annulent : 0 = 0).

## 5. L'empreinte (`laboutik/integrity.py`)

Nouvelle fonction `calculer_hmac_vente(vente, cle, previous_hmac)` — l'ancienne
`calculer_hmac` (par ligne) reste jusqu'à la fiche H.

Message = `json.dumps(donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` :

```python
donnees = {
    "format": 1,
    "uuid": str(vente.uuid),
    "numero": vente.numero,
    "datetime_encaissement": vente.datetime_encaissement.isoformat(),
    "nature": vente.nature, "origine": vente.origine, "unite": vente.unite,
    "totaux": [total_catalogue, total_offert, total_ttc, total_ht, total_tva],
    "articles": [  # tries par uuid
        [uuid, pricesold_uuid, f"{qty:.6f}", amount, f"{vat:.2f}",
         total_catalogue, part_offerte, source_offert, total_ttc, total_ht, total_tva,
         hors_chiffre_affaires],
    ],
    "reglements": [  # tries par uuid
        [uuid, moyen, montant, asset_ou_vide, reference_externe],
    ],
    "previous_hmac": previous_hmac,
}
```

- `qty` et `vat` sont normalisés en texte (même valeur en mémoire et relue en base).
- Clé : `LaboutikConfiguration.get_solo().get_or_create_hmac_key()` (inchangée).

Nouvelle fonction `verifier_chaine_ventes(cle)` : parcourt les ventes `REGLEE` par
`numero` croissant et renvoie la liste des anomalies :

| Anomalie | Exemple |
|---|---|
| empreinte fausse | un article ou un règlement modifié après encaissement |
| maillon cassé | `previous_hmac` ≠ empreinte de la vente précédente |
| trou de numéro | vente 7 supprimée |
| égalité rompue | Σ règlements ≠ Σ catalogue (relu en base) |

**Aucune exception tolérée** (pas de `CorrectionPaiement` : D14).

## 6. Fabrique de test (`tests/pytest/fabriques_vente.py`)

`fabriquer_vente_encaissee(origine, articles=[...], reglements=[...], nature=VENTE)`
passe **par le service** (jamais `Vente.objects.create` direct) : une fabrique qui
contourne le service rendrait les tests aveugles aux égalités.

## 7. Tests

Fichiers :
- `tests/pytest/test_montants_article.py` — formule seule (pas de base).
- `tests/pytest/test_vente_service.py` — service ; **schéma dédié** pour tout ce qui
  lit la numérotation ou la chaîne (elles couvrent tout le lieu).
- `tests/pytest/test_montants_entiers_egalites.py` — test transversal (§8 du tronc),
  créé ici avec les ventes fabriquées.

| Test | Donnée → attendu |
|---|---|
| `test_trois_jus_a_350_font_1050_ht_875_tva_175` | 350 × 3, 20 % → 1050 / 875 / 175 |
| `test_fromage_0_350_kg_a_1290_arrondi_demi_haut` | 1290 × 0,350 = 451,5 → **452** (pas 451) |
| `test_part_offerte_300_sur_500_net_200_tva_sur_200` | 500, offert 300, 20 % → net 200, HT 167, TVA 33 |
| `test_avoir_moins_deux_biere_a_500` | −2 × 500, 20 % → −1000 / −833 / −167 |
| `test_taux_zero_ht_egal_net` | 0 % → HT = net, TVA 0 |
| `test_net_105_a_20_pourcent_ht_88_tva_17` | 105, 20 % → HT 88, TVA 17 (HT + TVA = net) |
| `test_total_catalogue_impose_est_repris_tel_quel` | part LE 500 imposée (qty 1,428571) → 500, pas 499,99985 arrondi |
| `test_part_offerte_superieure_au_total_refusee` | offert 600 sur 500 → refus |
| `test_montant_de_reglement_decimal_refuse` | `Decimal("5.5")` → refus |
| `test_encaisser_refuse_si_reglements_differents_du_catalogue` | 1050 d'articles, 1049 de règlements → exception, **rien en base** (numéro vide, statut EN_ATTENTE) |
| `test_encaisser_refuse_si_argent_different_du_net` | offert 300 réglé en CB au lieu de LG → refus |
| `test_numeros_consecutifs_sans_trou` | 3 ventes → 1, 2, 3 (schéma dédié) |
| `test_vente_annulee_ou_en_attente_ne_prend_pas_de_numero` | attente, annulée, réglée → la réglée a le n° 1 |
| `test_premiere_vente_chainee_sur_vide_puis_suivante_sur_la_precedente` | `previous_hmac` = "" puis = empreinte n° 1 |
| `test_modifier_un_article_apres_encaissement_casse_la_chaine` | `update(total_ttc=…)` → anomalie « empreinte fausse » sur cette vente |
| `test_modifier_un_reglement_apres_encaissement_casse_la_chaine` | idem sur un règlement |
| `test_supprimer_une_vente_laisse_un_trou_signale` | anomalie « trou de numéro » |
| `test_vidage_de_carte_sans_article_encaisse` | règlements +500 LE, −500 CA → encaissée |
| `test_vente_en_points_refuse_une_tva` | `unite` = points, taux 20 → refus |

Vus rouges : tous (le module n'existe pas) ; noter l'`ImportError`, puis, une fois les
modèles posés, voir chaque test échouer sur un service volontairement vide.

**Concurrence** (deux encaissements simultanés) : pas testable proprement en pytest
sans `transaction=True` (interdit). Vérification manuelle documentée dans le
CHANGELOG : script `manage.py tenant_command shell` lançant deux threads
d'encaissement → numéros distincts et chaîne valide.

Mutations :

| Mutation | Test qui doit tomber |
|---|---|
| `ROUND_HALF_UP` → `ROUND_HALF_EVEN` | fromage 451,5 |
| `total_tva = net − ht` → calcul séparé `round(net × taux / (100 + taux))` | `test_net_105_a_20_pourcent_ht_88_tva_17` (à ajouter : HT 87,5 → 88, TVA 17 ; calculée à part, la TVA vaudrait 18 et HT + TVA = 106 ≠ 105) |
| retirer la 2ᵉ égalité | argent ≠ net |
| `numero = max + 1` → `count() + 1` | trou de numéro après suppression / annulée |
| retirer `"reglements"` du message HMAC | modifier un règlement |
| `previous_hmac` = "" toujours | chaînage |
| supprimer le filtre `statut=REGLEE` de la numérotation | vente en attente numérotée |

## 8. Hors fiche

Aucun producteur n'appelle le service (fiches B, C, D). Aucun rapport ne lit ces
tables (fiche F). Pas d'admin (fiche G).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-A-vente-reglement.md` (migration :
oui ; nouvelles chaînes i18n : libellés des natures et statuts).
