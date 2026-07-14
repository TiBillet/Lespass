# Design spec : Optimisations Menu Ventes (Session 16b)

**Date** : 2026-03-31
**Contexte** : POS LaBoutik en production festival, 10k+ ventes par soir.
**Scope** : 3 corrections ciblées sur le code écrit en session 16.

---

## 1. Pagination SQL — liste_ventes

### Problème

`liste_ventes` charge TOUTES les `LigneArticle` du service en cours en mémoire
Python, les regroupe dans un dict par `uuid_transaction`, puis pagine le résultat.
Avec 10k ventes → 10k+ objets ORM instanciés à chaque requête de page.

### Solution

Remplacer le regroupement Python par un `GROUP BY` côté PostgreSQL.

```sql
SELECT
    COALESCE(uuid_transaction, uuid) AS cle_vente,
    MAX(datetime) AS datetime,
    SUM(amount) AS total,
    COUNT(uuid) AS nb_articles,
    MAX(payment_method) AS moyen_paiement,
    MAX(point_de_vente__name) AS nom_pv
FROM BaseBillet_lignearticle
WHERE sale_origin = 'LB'
  AND datetime >= <datetime_ouverture>
  AND status = 'V'
GROUP BY cle_vente
ORDER BY datetime DESC
LIMIT 20 OFFSET <offset>
```

**Traduction Django ORM** :

```python
from django.db.models import Max, Sum, Count
from django.db.models.functions import Coalesce

ventes_requete = lignes.values(
    cle_vente=Coalesce('uuid_transaction', 'uuid'),
).annotate(
    datetime=Max('datetime'),
    total=Sum('amount'),
    nb_articles=Count('uuid'),
    moyen_paiement=Max('payment_method'),
    nom_pv=Max('point_de_vente__name'),
).order_by('-datetime')

# Pagination SQL native via slicing Django
ventes_page = list(ventes_requete[offset:offset + taille_page])

# Vérifier s'il y a une page suivante
a_page_suivante = ventes_requete[offset + taille_page:offset + taille_page + 1].exists()
```

### Impact template

La colonne "Articles" dans `hx_liste_ventes.html` affiche
`{{ vente.nb_articles }} article(s)` au lieu de la liste tronquée des noms.
Le détail des noms apparaît au clic (vue `detail_vente`).

### Impact tests

- Adapter `test_liste_ventes_paginee` : vérifier `article(s)` au lieu de noms
- Ajouter un test de pagination avec > 20 ventes

---

## 2. Colonne Chèque dans la vue "par moyen"

### Problème

Le template `hx_recap_en_cours.html` vue `par_moyen` affiche un tableau croisé
avec colonnes "Espèces, CB, Cashless, Total" mais pas "Chèque".
Le `RapportComptableService.calculer_synthese_operations()` retourne pourtant
`cheque` dans chaque ligne du dict.

### Solution

Ajouter une colonne `<th>Chèque</th>` dans le `<thead>` et
`{{ type_data.cheque|euros }}` dans chaque `<tr>` du `<tbody>`.

Fichier : `laboutik/templates/laboutik/partial/hx_recap_en_cours.html`, lignes 261-282.

---

## 3. URL params propres dans le scroll infini

### Problème

Quand aucun filtre n'est actif, l'URL de pagination contient `&pv=&moyen=`.
Fonctionnel mais pas propre (logs, debug, copier-coller).

### Solution

Utiliser `{% if %}` conditionnel dans le template pour n'inclure les params
que s'ils sont non vides.

```html
<!-- AVANT -->
?page={{ page_suivante }}&pv={{ filtre_pv }}&moyen={{ filtre_moyen }}

<!-- APRÈS -->
?page={{ page_suivante }}{% if filtre_pv %}&pv={{ filtre_pv }}{% endif %}{% if filtre_moyen %}&moyen={{ filtre_moyen }}{% endif %}
```

Fichiers : `hx_liste_ventes.html` (2 occurrences : page 1 et pages suivantes).

---

## Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `laboutik/views.py` | Réécriture `liste_ventes` : GROUP BY SQL + COALESCE |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` | Ajout colonne Chèque |
| `laboutik/templates/laboutik/partial/hx_liste_ventes.html` | nb_articles, URL params propres |
| `tests/pytest/test_menu_ventes.py` | Adapter tests existants |

## Vérification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
docker exec lespass_django poetry run pytest tests/e2e/test_pos_menu_ventes.py -v -s
```
