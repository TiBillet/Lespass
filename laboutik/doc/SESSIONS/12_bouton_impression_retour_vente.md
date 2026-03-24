# Session 12 — Bouton impression sur retour de vente + auto-print billetterie

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un bouton "Imprimer" sur l'ecran de succes apres chaque vente, et une impression automatique pour les billets (avec QR code agrandi).

**Architecture:** Champ `uuid_transaction` sur `LigneArticle` pour regrouper les lignes d'un meme paiement. Endpoint HTMX `imprimer_ticket_vente` pour le bouton. Impression auto des billets via `imprimer_billet()` existant (Celery). Formatter billet avec QR code signe (meme data que le PDF).

**Tech Stack:** Django, HTMX (hx-post), Celery (imprimer_async), segno (QR code), ESC/POS

---

## Contexte

L'ecran `hx_return_payment_success.html` a un `TODO: imprimer ticket` (ligne 67).
Le module `laboutik/printing/` est operationnel (4 backends : Cloud, LAN, Inner, Mock).
Le formatter `formatter_ticket_vente()` existe deja.
`imprimer_billet()` dans `views.py` lance deja l'impression async via Celery.

Ce qu'on ajoute :
1. `uuid_transaction` sur `LigneArticle` — regroupe les lignes d'un meme paiement
2. Bouton "Imprimer le ticket" sur l'ecran de succes (HTMX POST)
3. Impression auto des billets pour PV BILLETTERIE (QR code agrandi)
4. Endpoint `/laboutik/paiement/imprimer_ticket/` pour le bouton (et future re-impression)

## Fichiers concernes

| Action | Fichier | Responsabilite |
|--------|---------|----------------|
| MODIFIER | `BaseBillet/models.py` | Ajouter `uuid_transaction` sur LigneArticle |
| MODIFIER | `laboutik/views.py` | Generer uuid_transaction, passer au template, endpoint imprimer, auto-print billets |
| MODIFIER | `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Bouton "Imprimer" HTMX |
| MODIFIER | `laboutik/printing/formatters.py` | Ameliorer formatter_ticket_billet (QR code signe) |
| MODIFIER | `laboutik/printing/escpos_builder.py` | QR code agrandi pour billets |
| MODIFIER | `laboutik/urls.py` | Route endpoint imprimer_ticket |
| CREER | `laboutik/templates/laboutik/partial/hx_print_confirmation.html` | Feedback "Impression lancee" |
| CREER | `BaseBillet/migrations/0207_lignearticle_uuid_transaction.py` | Migration auto |
| CREER | `tests/pytest/test_print_button.py` | Tests |

---

## TACHE 1 — Champ `uuid_transaction` sur LigneArticle

**Fichiers :**
- Modifier : `BaseBillet/models.py` (LigneArticle, ~ligne 2887)
- Creer : `BaseBillet/migrations/0207_*.py` (auto)

Ajouter sur `LigneArticle` :

```python
# Identifiant de transaction — regroupe les lignes d'un meme paiement.
# Toutes les LigneArticle creees dans un meme paiement partagent ce UUID.
# Permet de reconstruire un ticket pour re-impression.
# / Transaction ID — groups lines from the same payment.
# All LigneArticle created in one payment share this UUID.
# Allows reconstructing a ticket for reprinting.
uuid_transaction = models.UUIDField(
    blank=True, null=True, db_index=True,
    verbose_name=_("Transaction ID"),
    help_text=_("Groups all lines from the same payment for reprinting."),
)
```

Nullable pour ne pas casser les lignes existantes.
Indexe pour la recherche rapide (re-impression).

**Verification :**
```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
```

## TACHE 2 — Generer `uuid_transaction` au paiement

**Fichier :** `laboutik/views.py`

Dans `_payer_par_carte_ou_cheque()`, `_payer_en_especes()`, et `_payer_par_nfc()` :

1. Generer un `uuid_transaction` AVANT le bloc `transaction.atomic()` :
```python
import uuid as uuid_module
uuid_transaction = uuid_module.uuid4()
```

2. Passer `uuid_transaction` a `_creer_lignes_articles()` qui le propage sur chaque `LigneArticle`.

3. Ajouter `uuid_transaction` au context du template de succes :
```python
context = {
    ...
    "uuid_transaction": str(uuid_transaction),
    "uuid_pv": str(point_de_vente.uuid),
    "pv_est_billetterie": point_de_vente.comportement == PointDeVente.BILLETTERIE,
}
```

4. Modifier `_creer_lignes_articles()` pour accepter et stocker `uuid_transaction` :
```python
def _creer_lignes_articles(articles_panier, moyen_paiement_code, uuid_transaction=None):
    ...
    for article in articles_panier:
        ligne = LigneArticle(
            ...
            uuid_transaction=uuid_transaction,
        )
        ...
```

## TACHE 3 — Impression auto pour billets (PV BILLETTERIE)

**Fichier :** `laboutik/views.py`

Apres le bloc `transaction.atomic()`, APRES l'envoi des emails, si le PV est de type BILLETTERIE et a une imprimante :

```python
# Impression automatique des billets pour la billetterie
# / Auto-print tickets for ticketing POS
if (reservations_billets
    and point_de_vente.comportement == PointDeVente.BILLETTERIE
    and point_de_vente.printer
    and point_de_vente.printer.active):

    for reservation in reservations_billets:
        tickets_de_cette_reservation = Ticket.objects.filter(
            reservation=reservation
        ).select_related('pricesold', 'reservation__event')

        for ticket in tickets_de_cette_reservation:
            imprimer_billet(ticket, reservation, reservation.event, point_de_vente)
```

**Modifier `formatter_ticket_billet()`** dans `laboutik/printing/formatters.py` pour utiliser le vrai QR code signe (meme data que le PDF) :

```python
def formatter_ticket_billet(ticket, reservation, event):
    ...
    # QR code : meme contenu que le PDF (UUID signe avec la cle RSA de l'event)
    # / QR code: same content as PDF (UUID signed with event's RSA key)
    qrcode_data = None
    try:
        qrcode_data = ticket.qrcode()  # Retourne "base64_uuid:signature"
    except Exception:
        # Fallback : UUID brut si la cle RSA n'est pas configuree
        # / Fallback: raw UUID if RSA key is not configured
        qrcode_data = str(ticket.uuid)

    return {
        ...
        "qrcode": qrcode_data,
        ...
    }
```

**Modifier `escpos_builder.py`** pour agrandir le QR code quand il y en a un (module_size 8 au lieu de 5 — plus lisible sur ticket thermique) :

```python
# QR code agrandi pour les billets (plus facile a scanner)
# / Enlarged QR code for tickets (easier to scan)
if qrcode_text:
    builder.lineFeed(1)
    builder.setAlignment(ALIGN_CENTER)
    builder.appendQRcode(module_size=8, ec_level=2, text=qrcode_text)
    builder.lineFeed(1)
```

## TACHE 4 — Bouton "Imprimer" sur l'ecran de succes

**Fichier :** `laboutik/templates/laboutik/partial/hx_return_payment_success.html`

Remplacer le `TODO` (ligne 67) par :

```html
<!-- Bouton imprimer le ticket de vente / Print receipt button -->
{% if uuid_transaction and uuid_pv %}
<div class="bt-basic-container" style="background-color: #2563EB; margin-top: 1rem;"
     data-testid="btn-imprimer-ticket"
     hx-post="{% url 'laboutik-paiement-imprimer_ticket' %}"
     hx-vals='{"uuid_transaction": "{{ uuid_transaction }}", "uuid_pv": "{{ uuid_pv }}"}'
     hx-target="#print-feedback"
     hx-swap="innerHTML">
  <div class="bt-basic-icon">
    <i class="fas fa-print" aria-hidden="true"></i>
  </div>
  <div class="bt-basic-text">
    <div>{% translate "Imprimer" %}</div>
  </div>
</div>
<div id="print-feedback" aria-live="polite"></div>
{% endif %}
```

**Creer** `laboutik/templates/laboutik/partial/hx_print_confirmation.html` :

```html
{% load i18n %}
<!--
CONFIRMATION D'IMPRESSION
Petit message de feedback apres clic sur "Imprimer".
/ Print confirmation feedback after clicking "Print".

