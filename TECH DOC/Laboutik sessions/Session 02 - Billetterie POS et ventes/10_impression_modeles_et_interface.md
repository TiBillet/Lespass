# Session 10 — Impression : modèles + interface + bibliothèque ESC/POS

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le module d'impression utilise le pattern Strategy : une interface `PrinterBackend`,
des backends concrets (Sunmi Cloud, Sunmi Inner), et Celery pour l'async.

Le code legacy de référence est dans `OLD_REPOS/LaBoutik/epsonprinter/sunmi_cloud_printer.py`
(bibliothèque ESC/POS Sunmi Cloud, 750+ lignes). On le copie et on le nettoie.

## TÂCHE 1 — Modèle `Printer`

Lis `laboutik/models.py`. Ajoute le modèle `Printer` :

- `uuid` PK
- `name` CharField(100)
- `printer_type` CharField(2) — choices : SC (Sunmi Cloud), SI (Sunmi Inner)
- `paper_width` CharField(2) — choices : 80 (80mm, 384 dots), 57 (57mm, 240 dots)
- `sunmi_serial_number` CharField(100, nullable) — pour Sunmi Cloud
- `active` BooleanField(default=True)

Ajoute aussi les FK inversées :
- `PointDeVente.printer` FK nullable vers Printer (ticket de vente)
- `BaseBillet.CategorieProduct.printer` FK nullable vers `laboutik.Printer` (ticket de commande)

Et les champs config Sunmi dans `LaboutikConfiguration` :
- `sunmi_app_id` CharField(200, nullable)
- `sunmi_app_key` CharField(200, nullable)
- Méthodes `get_sunmi_app_id()` / `set_sunmi_app_id()` avec chiffrement Fernet
  (utiliser `fernet_encrypt` / `fernet_decrypt` de `fedow_connect.utils`)

Migration : `laboutik/migrations/0004_printer.py` + migration BaseBillet pour la FK.

## TÂCHE 2 — Interface `PrinterBackend`

Crée `laboutik/printing/__init__.py` et `laboutik/printing/base.py` :

```python
# base.py
class PrinterBackend:
    def can_print(self, printer):
        raise NotImplementedError
    def print_ticket(self, printer, ticket_data):
        raise NotImplementedError
    def print_test(self, printer):
        raise NotImplementedError

# __init__.py
BACKENDS = {}  # sera rempli en Session 11
def imprimer(printer, ticket_data):
    backend = BACKENDS[printer.printer_type]()
    ok, error = backend.can_print(printer)
    if not ok:
        return {"ok": False, "error": error}
    return backend.print_ticket(printer, ticket_data)
```

## TÂCHE 3 — Copier et nettoyer sunmi_cloud_printer.py

Lis `OLD_REPOS/LaBoutik/epsonprinter/sunmi_cloud_printer.py`.
Copie-le dans `laboutik/printing/sunmi_cloud_printer.py`.

Nettoie :
- Supprimer les imports `numpy` et `PIL` (pas d'impression d'images)
- Supprimer les méthodes liées aux images (appendImage, etc.)
- Garder : signature HMAC, ESC/POS texte, QR code, barcode, coupe papier, pushContent
- Adapter les docstrings en FALC bilingue

## TÂCHE 4 — Admin Unfold

Lis `Administration/admin/laboutik.py`. Ajoute `PrinterAdmin` dans la sidebar "Caisse".

## VÉRIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_pos_models.py -v
```

Vérification manuelle : créer un Printer dans l'admin Unfold → sauvegarder OK.

### Critère de succès

- [ ] Modèle Printer créé avec migration appliquée
- [ ] FK printer sur PointDeVente et CategorieProduct
- [ ] Champs sunmi_app_id/key sur LaboutikConfiguration (Fernet)
- [ ] `printing/base.py` et `printing/__init__.py` créés
- [ ] `sunmi_cloud_printer.py` copié et nettoyé (pas de numpy/PIL)
- [ ] PrinterAdmin visible dans l'admin Unfold
- [ ] Tous les tests existants passent
