# Images locales pour les ressources de démo / Local images for demo resources

**Date :** 2026-11-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** `create_booking_fixtures` ne télécharge plus d'images depuis
picsum.photos. Chaque ressource de démo reçoit une image commitée
(`Administration/fixtures/demo_events/event-01.jpg` à `event-05.jpg`), posée sur
`Resource.img`. / `create_booking_fixtures` no longer downloads images from
picsum.photos. Each demo resource gets a committed image, set on `Resource.img`.

**Pourquoi / Why :** le flush de démo appelait picsum 5 fois par lieu, avec un délai
de 10 s : jusqu'à 50 s perdues par lieu quand picsum ne répondait pas. Et l'image
était posée sur `Product.img`, que les pages `/booking/` n'affichent pas : les
ressources de démo restaient sans image. / The demo flush called picsum 5 times per
venue (10 s timeout each). The image went to `Product.img`, which `/booking/` pages
never show.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/management/commands/create_booking_fixtures.py` | Plus de `requests` ; image locale lue et posée sur `Resource.img` si absente |
| `tests/pytest/test_demo_recap_de_la_veille.py` | Retrait du mock de `requests.get`, devenu inutile |

---

## Comment tester (a la main) / Manual test
### Test 1 — flush de démo
1. Lancer le flush / `demo_data_v2` habituel.
2. Vérifier que le message « Image non téléchargée pour … » n'apparaît plus.
3. Vérifier que l'étape « Création des données booking pour … » est rapide (~1 s par lieu).

### Test 2 — affichage
1. Ouvrir `https://lespass.tibillet.localhost/booking/`.
2. Les 5 ressources de démo ont une image sur leur carte.
3. Ouvrir une ressource : l'image apparaît en haut de sa page.

### Verifs DB
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from booking.models import Resource
with tenant_context(Client.objects.get(schema_name='lespass')):
    print([(r.name, r.img.name) for r in Resource.objects.all()])
"
```
