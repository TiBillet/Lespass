# Session 37 — Stock vrac négatif et alerte écran de validation

> Date : 2026-05-05
> Branche cible : V2
> Statut : Design validé, en attente d'implémentation
> Bug d'origine : retour Antoine 2026-05-04, item « Stock vrac hors stock pas de message d'erreur »

---

## 1. Contexte

Antoine a rapporté lors d'une journée de tests :

> *« Pour le vrac, vérification sur le stock manquant au moment où l'on input
> la quantité voulue, si on passe en hors stock la commande ne se fait juste
> pas, mais il n'y a jamais de message d'erreur. »*

Reproduction directe (2026-05-05) en saisissant 50 000 g sur un produit
« Cacahuètes en vrac » avec un stock de 200 g :

- **La vente se fait bien** (visible dans `/admin/BaseBillet/lignearticle/`)
- **Le stock n'est pas décrémenté** (la quantité reste à 200 g en DB)
- **Le caissier ne voit aucun message d'erreur** sur l'écran de succès
- **Erreur JS bonus** dans la console :
  `TypeError: can't access property "innerText", eleQuantity is null`
  à `tarif.js:409` (capturée par try/catch, non bloquante)

Effet : **vente fantôme** — comptablement validée, mais l'inventaire est faussé.

---

## 2. Diagnostic

### Cause racine côté back

Fichier : `laboutik/views.py` lignes 3614-3668 dans `_creer_lignes_articles()`

Le flow est :

1. Ligne 3598 — `LigneArticle.objects.create(...)` est appelé d'abord
2. Lignes 3622-3643 — `StockService.decrementer_pour_vente(...)` est appelé ensuite
3. Si stock insuffisant et `autoriser_vente_hors_stock=False`, le service lève
   `StockInsuffisant` (`inventaire/services.py:55`)
4. **Lignes 3665-3668** :
   ```python
   except Exception:
       # Pas de stock géré pour ce produit — comportement normal
       # / No stock managed for this product — normal behavior
       pass
   ```

L'intention du `pass` est de gérer le cas où le produit n'a pas de Stock lié
(`Stock.DoesNotExist`). Mais `except Exception` **avale aussi** `StockInsuffisant`.

**Conséquence :**
- La `LigneArticle` reste créée et chaînée HMAC (lignes 3686-3703)
- Le `MouvementStock` n'est jamais créé (la création est dans
  `decrementer_pour_vente` après le raise)
- La `Stock.quantite` n'est pas modifiée
- La fonction retourne sans erreur
- Le paiement continue, l'écran de succès s'affiche

Le flag `autoriser_vente_hors_stock` est complètement contourné par cet `except`.

### Cause racine côté front (cosmétique)

Fichier : `laboutik/static/js/tarif.js` lignes 240-303 (handler clic OK du pavé numérique)

Aucune comparaison entre quantité saisie et stock disponible. La seule garde
est `quantiteSaisie <= 0` (ligne 243). L'utilisateur peut saisir 50 000 g
même si le stock est à 200 g.

L'erreur JS `eleQuantity is null` à la ligne 409 vient du fait que le pavé
numérique vrac s'affiche en remplaçant `#products.innerHTML` (ligne 169 :
`articlesZone.innerHTML = ...`). Le badge `#article-quantity-number-{uuid}`
n'existe donc plus dans le DOM quand `addArticleWithPrice` essaie de l'incrémenter.

---

## 3. Décisions prises

Discussion 2026-05-05 :

1. **Les stocks négatifs sont autorisés** quand `autoriser_vente_hors_stock=True`.
   La vente passe, le stock va en négatif, une alerte informe le caissier.

