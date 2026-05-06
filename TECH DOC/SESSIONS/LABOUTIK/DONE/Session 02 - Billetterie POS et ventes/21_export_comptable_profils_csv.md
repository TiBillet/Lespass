# Session 21 — Export comptable : profils CSV configurables

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

La session 20 a mis en place le mapping comptable (CompteComptable, MappingMoyenDePaiement,
FK sur CategorieProduct) et le generateur FEC. Cette session ajoute les profils CSV
configurables pour les logiciels comptables qui n'importent pas le FEC nativement.

Le briefing complet est dans `TECH DOC/IDEAS/BRIEFING_EXPORT_COMPTABLE.md` (Priorite 2).

## TACHE 1 — Modele ExportProfile

Dans `laboutik/models.py` :
- `uuid` UUIDField PK
- `nom_du_profil` CharField(200)
- `separateur_de_champs` CharField(2, choices: tab/;/,/|)
- `separateur_decimal` CharField(1, choices: ,/.)
- `format_de_date` CharField(20, choices: AAAAMMJJ, JJ/MM/AAAA, JJMMAA, AAAA-MM-JJ)
- `inclure_les_entetes` BooleanField(default=True)
- `encodage_du_fichier` CharField(20, choices: utf-8, iso-8859-1, cp1252)
- `extension_du_fichier` CharField(5, choices: .csv, .txt)
- `mode_debit_credit` CharField(20, choices: DEBIT_CREDIT, MONTANT_SENS)
- `ordre_des_colonnes` JSONField(default=list)

Admin Unfold.

## TACHE 2 — Generateur CSV configurable

Dans `laboutik/csv_configurable.py` :
- Fonction `generer_csv_comptable(clotures, profil, mapping_moyens, comptes_tva)` → bytes
- Utilise le profil pour : delimiteur, decimal, date, en-tetes, encodage, colonnes
- Reutilise la meme logique de ventilation que le FEC (debits/credits par cloture)

## TACHE 3 — 5 profils pre-configures (fixtures)

1. Sage 50 : ; | . | JJ/MM/AAAA | sans en-tetes | 2 colonnes
2. EBP classique : , | . | JJMMAA | sans en-tetes | montant+sens
3. Dolibarr : , | . | AAAA-MM-JJ | avec en-tetes | 2 colonnes
4. Paheko simplifie : ; | , | JJ/MM/AAAA | avec en-tetes | montant unique
5. PennyLane : ; | , | JJ/MM/AAAA | avec en-tetes | 2 colonnes

## TACHE 4 — Export depuis l'admin

- Selection du profil dans le formulaire d'export (dropdown)
- Bouton "Export CSV" a cote du bouton "Export FEC" existant (session 20)

## TACHE 5 — Tests

- Tests generateur CSV (delimiteurs, encodages, formats de date)
- Tests profils pre-configures (chargement + generation)
- Test equilibre debits/credits identique au FEC

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "comptable or csv_profil"
```

### Critere de succes

- [ ] Modele ExportProfile + migration
- [ ] Generateur CSV configurable
- [ ] 5 profils pre-charges
- [ ] Export depuis l'admin avec choix du profil
- [ ] Tests verts, 0 regression
