# Session 15 — Mode ecole + exports admin

## CONTEXTE

Tu travailles sur `laboutik/` et `Administration/`.
Lis `GUIDELINES.md`, `CLAUDE.md`, et le skill `unfold`. **Ne fais aucune operation git.**

Les tickets legaux et la tracabilite sont en place (session 14).
Cette session ajoute le mode ecole/test (exigence LNE 5) et les exports admin.

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — `sale_origin=LABOUTIK_TEST`

Dans `BaseBillet/models.py`, ajouter un choix dans `SaleOrigin` :

```python
LABOUTIK_TEST = 'LT'
# Dans les choices :
(LABOUTIK_TEST, _('LaBoutik (test mode)')),
```

Pas de migration (c'est un CharField choices, pas un enum DB).

## TACHE 2 — Flag `mode_ecole` sur LaboutikConfiguration

Deja prevu dans le design spec. Ajouter :

```python
mode_ecole = models.BooleanField(
    default=False,
    verbose_name=_("Training mode"),
    help_text=_("Active le mode ecole. Les donnees sont marquees comme fictives. "
                "/ Enables training mode. Data is marked as fictitious."),
)
```

Migration si pas deja fait en session 12.

## TACHE 3 — Bandeau "MODE ECOLE" sur l'interface POS

Dans `laboutik/templates/cotton/header.html` (ou le template principal POS),
ajouter un bandeau conditionnel :

```html
{% if config.mode_ecole %}
<div style="background: #ff6600; color: white; text-align: center; padding: 8px; font-weight: bold; font-size: 1.2em;">
    MODE ECOLE — SIMULATION
</div>
{% endif %}
```

Le bandeau doit etre **toujours visible** tant que le mode est actif (exigence LNE).

## TACHE 4 — Marquage des ventes en mode ecole

Dans `_creer_lignes_articles()` de `laboutik/views.py` :

```python
config = LaboutikConfiguration.get_solo()
if config.mode_ecole:
    sale_origin = SaleOrigin.LABOUTIK_TEST
else:
    sale_origin = SaleOrigin.LABOUTIK
```

Les tickets imprimes en mode ecole portent la mention "SIMULATION" (ajouter dans le formatter).

## TACHE 5 — Admin Unfold : vue detail rapport

Dans `Administration/admin/laboutik.py`, ajouter sur `ClotureCaisseAdmin` :

- Vue detail personnalisee avec template HTML
- Les 12 sections du `rapport_json` rendues dans des tableaux structures (pas JSON brut)
- Template : `Administration/templates/admin/cloture_detail.html`
- Utiliser les components Unfold (cards, tables)

## TACHE 6 — Actions admin : exports

Actions sur `ClotureCaisseAdmin` :

### Export PDF (WeasyPrint)
- Template A4 : `laboutik/templates/laboutik/pdf/rapport_comptable.html`
- En-tete : logo, raison sociale, SIRET, adresse, n° sequentiel, dates
- 12 sections tabulaires
- Pied : date generation, mention legale

### Export CSV
- Delimiteur `;` (standard europeen)
- Toutes les 12 sections comme blocs separes

### Export Excel (openpyxl)
- Verifier que openpyxl est dans `pyproject.toml`. Sinon signaler au mainteneur.
- 1 onglet par section. Entetes gras, totaux gras, colonnes auto-width.

### Action "Renvoyer par email"
- Envoie PDF + CSV en PJ via Celery

## TACHE 7 — Tests

Dans `tests/pytest/test_mode_ecole.py` :

- `test_mode_ecole_sale_origin` : en mode ecole → sale_origin = LABOUTIK_TEST
- `test_mode_ecole_exclu_rapport_prod` : le service exclut LABOUTIK_TEST du rapport normal
- `test_mode_ecole_inclus_rapport_test` : un rapport test inclut les lignes LABOUTIK_TEST
- `test_ticket_simulation` : ticket en mode ecole → contient "SIMULATION"

Dans `tests/pytest/test_exports.py` :

- `test_export_pdf_genere` : retourne un PDF non vide
- `test_export_csv_delimiteur` : delimiteur = `;`
- `test_export_csv_12_sections` : les 12 sections presentes

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_mode_ecole.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_exports.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] sale_origin LABOUTIK_TEST disponible
- [ ] mode_ecole sur LaboutikConfiguration
- [ ] Bandeau "MODE ECOLE" visible dans l'interface POS
- [ ] Ventes marquees LABOUTIK_TEST en mode ecole
- [ ] Tickets portent "SIMULATION" en mode ecole
- [ ] Vue detail HTML du rapport (pas JSON brut)
- [ ] Export PDF A4 formel
- [ ] Export CSV delimiteur `;`
- [ ] Export Excel (si openpyxl disponible)
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent
