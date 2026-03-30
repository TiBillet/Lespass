# Session 18 — Archivage fiscal + acces administration

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Les clotures, corrections, et le menu ventes sont en place (sessions 12-17).
Cette session couvre l'archivage des donnees et l'acces pour l'administration fiscale
(exigences LNE 10, 11, 12, 15, 19).

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — Management command `archiver_donnees`

Cree `laboutik/management/commands/archiver_donnees.py`.

Export des donnees d'encaissement en format ouvert (CSV + JSON) :
- Toutes les LigneArticle de la periode
- Toutes les ClotureCaisse de la periode
- Toutes les CorrectionPaiement de la periode
- Toutes les ImpressionLog de la periode
- Donnees cumulatives et perpetuelles

Contraintes :
- Periode max = 1 an ou 1 exercice fiscal (exigence 11)
- Horodatage dans le nom du fichier
- Hash HMAC de l'archive (verifiable independamment du systeme)
- Format : ZIP contenant CSV + JSON + fichier hash

```bash
docker exec lespass_django poetry run python manage.py archiver_donnees \
    --tenant=demo --debut=2026-01-01 --fin=2026-12-31 --output=/archives/
```

## TACHE 2 — Integrite des archives (Ex.12)

Le fichier hash dans l'archive permet de verifier l'integrite :

```python
# hash.json dans l'archive :
{
    "algorithme": "HMAC-SHA256",
    "date_generation": "2026-12-31T23:59:59",
    "fichiers": {
        "lignes_article.csv": "abc123...",
        "clotures.csv": "def456...",
        "corrections.csv": "ghi789...",
    },
    "hash_global": "xyz...",
}
```

## TACHE 3 — Management command `verifier_archive`

```bash
docker exec lespass_django poetry run python manage.py verifier_archive \
    --archive=/archives/demo_2026.zip
```

Verifie que les hash correspondent aux fichiers. Utilisable **independamment du systeme**
(la commande n'a besoin que du fichier ZIP et de la cle HMAC).

## TACHE 4 — Tracabilite des operations (Ex.15)

Journal securise des operations d'archivage, purge, restauration.

Modele simple `JournalOperation` ou utiliser le systeme de logging Django
avec un handler dedie qui ecrit dans la DB avec chainage HMAC.

A minima : chaque archivage/purge/restauration cree une entree horodatee
avec l'identifiant du PV et l'operateur.

## TACHE 5 — Acces administration fiscale (Ex.19)

### Management command `acces_fiscal`

Export complet de toutes les donnees d'encaissement pour l'administration fiscale :

```bash
docker exec lespass_django poetry run python manage.py acces_fiscal \
    --tenant=demo --output=/export_fiscal/
```

Genere un dossier avec :
- Export CSV de toutes les donnees (lignes, clotures, corrections, impressions)
- Outil de verification d'integrite (script Python autonome ou instructions)
- README explicatif en francais (pour le controleur fiscal non-informaticien)

### Vue admin "Acces fiscal"

Dans l'admin Unfold, section "Ventes" :
- Bouton "Exporter pour l'administration fiscale"
- Genere le ZIP et le propose au telechargement
- Lecture seule (pas de modification possible)

## TACHE 6 — Tests

Dans `tests/pytest/test_archivage_fiscal.py` :

- `test_archiver_genere_zip` : la commande produit un ZIP non vide
- `test_archive_contient_csv` : le ZIP contient les fichiers attendus
- `test_archive_hash_integrite` : le hash correspond aux fichiers
- `test_verifier_archive_ok` : archive non modifiee → OK
- `test_verifier_archive_ko` : fichier modifie dans le ZIP → echec
- `test_acces_fiscal_genere_export` : la commande produit un dossier complet
- `test_journal_operation_archivage` : l'archivage cree une entree journal

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Management command `archiver_donnees` fonctionnel
- [ ] Archive en format ouvert (CSV + JSON dans ZIP)
- [ ] Hash HMAC de l'archive verifiable independamment
- [ ] Periode max 1 an par archive
- [ ] Management command `verifier_archive` fonctionnel
- [ ] Journal des operations d'archivage securise
- [ ] Management command `acces_fiscal` avec README francais
- [ ] Vue admin "Acces fiscal" en lecture seule
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent
