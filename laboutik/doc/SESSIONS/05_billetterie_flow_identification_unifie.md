# Session 05 — Flow d'identification unifié (1 panier = 1 client)

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

### Le problème actuel

Dans `laboutik/templates/laboutik/partial/hx_display_type_payment.html`, le code
utilise un `elif` mutuellement exclusif :

```
if consigne → flow consigne
elif panier_a_recharges → flow recharge (scan NFC client)
elif panier_a_adhesions → flow adhésion (wizard identification)
else → flow normal
```

Un panier avec `Recharge 10€ + Adhésion annuelle` ne fonctionne pas. C'est soit l'un, soit l'autre.

### La solution : 1 panier = 1 client

Quand le panier contient des articles qui nécessitent un client (recharge, adhésion,
ou billet dans une session future), le système demande UNE SEULE identification.
Ce client est utilisé pour tout : recharge → sa carte, adhésion → son user.

## TÂCHE 1 — Lire le code existant

1. Lis `laboutik/views.py`, fonction `moyens_paiement()` (~ligne 1600-1690).
   Note les flags `panier_a_recharges` et `panier_a_adhesions` et comment ils sont
   passés au template.

2. Lis `laboutik/templates/laboutik/partial/hx_display_type_payment.html` en entier.
   Note le `elif` et les 3 branches (consigne, recharge, adhesion, normal).

3. Lis les templates d'identification adhésion existants :
   - `laboutik/templates/laboutik/partial/hx_adhesion_choose_id.html`
   - `laboutik/templates/laboutik/partial/hx_read_nfc_adhesion.html`
   - `laboutik/templates/laboutik/partial/hx_adhesion_form.html`
   - `laboutik/templates/laboutik/partial/hx_adhesion_confirm.html`

4. Lis les actions ViewSet adhésion dans views.py :
   - `adhesion_choisir_identification()`, `lire_nfc_adhesion()`,
   - `adhesion_formulaire()`, `identifier_membre()`

## TÂCHE 2 — Nouveau flag unifié dans views.py

Dans `moyens_paiement()`, remplace les flags séparés par un flag unifié :

```python
panier_necessite_client = (
    _panier_contient_recharges(articles_panier)
    or panier_a_adhesions
)
```

Garde aussi les sous-flags individuels (`panier_a_recharges`, `panier_a_adhesions`)
pour que le template puisse adapter le texte explicatif.

Passe `panier_necessite_client` dans le contexte template.

## TÂCHE 3 — Nouveau template `hx_identifier_client.html`

Crée `laboutik/templates/laboutik/partial/hx_identifier_client.html`.

Ce template remplace les branches séparées. Il affiche :

1. Un titre "Identifier le client"
2. Un texte explicatif adaptatif :
   - Si `panier_a_recharges` : "Recharge → carte NFC requise"
   - Si `panier_a_adhesions` : "Adhésion → identification requise"
   - Si les deux : les deux lignes
3. Bouton "SCANNER CARTE NFC" (toujours présent)
4. Bouton "SAISIR EMAIL/NOM" (masqué si `panier_a_recharges` car carte physique requise)
5. Bouton RETOUR

Les boutons font des `hx-get` vers les actions existantes :
- Scanner → `lire_nfc_adhesion` (réutilisé, malgré le nom — on renommera plus tard)
- Email → `adhesion_formulaire` (idem)

`data-testid` : `identifier-client`, `identifier-btn-nfc`, `identifier-btn-email`

## TÂCHE 4 — Nouveau template `hx_recapitulatif_client.html`

Crée `laboutik/templates/laboutik/partial/hx_recapitulatif_client.html`.

Affiché après identification. Montre :

1. Nom/email du client identifié
2. Solde wallet (si carte NFC scannée)
3. Récap des articles avec ce qui sera fait :
   - Article VT : juste nom + prix
   - Article RE : "Recharge 10€ → carte de {client}"
   - Article AD : "Adhésion annuelle → rattachée à {client}"
4. Total
5. Boutons moyens de paiement (espèces, CB, chèque — PAS NFC si recharges)
6. Bouton RETOUR

Ce template est rendu par une action ViewSet `recapitulatif_client(POST)` qui
reçoit les données d'identification (tag_id et/ou email/nom) et reconstruit
le panier avec le contexte client.

## TÂCHE 5 — Modifier `hx_display_type_payment.html`

Remplace le `elif` par :

```html
{% if deposit_is_present %}
  {# flow consigne (inchangé) #}
{% elif panier_necessite_client %}
  {% include "laboutik/partial/hx_identifier_client.html" %}
{% else %}
  {# flow normal — boutons paiement standards (inchangé) #}
{% endif %}
```

Les branches `panier_a_recharges` et `panier_a_adhesions` disparaissent.

## TÂCHE 6 — Adapter `identifier_membre()` pour gérer les recharges

L'action `identifier_membre()` dans PaiementViewSet gère déjà l'identification
par NFC ou email pour les adhésions. Élargir pour aussi stocker le `tag_id`
nécessaire aux recharges.

Si le panier a des recharges ET que le client est identifié par NFC :
- Le `tag_id` est stocké dans le formulaire (champ caché)
- Il sera utilisé par `_payer_par_carte_ou_cheque()` pour créditer le wallet

## TÂCHE 7 — Écrire les tests

### Tests unitaires : `tests/pytest/test_identification_unifiee.py`

```python
def test_panier_necessite_client_vente_seule():
    """Panier avec seulement des articles VT → pas d'identification."""

def test_panier_necessite_client_recharge():
    """Panier avec recharge → identification requise."""

def test_panier_necessite_client_adhesion():
    """Panier avec adhésion → identification requise."""

def test_panier_necessite_client_mixte():
    """Panier recharge + adhésion → identification requise (1 seule fois)."""

def test_panier_recharge_bloque_email():
    """Panier avec recharge → le bouton email est masqué (carte physique requise)."""
```

### Tests E2E : adapter `44-laboutik-adhesion-identification.spec.ts`

Les chemins 1-5 de l'adhésion doivent toujours fonctionner, mais le template
d'entrée est maintenant `hx_identifier_client.html` (pas `hx_adhesion_choose_id.html`).
Adapter les sélecteurs `data-testid` si nécessaire.

Ajouter un test pour un panier mixte (recharge + adhésion) :
- Ajouter Recharge 10€ + Adhésion au panier
- VALIDER → écran identification client
- Scanner NFC → confirmation avec "Recharge → carte" + "Adhésion → rattachée"
- Payer en espèces → succès

## VÉRIFICATION

### Tests unitaires

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_identification_unifiee.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Tests E2E

```bash
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright

# Adhésion (le plus impacté)
npx playwright test tests/laboutik/44-laboutik-adhesion-identification.spec.ts

# Paiement standard (ne doit pas régresser)
npx playwright test tests/laboutik/39-laboutik-pos-paiement.spec.ts

# Tous les tests
npx playwright test tests/laboutik/ --reporter=list
```

### Critère de succès

- [ ] `hx_identifier_client.html` créé et fonctionnel
- [ ] `hx_recapitulatif_client.html` créé et fonctionnel
- [ ] Le `elif` mutuellement exclusif est supprimé de `hx_display_type_payment.html`
- [ ] Panier VT seul → pas d'identification
- [ ] Panier RE seul → identification NFC obligatoire (pas d'email)
- [ ] Panier AD seul → identification NFC ou email
- [ ] Panier RE + AD → identification NFC (1 seul scan, sert pour les 2)
- [ ] TOUS les tests pytest passent
- [ ] TOUS les tests Playwright passent
