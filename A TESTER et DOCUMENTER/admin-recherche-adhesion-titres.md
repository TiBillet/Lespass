# Admin — Recherche par adhésion + titres « Adhésion / … »

## Ce qui a été fait
1. **Recherche users** (changelist `HumanUserAdmin`) : cherche aussi dans les
   nom/prénom des **adhésions** (`memberships__first_name`, `memberships__last_name`),
   en plus de `email` / `first_name` / `last_name` de l'user.
2. **Titre du modèle** `Membership` → « Adhésion / Abonnement / Pass » (page admin).
3. **Sidebar** : item adhésions → « Adhésion / Pass ».

### Fichiers
| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | `search_fields` + `memberships__first_name/last_name` |
| `BaseBillet/models.py` | `Membership.Meta` verbose_name(_plural) |
| `BaseBillet/migrations/0213_alter_membership_options.py` | options (no-op DB) |
| `Administration/admin/dashboard.py` | item sidebar « Adhésion / Pass » |

## Tests à réaliser (manuel)

### Test 1 : recherche par nom de l'user
1. `/admin/AuthBillet/humanuser/` → barre de recherche → taper le **nom de famille d'un user**.
2. **Attendu** : le compte apparaît.

### Test 2 : recherche par nom saisi sur l'adhésion
1. Repérer une adhésion dont le **nom de l'adhérent·e diffère** du compte
   (ou est renseigné alors que le compte ne l'est pas).
2. Rechercher ce nom dans le changelist users.
3. **Attendu** : le compte propriétaire de l'adhésion apparaît (pas de doublon).

### Test 3 : titres
1. Page `/admin/BaseBillet/membership/` → **titre « Adhésion / Abonnement / Pass »**.
2. Sidebar (module adhésion actif) → item **« Adhésion / Pass »** sous la section
   « Adhésions ».

## Vérification logique (déjà validée en shell)
```
(a) recherche nom user      -> compte trouvé : True
(b) recherche nom adhésion  -> compte trouvé : True
```
(via `HumanUserAdmin.get_search_results`).

## Notes
- `distinct()` ajouté automatiquement par Django (recherche sur relation to-many).
- Migration `0213` = options du modèle uniquement, aucun changement de schéma.
- i18n : nouvelles chaînes FR (`Adhésion / Abonnement / Pass`, `Adhésion / Pass`)
  à compiler par le mainteneur.
- La section sidebar « Adhésions » (titre de groupe) est **inchangée** ; seul
  l'item cliquable est renommé. Dis-le-moi si tu voulais aussi la section.
```
