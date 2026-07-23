# Les ventes remontent-elles au ticket Z ? / Do sales reach the Z ticket?

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** 16 tests qui partent des VRAIES routes de paiement du point de vente et
verifient que les montants arrivent jusqu'au ticket X et au ticket Z.
/ 16 tests going through the REAL point-of-sale payment routes, checking the amounts reach
the X and Z tickets.

**Pourquoi / Why :** Les tests de vente du depot s'arretent tous a « la LigneArticle existe,
avec le bon montant et le bon moyen de paiement ». Aucun ne demandait ce qui compte pour le
gestionnaire : **est-ce que ce montant apparait sur son ticket de caisse ?**

Une vente peut etre parfaitement enregistree et rester invisible du rapport — il suffit
qu'elle porte une origine que le rapport ne lit pas. C'est ce qui s'est produit deux fois
cette semaine : les remboursements de carte et les ventes de tireuse.

Avant ce chantier, **un seul test du depot** faisait ce lien
(`test_paiement_complementaire.py`, cascade NFC fractionnee).

### Fichier ajoute / Added file

`tests/pytest/test_ventes_remontent_au_ticket_z.py` — 16 tests.

## Ce que les tests couvrent

| Sujet | Ce qui est verifie |
|---|---|
| Especes, carte bancaire | le montant exact atterrit sur le bon poste, et nulle part ailleurs |
| Total general | vaut la somme exacte des postes, sur des ventes de moyens differents |
| Detail des ventes | nomme les produits vendus, sous leur categorie, au bon montant |
| Ventilation TVA | separe les taux, et HT + TVA retombe exactement sur le TTC encaisse |
| Solde de caisse | suit les especes ; une carte bancaire ne remplit pas le tiroir |
| Perimetre | la tireuse entre, la vente en ligne reste dehors, une vente annulee ne compte pas |
| Ticket Z | fige exactement ce que le ticket X annoncait juste avant |
| Ticket Z | porte le detail relu par le PDF et le CSV |
| Cloture | refusee si aucune vente ; deux cloture successives ne comptent pas deux fois |
| Cloture | le numero sequentiel s'incremente sans trou |

**Montants exacts, pas des inegalites.** Le fichier utilise `FastTenantTestCase` : schema
isole, rollback entre chaque test. On verifie donc que `especes == 1100`, la ou les tests
tournant sur la base de dev partagee doivent se contenter de `>= 500` ou de deltas.

**Vraies routes, pas de `LigneArticle` fabriquee.** C'est la route qui decide de l'origine,
du statut, du moyen de paiement et du point de vente — precisement ce qu'on veut verifier.
Les tests de cloture existants injectent leurs lignes en base avec `sale_origin` code en dur :
ils valident l'arithmetique du rapport, mais sont structurellement incapables de detecter une
regression d'attribution. C'est le mecanisme qui a laisse passer les deux defauts de la
semaine.

## Les tests ont ete verifies par mutation

Un test qui passe ne prouve rien tant qu'on n'a pas vu ce qui le fait echouer. Deux mutations
temporaires du code de production, restaurees ensuite :

| Mutation | Resultat |
|---|---|
| retirer `TIREUSE` du perimetre du rapport | test en echec ✓ |
| faire entrer `LESPASS` dans le perimetre | **test PASSANT — le test ne prouvait rien** |

La seconde a revele un defaut de conception dans mon propre test : la vente en ligne y portait
`STRIPE_NOFED`, un moyen de paiement que le total n'additionne de toute facon pas. Le test
aurait passe meme si l'exclusion avait saute. Corrige en lui donnant `CASH`, un moyen que le
rapport sait sommer — la mutation est desormais detectee.

## Defaut LATENT, NON corrige

**Le total general n'est pas la somme des ventes du rapport.**

`calculer_totaux_par_moyen` additionne CINQ postes : especes, carte bancaire, cashless, cheque,
federe. Une vente de caisse reglee autrement compterait dans le nombre de transactions, dans le
detail des ventes et dans la ventilation TVA — **mais pas dans le total general**. Le ticket ne
s'equilibrerait plus avec lui-meme.

**Ce cas ne se produit pas aujourd'hui : zero ligne concernee en base, sur tous les tenants.**
Le chemin existe pourtant — `fedow_connect/views.py` cree une ligne de caisse avec un moyen de
paiement « inconnu » quand une adhesion est reglee depuis un portefeuille federe — mais il
depend du webhook d'interoperabilite, qui n'est pas encore actif (un `# TODO` dans ce fichier
annonce « quand LaBoutik sera integree »).

C'est donc une fragilite dormante, pas un defaut en production. Elle merite d'etre connue avant
que ce webhook ne s'active.

`test_un_moyen_de_paiement_non_ventile_manque_au_total_general` **decrit** ce comportement. Il
verifie que le detail totalise bien les deux ventes, que le total general n'en compte qu'une,
et il porte un message qui demande sa mise a jour le jour ou la divergence sera corrigee.

Correction non faite ici : elle touche la composition du total, donc la cloture, les exports et
le chainage LNE. A trancher.

---

## Comment tester (a la main) / Manual test

### Test 1 — le ticket X suit les encaissements

1. Ouvrir la caisse, encaisser une vente en especes puis une par carte.
2. Ouvrir le rapport temps reel : chaque montant doit figurer sur son poste, et le total
   general doit valoir leur somme.

### Test 2 — le ticket Z fige le ticket X

1. Noter les totaux du rapport temps reel.
2. Cloturer.
3. Le ticket Z doit annoncer exactement les memes montants.

### Test 3 — deux cloture ne se recouvrent pas

1. Encaisser, cloturer, noter le total.
2. Encaisser a nouveau, cloturer.
3. La seconde cloture ne doit contenir QUE les ventes posterieures a la premiere.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_ventes_remontent_au_ticket_z.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1035 tests verts**, aucun echec.

## Ce qui reste a couvrir / Still uncovered

Familles de vente sans test de bout en bout jusqu'au rapport :

- **billetterie POS** — `test_billetterie_pos.py` verifie la reservation et le billet, puis
  **supprime ses lignes** en fin de test : meme une cloture ulterieure ne les verrait pas ;
- **tireuse connectee** — `test_controlvanne_billing.py` verifie le montant debite et le solde
  du portefeuille, jamais la `LigneArticle` produite. Le present fichier couvre la remontee
  d'une ligne d'origine tireuse, mais ecrite a la main : la chaine reelle depuis l'API de la
  tireuse reste non testee ;
- **recharges cashless** et **adhesions vendues en caisse** — `calculer_recharges()` et
  `calculer_adhesions()` n'ont aucun test de valeur.
