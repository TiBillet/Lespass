# Session 12 — Rapports Comptables : modèle + service de calcul

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le rapport comptable (Ticket Z) est un document juridique légal en France.
Il remplace le `rapport_json` basique de la Phase 5 par un service de calcul complet.

Le code legacy de référence est `OLD_REPOS/LaBoutik/administration/ticketZ_V4.py`.
Lis-le pour comprendre la logique de calcul (TVA, solde caisse, habitus, etc.)
mais ne le copie pas tel quel — simplifie et adapte au nouveau modèle de données.

Le modèle de données actuel utilise `LigneArticle` (pas `ArticleVendu` du legacy).
Lis `BaseBillet/models.py` pour comprendre `LigneArticle` : champs `amount` (centimes),
`payment_method`, `sale_origin`, `vat`, `carte`, etc.

## TÂCHE 1 — Modèle `RapportComptable`

Dans `laboutik/models.py`, crée :

- `uuid` PK
- `cloture` OneToOne FK → ClotureCaisse (nullable — le Ticket X n'a pas de clôture)
- `numero_sequentiel` PositiveIntegerField — auto-incrémenté par PV, `unique_together`
- `point_de_vente` FK → PointDeVente (PROTECT)
- `responsable` FK → TibilletUser (SET_NULL, nullable)
- `datetime_debut`, `datetime_fin` DateTimeField
- Totaux (centimes) : `total_especes`, `total_carte_bancaire`, `total_cashless`, `total_cheque`, `total_general`
- `nombre_transactions` IntegerField
- `rapport_json` JSONField(default=dict) — structure détaillée
- `created_at` DateTimeField(auto_now_add)

Champs config dans `LaboutikConfiguration` :
- `fond_de_caisse` IntegerField(default=0) — montant initial tiroir (centimes)
- `rapport_emails` (JSONField, default=list) — destinataires envoi auto
- `rapport_periodicite` CharField(choices daily/weekly/monthly/yearly, default='daily')

Migration.

## TÂCHE 2 — `RapportComptableService`

Crée `laboutik/reports.py`. Classe avec 12 méthodes de calcul.

```python
class RapportComptableService:
    def __init__(self, point_de_vente, datetime_debut, datetime_fin):
        self.pv = point_de_vente
        self.debut = datetime_debut
        self.fin = datetime_fin
        self.lignes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=self.debut, datetime__lte=self.fin,
            status=LigneArticle.VALID,
        ).select_related('pricesold__productsold__product__categorie_pos', 'carte')
```

Méthodes à implémenter (toutes retournent un dict sérialisable JSON) :

1. `calculer_totaux_par_moyen()` — espèces, CB, NFC, chèque, total
2. `calculer_detail_ventes()` — par article groupé par catégorie, qty vendus/offerts, CA HT/TTC/TVA
   - TVA : `HT = TTC / (1 + taux/100)`, arrondi au centime
   - "Vendus" = paiements fiduciaires (CASH, CC, CHEQUE + cashless euro)
   - "Offerts" = paiements gratuits (FREE, cadeau)
3. `calculer_tva()` — par taux, somme HT/TVA/TTC
4. `calculer_solde_caisse()` — fond + entrées espèces − sorties espèces
5. `calculer_recharges()` — RE/RC/TM × moyen de paiement
6. `calculer_adhesions()` — nombre créées/renouvelées, total par moyen
7. `calculer_remboursements()` — vides carte, retours consigne
8. `calculer_habitus()` — cartes NFC distinctes, médiane recharge, panier moyen
   **SANS N+1** : utiliser `values('carte').annotate(total=Sum('amount'))` au lieu
   de boucler sur chaque carte
9. `calculer_billets_soiree()` — events dont `datetime` est dans la période,
   total billets (valid_tickets_count), vendus en caisse vs en ligne, scannés
10. `calculer_synthese_operations()` — tableau croisé type × moyen
11. `calculer_operateurs()` — total par caissier (si le champ existe sur LigneArticle)
12. `_infos_legales()` — SIRET/adresse depuis Configuration, n° séquentiel

Et un point d'entrée :
```python
def generer_rapport_complet(self):
    return {
        "totaux_par_moyen": self.calculer_totaux_par_moyen(),
        "detail_ventes": self.calculer_detail_ventes(),
        # ... les 12 sections
    }
```

## TÂCHE 3 — Tests

Crée `tests/pytest/test_rapport_comptable.py`.

Fixtures : créer des LigneArticle de test avec différents payment_method, montants, TVA.
Puis tester chaque méthode séparément :

- `test_totaux_par_moyen` : 3 lignes (espèces, CB, NFC) → totaux corrects
- `test_tva_calcul` : TVA 20% sur 1200 centimes TTC → HT=1000, TVA=200
- `test_solde_caisse` : fond 15000 + ventes espèces 5000 = 20000
- `test_habitus_sans_n_plus_1` : vérifier que le queryset utilise annotate (pas de boucle)
- `test_detail_ventes_par_categorie` : 2 catégories, sous-totaux corrects
- `test_rapport_complet` : vérifie que les 12 clés sont présentes dans le dict

## VÉRIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critère de succès

- [ ] Modèle RapportComptable créé avec migration
- [ ] `reports.py` avec 12 méthodes de calcul
- [ ] `generer_rapport_complet()` retourne un dict avec 12 clés
- [ ] TVA calculée correctement (HT = TTC / (1 + taux/100))
- [ ] Habitus sans N+1 (annotate, pas de boucle par carte)
- [ ] 6+ tests pytest verts
- [ ] Tous les tests existants passent
