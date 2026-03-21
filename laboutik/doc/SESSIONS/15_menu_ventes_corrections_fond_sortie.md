# Session 15 — Menu Ventes : corrections + fond de caisse + sortie

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le menu Ventes affiche le Ticket X et la liste des ventes (Session 14).
Il faut maintenant ajouter : correction de moyen de paiement, ré-impression ticket,
fond de caisse, et sortie de caisse avec ventilation par coupure.

## TÂCHE 1 — Modèles

Dans `laboutik/models.py`, crée :

### `CorrectionPaiement` (trace d'audit)

- `uuid` PK
- `ligne_article` FK → LigneArticle (PROTECT)
- `ancien_moyen` CharField(10)
- `nouveau_moyen` CharField(10)
- `raison` TextField (obligatoire — pas blank, pas default)
- `operateur` FK → TibilletUser (SET_NULL, nullable)
- `datetime` DateTimeField(auto_now_add)

### `SortieCaisse` (retrait espèces)

- `uuid` PK
- `point_de_vente` FK → PointDeVente (PROTECT)
- `operateur` FK → TibilletUser (SET_NULL, nullable)
- `datetime` DateTimeField(auto_now_add)
- `montant_total` IntegerField (centimes)
- `ventilation` JSONField
  Format : `{"5000": 0, "2000": 5, "1000": 2, "500": 0, "200": 3, "100": 2, "50": 4, "20": 0, "10": 0, "5": 0, "2": 0, "1": 0}`
  (clé = valeur de la coupure en centimes, valeur = quantité)
- `note` TextField(blank=True, default='')

Migration.

## TÂCHE 2 — Correction moyen de paiement

### Contrainte métier

**UNIQUEMENT espèces ↔ CB ↔ chèque.** Pas de modification du NFC (lié à une
Transaction fedow_core avec débit/crédit wallet — modifier le moyen créerait
une incohérence comptable). Pas de modification des ventes en ligne.

### Action ViewSet

Dans `PaiementViewSet`, ajoute :

```python
@action(detail=False, methods=['POST'], url_path='corriger_moyen_paiement')
def corriger_moyen_paiement(self, request):
    """Corrige le moyen de paiement d'une vente passée."""
    ligne_uuid = request.POST.get('ligne_uuid')
    nouveau_moyen = request.POST.get('nouveau_moyen')
    raison = request.POST.get('raison')

    ligne = LigneArticle.objects.get(uuid=ligne_uuid)

    # GARDE : NFC interdit
    if ligne.payment_method in ('NFC', PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT):
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("Les paiements cashless ne peuvent pas être modifiés"),
        }, status=400)

    # GARDE : raison obligatoire
    if not raison or not raison.strip():
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("La raison de la correction est obligatoire"),
        }, status=400)

    # Créer la trace d'audit
    CorrectionPaiement.objects.create(
        ligne_article=ligne,
        ancien_moyen=ligne.payment_method,
        nouveau_moyen=nouveau_moyen,
        raison=raison.strip(),
        operateur=request.user if request.user.is_authenticated else None,
    )

    # Modifier la LigneArticle
    ligne.payment_method = nouveau_moyen
    ligne.save(update_fields=['payment_method'])

    return render(request, "laboutik/partial/hx_detail_vente.html", {...})
```

### Template

`hx_corriger_moyen.html` : 3 boutons (ESPÈCE, CB, CHÈQUE) + champ raison obligatoire.
`data-testid` : `correction-btn-espece`, `correction-btn-cb`, `correction-btn-cheque`,
`correction-input-raison`, `correction-btn-confirmer`.

## TÂCHE 3 — Ré-impression ticket

Dans `CaisseViewSet`, ajoute :

