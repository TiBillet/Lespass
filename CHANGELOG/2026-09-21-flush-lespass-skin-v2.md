# Flush : le tenant lespass démarre en skin V2 / Flush: the lespass tenant starts with the V2 skin

**Date :** 2026-09-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** après un `flush.sh`, le tenant `lespass` est en skin `V2`.
`charger_site_lespass` (appelée par `demo_data_v2`) force maintenant `V2` au
lieu de `reunion` (classic). Le défaut du modèle `ConfigurationSite.skin` ne
change pas : les autres tenants restent en `reunion`.
/ After `flush.sh`, the `lespass` tenant uses the `V2` skin. `charger_site_lespass`
now forces `V2` instead of `reunion`. The model default is unchanged.

**Pourquoi / Why :** V2 est le skin de travail sur lespass. Chaque flush le
remettait en classic et il fallait le rebasculer à la main dans l'admin.
/ V2 is the working skin on lespass; every flush reset it to classic.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/management/commands/charger_site_lespass.py` | `_forcer_skin()` pose `V2` ; docstring et `help` mis à jour |
| `Administration/management/commands/demo_data_v2.py` | Commentaires : lespass en V2, la démo couvre trois skins |

---

## Comment tester (a la main) / Manual test

### Test 1 — la commande seule
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_site_lespass`
2. La sortie affiche `→ skin forcé à 'V2'.`
3. Ouvrir `https://lespass.tibillet.localhost/` : la page s'affiche en skin V2.
4. Admin → Configuration du site : « Thème graphique du site » = « Thème V2 (en béta) ».

### Test 2 — `--no-skin` ne touche pas au skin
1. Dans l'admin, passer lespass en « Réunion ».
2. `docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_site_lespass --no-skin`
3. Le skin reste « Réunion ». Le remettre en V2 ensuite.

### Test 3 — après un flush complet
1. Lancer `flush.sh`.
2. Vérifier les skins des tenants de démo :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django_tenants.utils import tenant_context
   from Customers.models import Client
   for c in Client.objects.exclude(schema_name='public'):
       with tenant_context(c):
           from pages.models import ConfigurationSite
           print(c.schema_name, ConfigurationSite.get_solo().skin)
   "
   ```
3. Attendu : `lespass V2`, `festival faire_festival` (en mode `--full`), les autres en `reunion`.
