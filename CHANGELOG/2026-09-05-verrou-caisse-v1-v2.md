# Verrou caisse V1 / V2 sur un même lieu / V1-V2 cash register lock on a single venue

**Date :** 2026-09-05
**Migration :** Non

## Resume / Summary

**Quoi / What :** Un lieu ne peut plus héberger à la fois la caisse LaBoutik V2 (intégrée
à Lespass) et une caisse LaBoutik V1 (conteneur séparé). L'appairage V1
(`/api/onboard_laboutik/`) est refusé en 409 tant que le module « Caisse & restauration »
est actif sur le lieu. Le tenant de démo `festival` sort désormais du flush avec la caisse
V2 éteinte, puisqu'il est destiné à la V1.
/ A venue can no longer run both the V2 cash register (built into Lespass) and a V1 POS
(separate container). V1 pairing is refused with a 409 while `module_caisse` is on. The
`festival` demo tenant now comes out of the flush with the V2 register off.

**Pourquoi / Why :** Les deux caisses tiennent la monnaie dans un moteur différent — la V2
dans `fedow_core` (base locale), la V1 dans le Fedow distant — et rien ne réconcilie les
deux soldes. Rien n'empêchait l'appairage jusqu'ici : le handshake passait, et le lieu se
retrouvait dans un état bâtard. S'ajoute un effet de bord côté Fedow : le handshake V1 pose
une clé RSA cashless sur la place, ce qui retire à Lespass le droit d'appeler Fedow avec sa
seule clé de place (`Fedow/fedow_core/permissions.py:256`) — les appels du kiosk et de la
caisse V2 depuis ce lieu tombent alors en 403.
/ Both registers keep the money in a different engine, with nothing reconciling the two
balances. Nothing prevented the pairing until now. On top of that, the V1 handshake sets a
cashless RSA key on the Fedow place, which revokes Lespass' key-only access (403).

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `Onboard_laboutik.post()` : refus 409 JSON si **`module_caisse`, `module_kiosk` ou `module_monnaie_locale`** est actif. Verrou **inconditionnel** (pas de désarmement en DEBUG). La réponse nomme les modules fautifs (`"modules": [...]`). Les trois sont concernés pour la même raison : le handshake V1 pose une clé RSA cashless sur la place Fedow, ce qui retire à Lespass son accès key-only (`Fedow/fedow_core/permissions.py:256`) — kiosk et monnaie locale tombent en 403 autant que la caisse. |
| `Administration/management/commands/demo_data_v2.py` | Clé `caisse_v1_legacy: True` sur la fixture `Festival` ; `module_monnaie_locale` / `module_caisse` / `module_kiosk` désormais conditionnés à ce flag au lieu d'être activés partout. |
| `../LaBoutik/administration/management/commands/install.py` | Garde `if not handshake_lespass.ok:` avant le `.json()` du handshake → `CommandError` lisible au lieu d'un `JSONDecodeError` opaque. |
| `../LaBoutik/administration/management/commands/install.py` | Correction `prepa_cuisine.printer = tm20O` → `tm20` (typo introduite le 2026-07-22 par le commit `3fdba31`, bloquait tout `install --tdd`). |

**i18n :** cette modification ajoute **1 chaîne traduisible** (le message de refus 409, msgid
en français). Le workflow i18n est à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

Prérequis : la stack tri-partite tourne (`docker compose -f docker-compose-laboutik-V1.yml up -d`),
Fedow puis Lespass ont été flushés dans cet ordre.

### Test 1 — le tenant festival sort du flush en V1

Après `./flush.sh` côté Lespass :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Customers.models import Client
from django_tenants.utils import tenant_context
from BaseBillet.models import Configuration
for schema in ['lespass', 'festival']:
    with tenant_context(Client.objects.get(schema_name=schema)):
        c = Configuration.get_solo()
        print(f'{schema:12} caisse={c.module_caisse} monnaie={c.module_monnaie_locale} kiosk={c.module_kiosk}')
"
```

Attendu :
- `lespass` → `caisse=True monnaie=True kiosk=True`
- `festival` → `caisse=False monnaie=False kiosk=False`

Les autres modules (billetterie, adhésion, crowdfunding, fédération, inventaire) restent à
`True` sur les deux : `festival` reste un lieu de billetterie normal.

### Test 2 — le flush LaBoutik V1 passe sur festival

`.env` : `LESPASS_TENANT_URL='https://festival.tibillet.localhost/'`, `ADMIN_LABOUTIK='jturbeaux+fest@pm.me'`.

```bash
docker exec -ti laboutik_django bash
./flush.sh
```

Attendu : `Lespass Plugged !` puis `Fedow handhshake OK`, et le flush va jusqu'au
`runserver`. Vérifier ensuite côté Lespass que `festival.Configuration.server_cashless`
vaut `https://laboutik.tibillet.localhost`.

### Test 3 — le verrou refuse l'appairage quand la caisse V2 est active

Réactiver la caisse V2 sur festival, puis retenter le flush LaBoutik :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Customers.models import Client
from django_tenants.utils import tenant_context
from BaseBillet.models import Configuration
with tenant_context(Client.objects.get(schema_name='festival')):
    c = Configuration.get_solo()
    c.module_monnaie_locale = True
    c.module_caisse = True
    c.save()
    print('caisse V2 reactivee sur festival')
"
```

Puis, dans le conteneur LaBoutik : `poetry run ./manage.py install --tdd`

Attendu — un message **lisible**, pas une traceback JSON :

```
CommandError: Handshake Lespass refuse par https://festival.tibillet.localhost/
(HTTP 409) : La caisse LaBoutik V2 est active sur ce lieu. Désactivez le module
« Caisse & restauration » avant de connecter une caisse LaBoutik V1.
```

Côté Lespass, le log doit porter :
`Onboard LaBoutik V1 refuse sur le tenant festival : la caisse V2 est active.`

### Test 4 — non-régression sur lespass (V2)

`https://lespass.tibillet.localhost/laboutik/caisse/` répond toujours 200 avec la carte
primaire, connecté en `jturbeaux@pm.me`.

⚠️ Rappel : `/laboutik/caisse/` exige d'être **admin du tenant** (M2M `client_admin`,
`AuthBillet/models.py:212`), pas seulement superuser. `jturbeaux@pm.me` est admin de
`lespass` uniquement ; l'admin de `festival` est `jturbeaux+fest@pm.me`.

### Vérif complémentaire

`docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → 0 issue.
