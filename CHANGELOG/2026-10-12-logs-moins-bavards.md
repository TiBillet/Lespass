# Logs moins bavards / Less verbose logs

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Retrait de traces de débogage en `logger.info` qui remplissaient les logs de prod :
- `fedow_connect/validators.py` (`validate_hex8`) : le numéro de chaque carte NFC validée (ex. `INFO AB15FB0F`) ;
- `BaseBillet/templatetags/tibitags.py` : `in_list` (une ligne par appel du filtre dans les gabarits) et `dict_key` (le dictionnaire entier) ; l'import du `logger` depuis la commande `demo_data`, devenu inutile, est retiré ;
- `BaseBillet/views.py` (`EventMVT.retrieve`) : `slug :`, `hex8 :`, `event avec hex8 trouvé`, `event avec slug trouvé` à chaque fiche événement.

Les lignes `place info from cache GET` (une par jeton sur `/my_account/`) disparaissent avec `2026-10-12-compte-lent-cache-des-lieux.md`.

/ Debug traces removed from production logs (card numbers, template filters, event lookups).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/validators.py` | log retiré |
| `BaseBillet/templatetags/tibitags.py` | 2 logs + import retirés |
| `BaseBillet/views.py` | 4 logs retirés |

## Comment tester / How to test
`docker logs -f lespass_django` en ouvrant une fiche événement et `/my_account/` : plus aucune de ces lignes.
