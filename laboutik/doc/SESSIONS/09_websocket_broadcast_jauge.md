# Session 09 — WebSocket broadcast jauge billetterie

## CONTEXTE

Tu travailles sur `laboutik/` et `wsocket/`.
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le WebSocket fonctionne (Session 08). Le badge "Connecté" apparaît au chargement.
Il faut maintenant broadcaster la jauge billetterie après chaque vente de billet.

## TÂCHE 1 — Broadcast après vente de billet

Lis `laboutik/views.py`, fonction `_creer_billets_depuis_panier()` (Session 07).

**APRÈS** le bloc `db_transaction.atomic()` (JAMAIS dedans — si rollback, le client
recevrait un état incohérent), ajoute :

```python
from wsocket.broadcast import broadcast_html

# Recalculer les données jauge pour chaque event modifié
for event in events_modifies:
    places_vendues = event.valid_tickets_count()
    event_data = {
        'uuid': str(event.uuid),
        'jauge_max': event.jauge_max,
        'places_vendues': places_vendues,
        'places_restantes': max(0, event.jauge_max - places_vendues) if event.jauge_max else None,
        'pourcentage': int(round(places_vendues / event.jauge_max * 100)) if event.jauge_max else 0,
        'complet': event.complet(),
    }
    broadcast_html(
        group_name=f"laboutik-pv-{pv_uuid}",
        template_name="laboutik/partial/hx_jauge_event.html",
        context={"event": event_data},
        message_type="jauge.update",  # → handler jauge_update() dans le consumer
    )
```

Note : il faut passer le `pv_uuid` à cette fonction. Adapter la signature si nécessaire.

## TÂCHE 2 — Adapter le partial jauge pour le swap OOB

Lis `laboutik/templates/laboutik/partial/hx_jauge_event.html` (Session 06).

Le partial doit avoir un `id` pour que HTMX puisse le swapper via WebSocket :

```html
<div id="billet-jauge-{{ event.uuid }}" hx-swap-oob="true" class="billet-tuile-jauge-wrapper">
  {# contenu jauge ... #}
</div>
```

L'`id` + `hx-swap-oob="true"` permet à HTMX de remplacer l'élément existant
dans le DOM quand le consumer envoie ce HTML via WebSocket.

Garder aussi le `hx-trigger="every 60s"` comme **fallback** (au cas où le WS se déconnecte).
Passer de 30s à 60s puisque le WS fait le push en temps réel.

## TÂCHE 3 — Handler dans le consumer

Vérifier que `LaboutikConsumer.jauge_update()` (Session 08) forward correctement
le HTML au client. Le handler doit être :

```python
async def jauge_update(self, event):
    await self.send(text_data=event["html"])
```

Le `message_type="jauge.update"` dans `broadcast_html()` est traduit par Channels
en appel de méthode `jauge_update()` (le point `.` devient `_`).

## VÉRIFICATION

### Test manuel avec 2 onglets

1. Ouvrir la caisse dans 2 onglets du navigateur (même PV)
2. Les 2 onglets montrent les tuiles billet avec jauge
3. Dans l'onglet 1 : ajouter un billet au panier → payer en espèces → succès
4. Dans l'onglet 2 : la jauge se met à jour en < 1 seconde (sans refresh)
5. Vérifier dans les logs Django : `[WS] Broadcast jauge...` ou message de `broadcast_html`

### Tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_billetterie_pos.py -v
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Critère de succès

- [ ] Après vente de billet, la jauge est broadcastée via WebSocket
- [ ] Le broadcast est APRÈS le atomic() (pas dedans)
- [ ] La jauge se met à jour en temps réel sur les autres onglets/caisses
- [ ] Le polling HTMX 60s reste comme fallback
- [ ] Tous les tests passent
