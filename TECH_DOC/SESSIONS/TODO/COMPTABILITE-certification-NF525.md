# Comptabilité — Sécuriser la chaîne des ventes, certification NF525

> **Status :** idée posée, **spec à écrire** (chantier dédié). Rien n'est codé.
> **Date :** 2026-09-29 (décision du mainteneur pendant le chantier 05, fiche A-3).
> **Pré-requis :** chantier 05 « montants entiers » terminé (chaîne simple des ventes,
> Z unique chaîné, archive, vérification d'intégrité).

## Pourquoi c'est à part
Le chantier 05 livre une **chaîne simple** : chaque vente réglée porte une empreinte
HMAC de ses articles et règlements, chaînée à la précédente, ordonnée par un numéro sans
trou (`laboutik/integrity.py` `calculer_hmac_vente`, `verifier_chaine_ventes`). Elle
détecte une vente, un article ou un règlement modifié, un maillon cassé, un trou au
milieu, une égalité rompue.

Le mainteneur a choisi de **ne pas durcir** la chaîne dans le chantier 05, pour
simplifier et accélérer le développement. Le durcissement et la conformité NF525 (loi
anti-fraude TVA, art. 286 CGI) sont traités ici.

## Constats déjà faits (fiche 05-A-3)
- **Fin de chaîne tronquée** : supprimer la dernière vente (ou la sortir de `REGLEE` par
  un `.update()`) ne laisse aucune trace dans la chaîne. Il faut une ancre extérieure :
  par exemple, chaque Z enregistre le numéro et l'empreinte de la dernière vente couverte,
  et la vérification compare la chaîne à la dernière ancre.
- **Début de chaîne** : une chaîne dont la première vente réglée n'a pas le n° 1 n'est pas
  signalée.
- **Périmètre de l'empreinte** (fiche 05-A §5 telle quelle) : `Reglement.wallet`,
  `Reglement.paiement_stripe`, `LigneArticle.cout_achat`, `Vente.client`, `Vente.operateur`,
  `Vente.carte` n'y entrent pas : un `.update()` sur ces champs n'est pas vu.
- **Suppressions** : `Reglement.delete()` et `LigneArticle.delete()` ne sont pas gardés (seul
  `save()` l'est) ; l'empreinte et les égalités le voient après coup.
- **Clé** : `LaboutikConfiguration.hmac_key` est une clé par lieu, en base : question de
  sa protection et de sa rotation.

## À étudier
- Exigences NF525 (inaltérabilité, sécurisation, conservation, archivage) et ce que la
  chaîne, le Z chaîné et l'archive du chantier 05 couvrent déjà.
- Journal des événements techniques (JET), durée de conservation, export pour
  l'administration.