LOCALISATION : laboutik/templates/laboutik/partial/hx_print_confirmation.html
-->
<div class="payment-msg-discret" style="color: #16A34A; margin-top: 0.5rem;"
     data-testid="print-confirmation">
  <i class="fas fa-check" aria-hidden="true"></i>
  {% translate "Impression lancée" %}
</div>
```

## TACHE 5 — Endpoint `imprimer_ticket`

**Fichier :** `laboutik/views.py` (dans `PaiementViewSet`)

Ajouter une action :

```python
@action(detail=False, methods=["post"], url_path="imprimer_ticket", url_name="imprimer_ticket")
def imprimer_ticket(self, request):
    """
    POST /laboutik/paiement/imprimer_ticket/
    Imprime (ou re-imprime) un ticket de vente a partir du uuid_transaction.
    / Prints (or reprints) a sale ticket from the uuid_transaction.

    LOCALISATION : laboutik/views.py
    """
    uuid_transaction = request.POST.get("uuid_transaction")
    uuid_pv = request.POST.get("uuid_pv")

    if not uuid_transaction or not uuid_pv:
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("Donnees manquantes pour l'impression"),
            "selector_bt_retour": "#print-feedback",
        })

    # Recuperer le PV et son imprimante
    # / Get the POS and its printer
    try:
        point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)
    except PointDeVente.DoesNotExist:
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("Point de vente introuvable"),
            "selector_bt_retour": "#print-feedback",
        })

    if not point_de_vente.printer or not point_de_vente.printer.active:
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("Aucune imprimante configuree pour ce point de vente"),
            "selector_bt_retour": "#print-feedback",
        })

    # Recuperer les lignes de cette transaction
    # / Get the lines for this transaction
    lignes_du_paiement = LigneArticle.objects.filter(
        uuid_transaction=uuid_transaction
    ).select_related('pricesold__productsold')

    if not lignes_du_paiement.exists():
        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "warning",
            "msg_content": _("Aucune ligne trouvee pour cette transaction"),
            "selector_bt_retour": "#print-feedback",
        })

    # Construire le ticket et lancer l'impression async
    # / Build the ticket and launch async printing
    from laboutik.printing.formatters import formatter_ticket_vente
    from laboutik.printing.tasks import imprimer_async

    # Operateur = user connecte (admin session)
    # / Operator = logged-in user (admin session)
    operateur = request.user if request.user.is_authenticated else None

    # Moyen de paiement = celui de la premiere ligne
    # / Payment method = from the first line
    premiere_ligne = lignes_du_paiement.first()
    moyen_paiement = premiere_ligne.payment_method if premiere_ligne else ""

    ticket_data = formatter_ticket_vente(
        lignes_du_paiement, point_de_vente, operateur, moyen_paiement
    )

    imprimer_async.delay(
        str(point_de_vente.printer.pk),
        ticket_data,
        connection.schema_name,
    )

    return render(request, "laboutik/partial/hx_print_confirmation.html")
```

**Fichier :** `laboutik/urls.py` — Verifier que la route est auto-generee par le router DRF (action sur PaiementViewSet). Pas besoin de toucher urls.py.

## TACHE 6 — Tests

**Fichier :** `tests/pytest/test_print_button.py`

Tests a ecrire :

1. `test_uuid_transaction_sur_lignearticle` — creer une LigneArticle avec uuid_transaction, verifier qu'on la retrouve par filtre
2. `test_formatter_ticket_billet_qrcode_signe` — verifier que le QR contient la signature (mock ticket.qrcode())
3. `test_endpoint_imprimer_ticket_sans_imprimante` — POST sans imprimante → message warning
4. `test_endpoint_imprimer_ticket_ok` — POST avec mock printer → impression lancee

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_print_button.py tests/pytest/test_printing.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

## CE QU'ON NE FAIT PAS

- Pas de page "historique des impressions" (futur)
- Pas de re-impression depuis l'admin (futur — Menu Ventes, session 13+)
- Pas de modification du JS existant
- Pas de formatter pour les recharges cashless (pas de ticket papier pour les recharges)
