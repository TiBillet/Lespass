# Carte de maintenance — autocomplétion de la carte NFC (issue #446)

**Date :** 2026-07-13
**Migration :** Non

Issue : https://github.com/TiBillet/Lespass/issues/446
Signalée depuis la régie par Starsky (stress-test V2, module tireuse).

## Le bug

Sur `/admin/controlvanne/cartemaintenance/add/`, le champ « Carte NFC » était
déclaré en `raw_id_fields`. Django rend alors un **champ texte qui attend le pk
numérique** de la `CarteCashless` (`1`, `2`…), avec une loupe à côté.

En régie, on tape naturellement le **Tag ID** lu sur la puce (`611377E9`). Rien
n'était reconnu, alors que la carte venait d'être créée. Et la loupe ouvrait le
changelist des cartes en popup (`?_to_field=id&_popup=1`) — pris pour un
« formulaire de création de carte ».

La docstring de l'admin annonçait pourtant déjà `autocomplete_fields` : le code
ne faisait pas ce que le commentaire promettait.

## Second défaut, trouvé au passage (non signalé dans l'issue)

`CarteMaintenanceAdmin` n'avait **aucun `formfield_for_foreignkey`**.
`CarteCashless` est en SHARED_APPS (schéma `public`) : aucune isolation
automatique. Le queryset du champ remontait donc **les cartes de tous les lieux**.

Le queryset d'un champ est ce qui **valide** la valeur postée : un pk forgé
pointant vers la carte d'un autre lieu aurait été accepté. `CartePrimaireAdmin`
(`Administration/admin/laboutik.py:268`) documente précisément ce piège et le
corrige — `CarteMaintenanceAdmin` avait copié le modèle sans cette protection.

## Le fix

| Fichier | Changement |
|---|---|
| `controlvanne/admin.py` | `raw_id_fields` → `autocomplete_fields` sur `carte` ; ajout de `formfield_for_foreignkey` filtrant sur `detail__origine=connection.tenant` ; `list_display` et `search_fields` alignés sur `CartePrimaireAdmin` |
| `tests/pytest/test_controlvanne_admin_carte_maintenance.py` | **Nouveau** — 2 tests (widget autocomplete, isolation cross-tenant) |

L'autocomplétion s'appuie sur les `search_fields` de `CarteCashlessAdmin`
(`tag_id`, `number`, `user__email`) : on tape le Tag ID **ou** le numéro imprimé.

### Numéro imprimé vs Tag ID — ce qu'il faut savoir

Ce sont **deux identifiants différents et sans rapport** :
- le **Tag ID** vient de la puce NFC (lisible avec Mifare Classic Tool) ;
- le **numéro imprimé** (`number`) dérive de l'UUID du QR code — c'est lui qui est
  écrit sur la carte physique, lisible à l'œil.

| | Comportement |
|---|---|
| Ce que l'autocomplétion **affiche** | le **numéro imprimé** (`CarteCashless.__str__`) |
| Ce sur quoi elle **filtre** | le Tag ID **et** le numéro imprimé |

Avant ce correctif, la changelist des cartes de maintenance affichait le **Tag ID**
alors que le formulaire proposait le **numéro imprimé** : l'opérateur voyait un
identifiant différent selon l'écran. Les deux colonnes sont désormais affichées côte à
côte, et la recherche couvre les deux — comme sur `CartePrimaireAdmin`.

Aucune migration.

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest \
    tests/pytest/test_controlvanne_admin_carte_maintenance.py -q
```

- `test_le_champ_carte_propose_une_autocompletion` — le widget doit être un
  `AutocompleteSelect`, pas un `ForeignKeyRawIdWidget`.
- `test_le_champ_carte_ne_montre_que_les_cartes_du_lieu_courant` — la carte d'un
  autre lieu ne doit pas être sélectionnable. **Ce test échouait avant le fix**
  (fuite cross-tenant réelle).

## Tests manuels

### Test 1 : le scénario de Starsky (nominal)
1. Créer une carte NFC : `/admin/QrcodeCashless/cartecashless/add/` (noter le Tag ID).
2. Aller sur `/admin/controlvanne/cartemaintenance/add/`.
3. Cliquer sur le champ « Carte NFC » → une liste déroulante s'ouvre avec les
   Tag ID des cartes du lieu.
4. Taper les premiers caractères du Tag ID → la liste se filtre en direct.
5. Sélectionner la carte, « Enregistrer » → « Carte de maintenance … ajoutée avec succès ».

Vérifié en session (Chrome, 2026-07-12) : carte `33BC1DAA` créée bout en bout.

### Test 2 : isolation entre lieux
Avec deux lieux ayant chacun leurs cartes : depuis le lieu A, l'autocomplétion ne
doit proposer **que** les cartes du lieu A. Aucune carte du lieu B, même en
tapant son Tag ID complet.

### Vérification en base
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from controlvanne.models import CarteMaintenance
with tenant_context(Client.objects.get(schema_name='lespass')):
    for cm in CarteMaintenance.objects.select_related('carte'):
        print(cm.carte.tag_id, '|', cm.produit, '|', cm.carte.detail.origine)
"
```
Toutes les lignes doivent afficher le lieu courant en `origine`.

## Compatibilité

Aucune migration, aucun changement de modèle. Les `CarteMaintenance` existantes
restent valides. Seul le widget du formulaire d'admin change.

**Donnée de test laissée en dev** : une carte de maintenance `33BC1DAA` a été
créée sur le tenant `lespass` pendant la validation. À supprimer si elle gêne.
