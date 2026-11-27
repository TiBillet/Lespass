# Admin : boutons d'enregistrement / Admin: save buttons

**Date :** 2026-11-27
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Les 11 pages de configuration (modèles django-solo : Paramètres, Envoi des rapports, LaBoutik, Ghost, Brevo, etc.) n'ont plus qu'un bouton « Enregistrer ». Il enregistre et reste sur la page, avec le message « Modifications enregistrées. ».
- Sur toutes les autres pages de l'admin, le bouton `_continue` affiche son vrai libellé : « Enregistrer et continuer les modifications » (au lieu de « Enregistrer et afficher »).
/ The 11 configuration pages get a single "Save" button that stays on the page, with a French message. Everywhere else, the "_continue" button shows its real label.

**Pourquoi / Why :**
- django-solo renvoyait au tableau de bord après « Enregistrer », avec un message en anglais (« Envoi des rapports was changed successfully. ») : solo n'a pas de traduction française.
- Avec Unfold 0.89 et Django 4.2, `can_change` est perdu dans le `{% component %}` du bouton (`_flatten_context`, unfold/templatetags/unfold.py) : le gabarit affichait le libellé de secours « Save and view ».
/ django-solo redirected to the dashboard with an untranslated message. Unfold 0.89 + Django 4.2 lose `can_change` inside the button component.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/base.py` | Nouvelle classe `SingletonAdmin` : `change_view` cache `_continue`, `response_change` reste sur la page |
| `Administration/admin_tenant.py` | 7 admins de configuration héritent de `SingletonAdmin` |
| `Administration/admin/laboutik.py`, `comptabilite/admin.py`, `controlvanne/admin.py`, `pages/admin.py` | 1 admin de configuration chacun hérite de `SingletonAdmin` |
| `Administration/templates/admin/submit_line.html` | Nouveau : copie du gabarit d'Unfold 0.89.0 avec un `{% with can_change=can_change %}` autour du bouton `_continue` |
| `tests/pytest/test_admin_boutons_enregistrement.py` | Nouveau : 4 tests |

**i18n :** une nouvelle chaîne, « Modifications enregistrées. » (workflow i18n à lancer).

**À la mise à jour d'Unfold :** comparer `Administration/templates/admin/submit_line.html` avec le gabarit d'Unfold. Le supprimer si le bug est corrigé (ou au passage à Django 5).

---

## Comment tester (a la main) / Manual test
### Test 1 — page de configuration
1. Ouvrir `https://lespass.tibillet.localhost/admin/BaseBillet/configuration/`.
2. Un seul bouton en bas : « Enregistrer ».
3. Cliquer dessus : on reste sur la page, le message « Modifications enregistrées. » s'affiche.
4. Même chose sur `/admin/comptabilite/configurationdesrapports/`.

### Test 2 — page ordinaire
1. Ouvrir un événement dans l'admin.
2. Les boutons sont : « Enregistrer », « Enregistrer et continuer les modifications », « Enregistrer et ajouter un nouveau ».
3. « Enregistrer et continuer les modifications » reste sur la fiche. « Enregistrer » revient à la liste (inchangé).

### Limite connue
Sur « Paramètres », l'onglet ouvert n'est pas conservé après l'enregistrement : la page revient sur « Identité du lieu ». C'était déjà le cas avec l'ancien bouton `_continue`.

### Verifs DB / Playwright
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_boutons_enregistrement.py -q
```
Le test E2E `tests/e2e/test_admin_configuration.py` clique sur `_save` puis lit la base : il doit toujours passer.