2. **La vente est bloquée** quand `autoriser_vente_hors_stock=False`
   (le flag retrouve son vrai sens d'autorisation).

3. **Pas de rollback de transaction** — trop spaghetti et sur-ingénieuré.
   Le blocage se fait par **validation amont** : on vérifie le stock
   AVANT d'ouvrir le `transaction.atomic()`.

4. **Pas de toast** pour l'instant. L'audit a montré 4 patterns toast
   différents dans le projet et aucun n'est implémenté côté POS LaBoutik
   (pas de SweetAlert2 chargé, pas de listener `panierToast` dans la base).
   Un futur chantier d'unification sera lancé.

5. **L'info stock négatif est ajoutée à l'écran de validation de la vente**
   (`hx_return_payment_success.html`), dans une zone cohérente avec les
   éléments existants (`.give-back-box`, `.cascade-badges-list`).

---

## 4. Design — 4 modifications

### Modif 1 — `inventaire/services.py:decrementer_pour_vente` (~5 lignes modifiées)

**Avant :** deux branches selon `autoriser_vente_hors_stock`. Si vente
hors stock interdite et stock insuffisant, lève `StockInsuffisant`.

**Après :** décrémente toujours sans condition. Retourne `True` si le
stock vient de passer en négatif, `False` sinon. Plus de `raise`.

```python
@staticmethod
def decrementer_pour_vente(stock, contenance, qty, ligne_article=None) -> bool:
    """
    Decremente le stock apres une vente POS.
    Le caller a la responsabilite de bloquer en amont si vente hors stock interdite.
    / Decrements stock after a POS sale. Caller is responsible for blocking upstream.

    :return: True si le stock est passe negatif apres cette vente, False sinon.
    """
    contenance_effective = contenance or 1
    delta = qty * contenance_effective
    stock_avant = stock.quantite

    Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") - delta)

    MouvementStock.objects.create(
        stock=stock,
        type_mouvement=TypeMouvement.VE,
        quantite=-delta,
        quantite_avant=stock_avant,
        ligne_article=ligne_article,
        cree_par=None,
    )

    logger.info(...)  # inchangé

    return (stock_avant - delta) < 0
```

L'exception `StockInsuffisant` reste dans `inventaire/models.py` pour les
management commands, mais n'est plus levée par ce service.

### Modif 2 — `laboutik/views.py` — fonctions de validation amont (~30 lignes)

Deux fonctions ajoutées au-dessus de `_creer_lignes_articles` :

```python
def _valider_stock_panier(articles_panier):
    """
    Verifie que chaque article du panier a un stock suffisant
    si son Stock interdit la vente hors stock.
    Returns: liste de dicts {name, demande, disponible, unite}.
    Liste vide = panier OK.
    / Checks that each cart item has enough stock if Stock blocks out-of-stock sale.
    """
    erreurs = []
    for article in articles_panier:
        produit = article["product"]
        try:
            stock = produit.stock_inventaire
        except Stock.DoesNotExist:
            continue  # Pas de gestion de stock pour ce produit

        if stock.autoriser_vente_hors_stock:
            continue  # Vente hors stock autorisee, pas de blocage

        # Calcule la quantite demandee (poids/mesure ou contenance fixe)
        weight_amount = article.get("weight_amount")
        if weight_amount:
            demande = weight_amount  # ex: 50000g
        else:
            demande = article["quantite"] * (article["price"].contenance or 1)

        if demande > stock.quantite:
            erreurs.append({
                "name": produit.name,
                "demande": demande,
                "disponible": stock.quantite,
                "unite": stock.unite,
            })
    return erreurs


def _formater_erreurs_stock(erreurs):
    """
    Formate la liste d'erreurs en message lisible pour le partial hx_messages.html.
    / Formats error list into a readable message.
    """
    parts = []
    for e in erreurs:
        parts.append(
            f"{e['name']} : "
            f"{_('demande')} {e['demande']} {e['unite']}, "
            f"{_('reste')} {e['disponible']} {e['unite']}"
        )
    return _("Stock insuffisant — vente refusée.") + " " + " ; ".join(parts)
```

### Modif 3 — `laboutik/views.py:3614-3668` (~10 lignes)

Deux changements :

**a)** Remplacer `except Exception:` par `except Stock.DoesNotExist:`
(capture uniquement le cas attendu).

**b)** Récupérer le flag `stock_devenu_negatif` du service et accumuler
les produits concernés. La fonction `_creer_lignes_articles` doit aussi
remonter cette liste à l'appelant.

Signature avant :
```python
def _creer_lignes_articles(...) -> list[LigneArticle]:
```

