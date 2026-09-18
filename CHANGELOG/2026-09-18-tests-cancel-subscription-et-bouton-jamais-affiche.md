# Tests de CancelSubscription + bouton d'arret du prelevement jamais affiche

## 1. Tests de la vue CancelSubscription / Tests for the CancelSubscription view

**Quoi / What:** Ajout de `tests/pytest/test_cancel_subscription.py` (12 tests)
couvrant toutes les branches de `ApiBillet/views.py::CancelSubscription`.

**Pourquoi / Why:** Le chemin du gabarit HTMX rendu par la vue vient de changer
(`fonctionnel/compte/membership/` -> `pages/classic/vues/compte/membership/`).
L'ancien dossier n'existe plus : sans ce changement, toutes les reponses HTMX
levaient `TemplateDoesNotExist`. Aucun test pytest ne couvrait cette vue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_cancel_subscription.py` | Nouveau : 12 tests (UUID invalide, adhesion inconnue, non recurrente, sans id Stripe, erreur Stripe, succes, HTMX + JSON) |

### Migration
- **Migration necessaire / Migration required:** Non

---

## 2. BUG : le bouton « Arreter le prelevement automatique » ne s'affiche jamais

**Quoi / What:** Dans `membership_card.html` (skins `classic` ET `V2`), le bouton
d'arret du prelevement est conditionne par `membership.status == 'A'`.
Or `'A'` est la constante `Membership.ONCE`, pas `Membership.AUTO` (qui vaut `'O'`) :

```python
# BaseBillet/models.py:3903
ONCE, AUTO =  'A', 'O'
```

La condition complete du gabarit est :
```django
{% if membership.status == 'A' and membership.stripe_id_subscription and not membership.price.commitment %}
```

Les deux premieres conditions sont mutuellement exclusives :
`BaseBillet/triggers.py:37-45` pose `status = ONCE` par defaut, puis bascule sur
`status = AUTO` **en meme temps** qu'il renseigne `stripe_id_subscription`.
Une adhesion `ONCE` n'a donc jamais d'identifiant d'abonnement.
**Resultat : le bouton n'est rendu dans aucun cas.**

Meme cause pour le badge : `{% if membership.status == 'A' %}` affiche
« Paiement recurrent » sur les adhesions payees **une seule fois**.

**Pourquoi / Why:** Le gabarit teste la valeur `'A'` en dur au lieu d'utiliser la
constante du modele. L'inversion `ONCE, AUTO = 'A', 'O'` est piegeuse a la lecture.

### Fichiers concernes / Affected files
| Fichier / File | Ligne | Changement propose / Proposed change |
|---|---|---|
| `pages/templates/pages/classic/vues/compte/membership/membership_card.html` | 37, 39, 94 | `status == 'A'` -> `status == 'O'` (badge recurrent + bouton), `status == 'C'` inchange |
| `pages/templates/pages/V2/vues/compte/membership/membership_card.html` | 56, 58, 109 | idem |

### Test de non-regression / Regression test
`tests/pytest/test_cancel_subscription.py::test_le_bouton_arreter_le_prelevement_est_affiche_pour_une_adhesion_auto`
**echoue aujourd'hui** et passera une fois le gabarit corrige.

### Migration
- **Migration necessaire / Migration required:** Non

---

## Comment tester / How to test

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cancel_subscription.py -v
```

Resultat attendu aujourd'hui : **11 passent, 1 echoue** (le test du bouton,
qui documente le bug ci-dessus).
