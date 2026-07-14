# Session 20 — Export comptable : mapping + generateur FEC

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Le briefing complet est dans `TECH DOC/IDEAS/BRIEFING_EXPORT_COMPTABLE.md`.
Cette session couvre les priorites 0 et 1 du briefing.

## TACHE 1 — Modele CompteComptable

Dans `laboutik/models.py`, creer le modele `CompteComptable` :
- `uuid` UUIDField PK
- `numero_de_compte` CharField(20) — ex: "7072000", "530000"
- `libelle_du_compte` CharField(200)
- `nature_du_compte` CharField(30, choices: VENTE, TVA, TRESORERIE, TIERS, CHARGE, PRODUIT_EXCEPTIONNEL, SPECIAL)
- `taux_de_tva` DecimalField(5,2, null/blank) — uniquement pour comptes de vente
- `est_actif` BooleanField(default=True)

Admin Unfold lecture/ecriture.

## TACHE 2 — Modele MappingMoyenDePaiement

Dans `laboutik/models.py` :
- `uuid` UUIDField PK
- `moyen_de_paiement` CharField(10) — reprend les codes PaymentMethod existants (CA, CC, CH, QR, SN, etc.)
- `compte_de_tresorerie` ForeignKey(CompteComptable, null=True, blank=True) — null = moyen ignore a l'export
- Unique sur `moyen_de_paiement`

Admin Unfold.

## TACHE 3 — FK compte_comptable sur CategorieProduct

Dans `BaseBillet/models.py`, ajouter sur `CategorieProduct` :
- `compte_comptable` ForeignKey('laboutik.CompteComptable', null=True, blank=True, SET_NULL)

Le gerant choisit le compte de vente directement dans l'admin de la categorie.

## TACHE 4 — Fixtures par defaut

2 jeux de comptes pre-configures (management command ou JSON fixture) :
- "Bar / Restaurant" (15 comptes)
- "Association / Tiers-lieu" (12 comptes)

Le gerant choisit un jeu lors de la premiere configuration.

## TACHE 5 — Generateur FEC

Dans `laboutik/fec.py` :
- Fonction `generer_fec(clotures, mapping_moyens, comptes_tva)` → bytes (fichier .txt)
- Format : 18 colonnes separees par tabulation, UTF-8, CRLF
- Nom fichier : `{SIREN}FEC{AAAAMMJJ}.txt`
- Chaque cloture = 1 ecriture equilibree (debits = credits)

## TACHE 6 — Vue admin + ViewSet export

- Bouton "Export FEC" dans l'admin des clotures (meme pattern que export fiscal session 18)
- Action ViewSet pour acces depuis le POS si necessaire
- Formulaire : periode debut/fin + bouton telecharger

## TACHE 7 — Documentation utilisateur

Creer `TECH DOC/A DOCUMENTER/export-comptable-guide-utilisateur.md` :
- Explication comptabilite pour debutants
- Comment configurer les comptes
- Comment exporter

## TACHE 8 — Tests

- Tests modeles (CompteComptable, MappingMoyenDePaiement, FK categorie)
- Tests generateur FEC (18 colonnes, equilibre debits/credits, format)
- Tests fixtures (chargement des 2 jeux)

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "comptable or fec"
```

### Critere de succes

- [ ] 2 modeles + 1 FK crees avec migrations
- [ ] Admin Unfold pour CompteComptable et MappingMoyenDePaiement
- [ ] 2 jeux de fixtures chargeables
- [ ] Generateur FEC fonctionnel (fichier .txt 18 colonnes)
- [ ] Export depuis l'admin
- [ ] Documentation utilisateur
- [ ] Tests verts, 0 regression