```python
@action(detail=False, methods=['POST'], url_path='reimprimer_ticket')
def reimprimer_ticket(self, request):
    """Reconstruit le ticket et l'envoie à l'imprimante."""
    ligne_uuid = request.POST.get('ligne_uuid')
    ligne = LigneArticle.objects.get(uuid=ligne_uuid)
    # Reconstruire ticket_data depuis la LigneArticle
    ticket_data = formatter_ticket_vente([ligne], ...)
    printer = ligne.pricesold.productsold.product.categorie_pos.printer
    if printer:
        imprimer_async.delay(str(printer.pk), ticket_data)
    return render(request, "laboutik/partial/hx_messages.html", {
        "msg_type": "success", "msg_content": _("Ticket envoyé à l'imprimante"),
    })
```

## TÂCHE 4 — Fond de caisse

Dans `CaisseViewSet`, ajoute :

```python
@action(detail=False, methods=['GET', 'POST'], url_path='fond_de_caisse')
def fond_de_caisse(self, request):
    """GET: affiche le montant actuel. POST: met à jour."""
    config = LaboutikConfiguration.get_solo()
    if request.method == 'POST':
        montant = int(round(float(request.POST.get('montant', 0)) * 100))
        config.fond_de_caisse = montant
        config.save(update_fields=['fond_de_caisse'])
    return render(request, "laboutik/partial/hx_fond_de_caisse.html", {
        "fond_de_caisse_euros": config.fond_de_caisse / 100,
    })
```

Template `hx_fond_de_caisse.html` : input `inputmode="decimal"`, bouton ENREGISTRER.

## TÂCHE 5 — Sortie de caisse

Dans `CaisseViewSet`, ajoute :

```python
@action(detail=False, methods=['GET', 'POST'], url_path='sortie_de_caisse')
def sortie_de_caisse(self, request):
    """GET: formulaire ventilation. POST: enregistre la sortie."""
```

Template `hx_sortie_de_caisse.html` :
- Tableau avec 12 lignes (50€, 20€, 10€, 5€, 2€, 1€, 0.50€, 0.20€, 0.10€, 0.05€, 0.02€, 0.01€)
- Chaque ligne : coupure | input quantité (type number, min 0) | sous-total calculé
- Total auto-calculé (JS minimal : somme des sous-totaux)
- Champ note (textarea, optionnel)
- Boutons : ANNULER, IMPRIMER JUSTIFICATIF, ENREGISTRER

Le POST crée un `SortieCaisse` avec la ventilation JSON.
Le total est recalculé côté serveur (ne pas faire confiance au JS).

## TÂCHE 6 — Tests

### pytest : `tests/pytest/test_menu_ventes_actions.py`

```python
def test_correction_moyen_espece_vers_cb(tenant):
    """Correction espèce → CB : LigneArticle modifiée + CorrectionPaiement créée."""

def test_correction_nfc_refuse(tenant):
    """Correction NFC → retourne 400."""

def test_correction_raison_obligatoire(tenant):
    """Correction sans raison → retourne 400."""

def test_fond_de_caisse_get(tenant):
    """GET retourne le montant actuel."""

def test_fond_de_caisse_post(tenant):
    """POST met à jour le montant."""

def test_sortie_de_caisse_creation(tenant):
    """POST crée SortieCaisse avec bonne ventilation et bon total."""

def test_sortie_de_caisse_total_recalcule(tenant):
    """Le total est recalculé côté serveur, pas confiance au JS."""
```

### Playwright

Étendre les tests laboutik ou créer un nouveau spec :
- Corriger un paiement espèces → CB → vérifier le changement
- Tenter de corriger un paiement NFC → message d'erreur
- Saisir un fond de caisse → vérifier la persistance
- Faire une sortie de caisse → vérifier le justificatif

## VÉRIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes_actions.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Critère de succès

- [ ] Modèles CorrectionPaiement et SortieCaisse créés avec migration
- [ ] Correction ESP↔CB↔CHQ fonctionne avec audit trail
- [ ] Correction NFC refusée (400)
- [ ] Raison obligatoire pour toute correction
- [ ] Fond de caisse GET/POST fonctionne
- [ ] Sortie de caisse avec ventilation par coupure
- [ ] Total sortie recalculé côté serveur
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent
