# PIEGES.md — Pièges techniques Lespass

Catalogue des pièges découverts en session de développement et de test.
Format : symptôme → cause → workaround → contexte de découverte.

---

## stdimage `post_delete` crash sur `Event` sans image

**Symptôme** : `event.delete()` dans un test crashe avec
`TypeError: expected str, bytes or os.PathLike object, not NoneType`
dans `os.path.splitext(None)` (provenant de `stdimage/models.py`).

**Cause** : stdimage enregistre un signal `post_delete` sur les
modèles avec `StdImageField`. Si l'instance n'a pas d'image set
(champ `img` à None), le callback essaie de supprimer un fichier
inexistant et crashe sur le `splitext(None)`.

**Reproduction** :

```python
from BaseBillet.models import Event
event = Event.objects.create(name="Test", datetime=timezone.now())
event.delete()  # crash : os.path.splitext(None)
```

**Workaround pour tests** : retirer temporairement les receivers
`post_delete` matching `id(Event)` du signal avant le `.delete()`,
puis les restaurer ensuite.

```python
from django.db.models.signals import post_delete

receivers_to_restore = []
for sender_key, receiver_dict in list(post_delete.receivers):
    if sender_key[1] == id(Event):
        receivers_to_restore.append((sender_key, receiver_dict))
        post_delete.receivers.remove((sender_key, receiver_dict))
try:
    event.delete()
finally:
    post_delete.receivers.extend(receivers_to_restore)
```

**Découvert** : session COMPTABILITE S2 (2026-05-15) lors des tests
du service `RapportComptableService` qui crée des `Event` éphémères.

---

## Pytest `API_KEY` injection : `docker exec` non disponible dans le container

**Symptôme** : Tous les tests pytest échouent avec :
```
FileNotFoundError: [Errno 2] No such file or directory: 'docker'
```

**Cause** : `tests/pytest/conftest.py` a une fixture autouse
`_inject_cli_env` qui tente d'appeler `docker exec` (depuis
l'intérieur du container) pour récupérer l'API key. Or `docker`
n'est pas installé dans le container `lespass_django`.

**Workaround** : passer `API_KEY` explicitement via `-e` à
`docker exec` depuis l'hôte.

```bash
API_KEY=$(docker exec lespass_django poetry run python /DjangoFiles/manage.py test_api_key 2>/dev/null | tail -1) && \
docker exec -e "API_KEY=$API_KEY" lespass_django bash -c \
    "cd /DjangoFiles && /home/tibillet/.cache/pypoetry/virtualenvs/lespass-LcPHtxiF-py3.11/bin/pytest tests/pytest/ -v"
```

La fixture détecte alors `os.getenv("API_KEY")` et n'appelle plus
`docker exec`. Le test se déroule normalement.

**Découvert** : sessions COMPTABILITE S1-S5 (2026-05-15) lors des
runs de tests TDD.
