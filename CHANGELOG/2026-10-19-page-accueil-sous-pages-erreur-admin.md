# Pages : erreur 500 en admin quand l'accueil a des sous-pages / Pages: admin 500 when the home page has sub-pages

**Date :** 2026-10-19
**Migration :** Non

## Resume / Summary
**Quoi / What :** une page ne peut plus être rangée sous la page d'accueil. Les erreurs de `Page.clean()` qui visent un champ absent du formulaire admin (`est_accueil`, ou `parent` dans la liste) s'affichent maintenant comme des erreurs générales, au lieu de provoquer une erreur 500.
/ A page can no longer be filed under the home page. `Page.clean()` errors aimed at a field missing from the admin form now show as general form errors instead of a 500.

**Pourquoi / Why :** Sentry BILLETTERIE-COOP-V7 (`ValueError: 'PageForm' has no field named 'est_accueil'`). Rien n'empêchait de donner l'accueil comme parent à une sous-page. Ensuite, chaque bascule de « Publiée » dans la liste revalidait l'accueil, et ça plantait.
/ Nothing prevented picking the home page as a parent. Afterwards, every "Published" toggle in the list revalidated the home page and crashed.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/models.py` | `Page.clean()` : refuse un `parent` qui est la page d'accueil (erreur sur `parent`) |
| `pages/admin.py` | `PageAdminForm` : une erreur sur un champ absent devient une erreur générale. Branchée sur la fiche (`form`) et sur la liste (`get_changelist_form`) |
| `pages/admin.py` | `formfield_for_foreignkey` : la page d'accueil n'est plus proposée dans la liste déroulante « Page parente » |
| `tests/pytest/test_pages.py` | 4 tests : règle côté enfant, accueil absent du choix de parent, liste admin sans 500, fiche admin sans 500 |

Nouvelle chaîne traduisible : « La page d'accueil ne peut pas avoir de sous-pages : choisissez une autre page parente. »

Fixes BILLETTERIE-COOP-V7

---

## Comment tester (a la main) / Manual test

### Test 1 — l'accueil ne peut pas devenir parent
1. Admin → Pages → ouvrir une page qui n'est pas l'accueil.
2. Ouvrir la liste déroulante « Page parente ».
3. Attendu : la page d'accueil n'y figure pas. (Par l'API v2, `isPartOf` vers l'accueil est refusé par `Page.clean()`.)

### Test 2 — un accueil déjà incohérent ne plante plus la liste
1. Rendre l'accueil incohérent depuis le shell (contourne `clean()`) :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django_tenants.utils import schema_context
   with schema_context('lespass'):
       from pages.models import Page
       Page.objects.create(titre='Test', slug='test-sous-accueil', parent=Page.objects.get(est_accueil=True))"
   ```
2. Admin → Pages → basculer « Publiée » sur n'importe quelle ligne → Enregistrer.
3. Attendu : pas d'erreur 500. Le bandeau rouge « Corrigez l'erreur ci-dessous. » apparaît, et le message « Cette page a des sous-pages… » s'affiche au-dessus de la ligne de l'accueil.
4. Ouvrir la fiche de l'accueil → Enregistrer : le même message s'affiche en haut de la fiche.
5. Nettoyage : `Page.objects.filter(slug='test-sous-accueil').delete()`.
