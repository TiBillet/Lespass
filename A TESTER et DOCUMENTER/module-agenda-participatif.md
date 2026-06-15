# Module « Agenda participatif »

## Ce qui a été fait

Le wizard public de proposition d'évènement est désormais conditionné par un
module Groupware dédié, **désactivé par défaut**.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Champ `module_agenda_participatif` (`BooleanField`, `default=False`) sur `Configuration` |
| `BaseBillet/migrations/0210_configuration_module_agenda_participatif.py` | Migration du champ |
| `Administration/admin/dashboard.py` | Entrée `MODULE_FIELDS` → carte dashboard + texte d'aide |
| `BaseBillet/templates/reunion/views/event/list.html` | Bouton « Proposer un évènement » affiché seulement si module actif |
| `BaseBillet/validators.py` | `WizardEventPublicSerializer.validate()` refuse la création si module désactivé |

## Tests à réaliser

### Test 1 : Module désactivé par défaut
1. Sur un tenant, aller sur le dashboard admin.
2. **Attendu :** carte « Agenda participatif » présente, toggle **éteint** (off).
3. Aller sur la page agenda publique (`/event/`).
4. **Attendu :** le bouton « Proposer un évènement » est **absent**.

### Test 2 : Activation du module
1. Sur le dashboard, activer le toggle « Agenda participatif » (modal de confirmation → HX-Refresh).
2. Recharger la page agenda publique.
3. **Attendu :** le bouton « Proposer un évènement » apparaît.

### Test 3 : Garde serveur (création conditionnée)
1. Module **désactivé**.
2. Atteindre directement l'URL du wizard public et tenter d'ajouter/soumettre un évènement.
3. **Attendu :** `WizardEventPublicSerializer` rejette → erreur « La proposition d'évènement n'est pas activée. » (la proposition n'est pas créée).
4. Module **activé** : l'ajout d'un brouillon fonctionne normalement.

### Test 4 : Parcours admin inchangé
1. Connecté en admin, le bouton « Ajouter un évènement » (wizard admin) reste visible **quel que soit** l'état du module.
2. **Attendu :** la création admin d'évènement n'est jamais bloquée par ce module.

## Vérification en base
```bash
docker exec -e TEST=1 lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from BaseBillet.models import Configuration; print(Configuration.get_solo().module_agenda_participatif)"
```

## Note tests automatisés
`tests/pytest/test_event_wizard_public.py` contient 10 tests **déjà en échec
avant cette modification** : ils simulent l'ancien flux OTP/anonyme alors que la
vue exige désormais une connexion (`_require_login_or_redirect`, OTP « parké »).
Ces échecs sont **indépendants** de ce module (le finalize n'utilise pas le
serializer ; la garde de connexion redirige avant). Les tests
`tests/pytest/test_event_proposal_admin.py` (validation en admin) passent.

## Compatibilité
- `default=False` : aucun tenant existant ne voit le bouton tant qu'il n'active pas le module.
- Aucun impact sur le wizard admin ni sur l'affichage/validation des propositions en admin.
