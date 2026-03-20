# Session 13 — Rapports Comptables : admin Unfold + exports + envoi auto

## CONTEXTE

Tu travailles sur `laboutik/` et `Administration/`.
Lis `GUIDELINES.md`, `CLAUDE.md`, et le skill `unfold`. **Ne fais aucune opération git.**

Le `RapportComptableService` est en place (Session 12). Il faut maintenant :
- L'afficher dans l'admin Unfold avec un rendu HTML structuré
- Exporter en PDF, CSV, Excel
- Envoyer automatiquement via Celery Beat

## TÂCHE 1 — Admin Unfold `RapportComptableAdmin`

Lis `Administration/admin/laboutik.py`. Ajoute `RapportComptableAdmin` :

- **Section sidebar** : "Ventes" (conditionnelle `module_caisse`, après la section "Caisse")
- **List display** : numero_sequentiel, point_de_vente, responsable, datetime_fin, total_general
- **Filtres** : date, point_de_vente, responsable
- **Lecture seule** (pas de modification — document comptable immuable)
- **Vue détail personnalisée** : template HTML qui rend les 12 sections du rapport_json
  dans des tableaux structurés (pas juste le JSON brut)
- **Actions** : "Télécharger PDF", "Télécharger CSV", "Télécharger Excel", "Renvoyer par email"

Template détail : `Administration/templates/admin/rapport_comptable_detail.html`
Utilise les components Unfold (cards, tables) pour un rendu soigné.

## TÂCHE 2 — Export PDF

Lis `laboutik/pdf.py` (existant, Phase 5). Ajoute `generer_pdf_rapport_comptable()`.

Template : `laboutik/templates/laboutik/pdf/rapport_comptable.html`
Format A4 avec :
- En-tête : logo, raison sociale, SIRET, adresse, n° séquentiel, dates
- 12 sections tabulaires
- Pied de page : date génération, mention légale

Utilise WeasyPrint (déjà en place).

## TÂCHE 3 — Export CSV

Lis `laboutik/csv_export.py` (existant). Ajoute `generer_csv_rapport_comptable()`.
Délimiteur `;` (standard européen). Toutes les 12 sections comme blocs séparés.

## TÂCHE 4 — Export Excel

Crée `laboutik/excel_export.py`. Utilise `openpyxl`.
Vérifie que `openpyxl` est dans `pyproject.toml`. Sinon, signale au mainteneur.

1 onglet par section. Mise en forme : entêtes gras, totaux en gras, colonnes auto-width.

## TÂCHE 5 — Envoi automatique Celery Beat

Dans `laboutik/tasks.py`, ajoute :

```python
@shared_task
def generer_et_envoyer_rapport_periodique(periodicite='daily'):
    """Itère sur les tenants actifs, génère et envoie le rapport."""
    from Customers.models import Client
    for tenant in Client.objects.filter(categorie=Client.SALLE_SPECTACLE):
        with schema_context(tenant.schema_name):
            config = LaboutikConfiguration.get_solo()
            if not config.rapport_emails:
                continue
            # Calculer début/fin selon périodicité
            # Générer RapportComptable via service
            # Envoyer PDF + CSV + Excel par email
```

## TÂCHE 6 — Connecter `cloturer()` au service

Lis `laboutik/views.py`, `cloturer()`. Après la création de `ClotureCaisse`,
créer aussi un `RapportComptable` via `RapportComptableService.generer_rapport_complet()`.

## VÉRIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_export.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

Vérification manuelle dans l'admin : créer une clôture → rapport visible dans "Ventes" →
télécharger PDF/CSV/Excel.

### Critère de succès

- [ ] `RapportComptableAdmin` dans l'admin Unfold, section "Ventes"
- [ ] Vue détail HTML (pas JSON brut) avec les 12 sections
- [ ] Export PDF A4 formel avec en-tête légal
- [ ] Export CSV avec toutes les sections
- [ ] Export Excel (openpyxl) avec mise en forme
- [ ] `cloturer()` crée un `RapportComptable` automatiquement
- [ ] Celery Beat task pour envoi automatique
- [ ] Tous les tests passent
