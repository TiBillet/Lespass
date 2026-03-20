# Session 11 — Impression : backends Sunmi + Celery + formatters

## CONTEXTE

Tu travailles sur `laboutik/printing/` (module d'impression modulaire).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Les modèles et l'interface sont en place (Session 10). Il faut maintenant :
- Implémenter les 2 backends (Cloud + Inner)
- Créer le PrinterConsumer WebSocket dédié
- Écrire les formatters de tickets
- Créer les tâches Celery avec retry

## TÂCHE 1 — `SunmiCloudBackend`

Crée `laboutik/printing/sunmi_cloud.py`. Utilise la bibliothèque `sunmi_cloud_printer.py`
(Session 10) pour construire le ticket ESC/POS et l'envoyer via l'API Sunmi Cloud.

- `can_print()` : vérifie `printer.sunmi_serial_number` + `config.get_sunmi_app_id/key()`
- `print_ticket()` : charger credentials, créer `SunmiCloudPrinter`, builder le ticket,
  `pushContent(trade_no, sn, ...)`
- `check_online()` : appel API `onlineStatus` → retourne True/False

## TÂCHE 2 — `SunmiInnerBackend`

Crée `laboutik/printing/sunmi_inner.py`. Envoie les commandes JSON au terminal
via WebSocket (`channel_layer.group_send`).

- `can_print()` : vérifie que le printer_uuid est valide
- `print_ticket()` : convertit `ticket_data` en liste de commandes JSON
  (`[{"type": "text", "value": "..."}, {"type": "cut"}]`) et envoie via
  `async_to_sync(channel_layer.group_send)(f"printer-{printer.uuid}", {...})`

## TÂCHE 3 — `PrinterConsumer`

Lis `wsocket/consumers.py`. Ajoute `PrinterConsumer` (séparé de `LaboutikConsumer`) :

```python
class PrinterConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.printer_uuid = self.scope["url_route"]["kwargs"]["printer_uuid"]
        self.group_name = f"printer-{self.printer_uuid}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def print_ticket(self, event):
        await self.send(text_data=json.dumps({"action": "print", "commands": event["commands"]}))
```

Lis `wsocket/routing.py`. Ajoute la route :
```python
re_path(r'ws/printer/(?P<printer_uuid>[0-9a-f-]+)/$', consumers.PrinterConsumer.as_asgi()),
```

## TÂCHE 4 — Formatters

Crée `laboutik/printing/formatters.py`. 4 fonctions qui retournent un dict `ticket_data`
indépendant du backend :

- `formatter_ticket_vente(lignes_articles, pv, operateur, moyen)` : ticket client standard
- `formatter_ticket_billet(ticket, reservation, event)` : billet avec QR code
- `formatter_ticket_commande(commande, articles_groupe, printer)` : ticket cuisine/bar
- `formatter_ticket_cloture(cloture)` : Z-ticket

Chaque formatter retourne un dict avec : `type`, `header`, `articles`, `total`, `footer`, `qrcode`.

## TÂCHE 5 — Celery tasks

Crée `laboutik/printing/tasks.py` :

```python
@shared_task(bind=True, max_retries=10)
def imprimer_async(self, printer_pk, ticket_data):
    """Impression avec retry exponentiel."""
    try:
        printer = Printer.objects.get(pk=printer_pk)
        result = imprimer(printer, ticket_data)
        if not result["ok"]:
            raise Exception(result["error"])
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(5 * (2 ** self.request.retries), 300))

@shared_task(bind=True, max_retries=10)
def imprimer_commande(self, commande_pk):
    """Split commande par CategorieProduct.printer → 1 ticket par imprimante."""
    commande = CommandeSauvegarde.objects.get(pk=commande_pk)
    articles = commande.articles.select_related('product__categorie_pos__printer').all()
    par_imprimante = {}
    for article in articles:
        printer = article.product.categorie_pos.printer if article.product.categorie_pos else None
        if printer and printer.active:
            par_imprimante.setdefault(str(printer.pk), []).append(article)
    for printer_pk, articles_groupe in par_imprimante.items():
        printer = Printer.objects.get(pk=printer_pk)
        ticket_data = formatter_ticket_commande(commande, articles_groupe, printer)
        imprimer(printer, ticket_data)
```

## TÂCHE 6 — Remplacer le stub dans views.py

Lis `laboutik/views.py`. Cherche `imprimer_billet` (le stub logger).
Remplace par `imprimer_async.delay(printer.pk, ticket_data)`.

Enregistre les backends dans `laboutik/printing/__init__.py` :
```python
BACKENDS = {'SC': SunmiCloudBackend, 'SI': SunmiInnerBackend}
```

## TÂCHE 7 — Tests

Crée `tests/pytest/test_printing.py` :

- `test_sunmi_cloud_can_print_sans_serial` : can_print retourne False
- `test_sunmi_cloud_can_print_ok` : can_print retourne True (mock config)
- `test_sunmi_inner_send_commands` : vérifie que le group_send est appelé (mock channel_layer)
- `test_formatter_ticket_vente` : vérifie la structure du dict retourné
- `test_imprimer_commande_split` : 2 articles, 2 imprimantes → 2 appels imprimer
- `test_celery_retry_on_failure` : mock le backend pour lever une exception → vérifie retry

## VÉRIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_printing.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright && npx playwright test tests/laboutik/ --reporter=list
```

### Critère de succès

- [ ] SunmiCloudBackend et SunmiInnerBackend implémentés
- [ ] PrinterConsumer WebSocket fonctionnel sur `ws/printer/{uuid}/`
- [ ] 4 formatters créés
- [ ] `imprimer_async()` et `imprimer_commande()` Celery tasks avec retry
- [ ] Le stub `imprimer_billet()` est remplacé par `imprimer_async.delay()`
- [ ] 6+ tests pytest verts
- [ ] Tous les tests existants passent