Signature après :
```python
def _creer_lignes_articles(...) -> tuple[list[LigneArticle], list[dict]]:
    # Returns: (lignes_creees, produits_stock_negatif)
```

Idem pour `_creer_lignes_articles_cascade` (`laboutik/views.py:3728`).

### Modif 4 — 6 vues de paiement (~15 lignes par vue, helper extrait)

Les vues concernées : lignes 4956, 5115, 5586, 6457, 6807, 8181.

**a) Validation amont** — juste avant le `transaction.atomic()` :

```python
erreurs_stock = _valider_stock_panier(articles_panier)
if erreurs_stock:
    return render(
        request,
        "laboutik/partial/hx_messages.html",
        {
            "msg_type": "warning",
            "msg_content": _formater_erreurs_stock(erreurs_stock),
        },
        status=400,
    )
```

⚠ **Ce blocage dépend de la fix B du bug 1** (config globale
`htmx:beforeOnLoad` qui swappe sur 400). Sans elle, l'utilisateur ne
verra rien (htmx 2.0 ignore les 4xx par défaut).

**b) Propagation de `produits_stock_negatif`** — récupéré du retour
de `_creer_lignes_articles*` et passé au contexte du render :

```python
lignes_creees, produits_stock_negatif = _creer_lignes_articles(...)
# ...
context["produits_stock_negatif"] = produits_stock_negatif
return render(request, "laboutik/partial/hx_return_payment_success.html", context)
```

### Modif 5 — `hx_return_payment_success.html` — zone alerte stock négatif

À ajouter avant le bouton `<c-bt.return />` (ligne 95) :

```html
{% if produits_stock_negatif %}
<div class="give-back-box stock-alerte-box"
     data-testid="alerte-stock-negatif"
     role="alert"
     style="background-color: var(--warning00); margin-top: 0.75rem;">
  <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
  <strong>{% translate "Stock négatif" %} :</strong>
  <ul style="margin: 0.25rem 0 0 1.5rem; padding: 0;">
    {% for p in produits_stock_negatif %}
    <li>{{ p.name }} ({{ p.quantite }} {{ p.unite }})</li>
    {% endfor %}
  </ul>
  <p style="margin: 0.5rem 0 0; font-size: 0.9em; opacity: 0.9;">
    {% translate "Vous pouvez bloquer la vente via le menu clic long sur cet article." %}
  </p>
</div>
{% endif %}
```

Réutilise `give-back-box` (existant) avec une variante orange pour cohérence
avec les autres alertes de la session 36. Pas de nouveau composant.

### Modif bonus — `tarif.js:408` (1 ligne)

Pour faire taire le `TypeError` dans la console :

```js
const eleQuantity = document.querySelector(`#article-quantity-number-${productUuid}`)
if (eleQuantity) {
    let tileQty = Number(eleQuantity.innerText)
    tileQty++
    eleQuantity.innerText = tileQty
    eleQuantity.classList.add('badge-visible')
}
```

Le try/catch capture déjà l'erreur — c'est juste de la propreté.

---

## 5. Logique en 4 cas — récap

| `autoriser_vente_hors_stock` | Stock suffisant ? | Comportement |
|---|---|---|
| **True** | Oui | Vente normale, écran succès classique |
| **True** | Non | **Vente passe** + alerte « Stock négatif : ... » sur l'écran de succès |
| **False** | Oui | Vente normale |
| **False** | Non | **Vente BLOQUÉE** + message d'erreur 400 « Stock insuffisant ». Aucune écriture en DB. |

---

## 6. Fichiers concernés

| Fichier | Action |
|---|---|
| `inventaire/services.py` | Modif 1 — `decrementer_pour_vente` retourne bool |
| `laboutik/views.py` (ligne ~3500) | Modif 2 — ajout `_valider_stock_panier` et `_formater_erreurs_stock` |
| `laboutik/views.py:3614-3668` | Modif 3a — `except Stock.DoesNotExist` |
| `laboutik/views.py:3565-3670` | Modif 3b — accumuler `produits_stock_negatif` |
| `laboutik/views.py:3728...` | Idem dans `_creer_lignes_articles_cascade` |
| `laboutik/views.py:4956,5115,5586,6457,6807,8181` | Modif 4 — validation amont + propagation contexte (6 vues) |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Modif 5 — zone alerte stock négatif |
| `laboutik/static/js/tarif.js:408` | Modif bonus — guard null |
| `locale/fr/LC_MESSAGES/django.po` + `en/...` | Nouvelles chaînes à traduire |
| `CHANGELOG.md` | Entrée nouvelle |
| `A TESTER et DOCUMENTER/stock-negatif-vrac.md` | Tests manuels |

---

## 7. Tests à prévoir

### Tests pytest

- `test_decrementer_pour_vente_stock_suffisant` → retourne `False`
- `test_decrementer_pour_vente_stock_passe_negatif` → retourne `True`,
  stock effectivement négatif en DB, `MouvementStock` créé
- `test_valider_stock_panier_vente_hors_stock_autorisee` →
  retourne `[]` même si stock insuffisant
- `test_valider_stock_panier_vente_hors_stock_interdite_stock_ok` →
  retourne `[]`
- `test_valider_stock_panier_vente_hors_stock_interdite_insuffisant` →
  retourne 1 erreur avec `name`, `demande`, `disponible`
- `test_creer_lignes_articles_retourne_produits_negatifs` →
  signature mise à jour
- `test_paiement_bloque_si_stock_insuffisant_et_vente_hors_stock_interdite` →
  status 400, aucune `LigneArticle` créée, partial `hx_messages.html`
- `test_paiement_passe_si_stock_insuffisant_et_vente_hors_stock_autorisee` →
  status 200, `LigneArticle` créée, alerte dans le contexte du template

### Tests E2E Playwright

- `test_pos_vrac_alerte_stock_negatif` :
  - Charger fixture vrac avec `autoriser_vente_hors_stock=True`, stock 200 g
  - Saisir 5000 g au pavé numérique
  - Valider paiement espèces
  - Vérifier présence de `[data-testid="alerte-stock-negatif"]`
  - Vérifier que le texte contient le nom du produit + quantité négative
  - Vérifier que le mot « clic long » apparaît dans le message

- `test_pos_vrac_blocage_vente_hors_stock_interdite` :
  - Idem mais avec `autoriser_vente_hors_stock=False`
  - Vérifier absence de `LigneArticle` créée
  - Vérifier message d'erreur affiché (dépend bug 1 fix B)

### Test manuel

À documenter dans `A TESTER et DOCUMENTER/stock-negatif-vrac.md`.

---

## 8. Hors scope

- **Toast unifié POS** — gros chantier identifié, à traiter dans une session
  dédiée. L'audit a relevé 4 patterns coexistants
  (`HX-Trigger: "stockUpdated"` signal, `appToast`/`panierToast` SweetAlert2,
  Bootstrap toast Django messages). Le POS LaBoutik n'a actuellement aucun
  système toast.

- **Garde au pavé numérique vrac** (`tarif.js`) — empêcher la saisie de
  X g si X > stock disponible. Améliorerait l'UX (feedback instantané sans
  round-trip serveur). Reporté pour limiter le scope de cette session.

- **Erreur JS `tarif.js:409`** — fix bonus inclus, mais analyse plus large
  de la cohérence d'état JS (Session 35 §10) reste à faire.

- **Bug 1 (sortie de caisse 0€ → 400 silencieux)** — traité dans une autre
  session. La fix B (config globale `htmx:beforeOnLoad`) est un **prérequis**
  pour que le blocage du Modif 4a soit visible côté caisse.

---

## 9. Suite

- [ ] Valider ce design avec le mainteneur
- [ ] Implémenter Modif 1 → Modif 5 dans l'ordre, en lançant les tests pytest
      après chaque modification (méthode FALC, max 3 fichiers avant tests)
- [ ] Workflow djc complet : `makemessages` + `compilemessages`, CHANGELOG,
      A TESTER et DOCUMENTER
- [ ] Vérifier en navigateur sur Chrome (vrac avec et sans autoriser hors stock)
- [ ] Confirmer absence de régression : `pytest tests/pytest/test_pos_*.py`
      et `pytest tests/pytest/test_caisse_*.py`
