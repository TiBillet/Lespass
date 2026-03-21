# Session 08c — Federation cross-tenant

## Statut : FAIT (2026-03-21)

## Depend de : 08a (fixtures conftest.py)

## Objectif

Convertir le test de federation d'assets cross-tenant (PW 31).

## Ce qui a ete fait

### conftest.py modifie

- `django_shell` : ajout parametre `schema` (defaut "lespass") pour executer du code sur un autre tenant (ex: `django_shell("...", schema="chantefrein")`)

### 1 fichier cree

| Fichier | Tests | Source TS | Resultat |
|---|---|---|---|
| `test_asset_federation.py` | 1 | PW 31 | PASS |

### Resultats

- **31 tests E2E** (30 existants + 1 nouveau)
- **29 passed, 2 skipped**
- **178 tests pytest inchanges**

### Detail du test (12 etapes)

1. Login admin Lespass
2. Naviguer vers `/admin/fedow_core/asset/`
3. Creer asset `PW Test Fed <random_id>` (TLF, EUR)
4. Editer → inviter Chantefrein via Tom Select (autocomplete Unfold)
5. Verifier changelist Lespass : "Lieux federes" = Lespass seul
6-7. Login sur Chantefrein (URLs absolues, flow manuel)
8. Verifier invitation visible (`data-testid="asset-invitations-panel"`)
9. Accepter invitation → message "Invitation acceptee"
10. Verifier changelist Chantefrein : Lespass + Chantefrein
11. Verifier lecture seule pour Chantefrein
12. Retour Lespass : verifier Lespass + Chantefrein

### Points d'attention

1. **`module_monnaie_locale` sur chantefrein** : etait `False` en base dev. Le test l'active en setup via `django_shell(schema="chantefrein")`.

2. **Login cross-tenant** : `login_as_admin(page)` resout vers `baseURL` (Lespass). Pour Chantefrein, login manuel avec URLs absolues (`https://chantefrein.tibillet.localhost/`). Les cookies sont per-subdomain → la session Lespass reste active.

3. **Tom Select** (autocomplete Unfold) : `page.get_by_role("searchbox").last` puis `page.get_by_role("option", name=re.compile(r"Chantefrein"))`.

4. **Pagination changelist** : toujours filtrer par nom (`?q=...`) pour eviter que l'asset soit invisible sur la 1ere page.

## Verification

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_asset_federation.py -v -s --tb=long
# 1 passed

docker exec lespass_django poetry run pytest tests/e2e/ --co -q | tail -1
# 31 tests collected
```
