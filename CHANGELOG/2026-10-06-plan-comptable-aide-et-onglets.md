# Plan comptable : une entrée de menu, onglets « Gérer » (la balance) / « Configurer », une aide FALC par page / Chart of accounts: one menu entry, "Manage" (trial balance) / "Configure" tabs, a plain-language help on each page

**Date :** 2026-10-06
**Migration :** Non

## Résumé / Summary

**Quoi / What :**
1. **Un seul menu « Plan comptable »** (`Administration/admin/dashboard.py`) : les trois
   entrées « Plan comptable », « Comptes des moyens de paiement », « Comptes des
   monnaies » du groupe « Ventes & comptabilité » deviennent UNE entrée, qui ouvre
   l'onglet « Gérer ». Elle reste marquée active sur les quatre pages du plan.
   / One menu entry instead of three; it opens the "Manage" tab and stays active on the
   four plan pages.
2. **Deux onglets** (`_onglets_du_plan_comptable`, branché dans `get_tabs`) :
   - **Gérer** : la **balance** (nouvelle page en lecture seule) ;
   - **Configurer** : les trois listes de réglage (comptes, moyens de paiement,
     monnaies), reliées par un second niveau de liens
     (`Administration/templates/admin/comptable/sous_onglets_configurer.html`, page
     affichée en `aria-current="page"`). Unfold ne dessine qu'une barre d'onglets par
     page : le second niveau est dessiné par nos gabarits « avant la liste ».
   L'onglet actif est calculé par nous (Unfold compare les adresses avec « in » et se
   tromperait : l'adresse des comptes est contenue dans celle de la balance). La barre
   n'apparaît jamais sur les fiches. Les adresses des trois listes ne changent pas :
   « Plan complet ? », la règle 7 et les autres liens restent justes.
   / Two tabs: Manage = trial balance; Configure = the three settings lists with a
   second-level link row. Active state computed by us; list URLs unchanged.
3. **La balance** (`comptabilite/balance.py`, vues `CompteComptableAdmin.balance` et
   `balance_csv`, gabarit `admin/comptable/balance.html`) : pour une période (par défaut
   le mois en cours, dans le fuseau du lieu), une ligne par compte qui a bougé (numéro,
   libellé, débit, crédit, solde débiteur ou créditeur), rangée par numéro et groupée
   par famille (4, 5, 6, 7), puis le total : total débit = total crédit, vérifié
   (alerte visible sinon). **Les chiffres sont ceux du FEC** : même choix des clôtures J
   (datées du jour local de leur première vente, `journees_datees_entre`), mêmes
   écritures (`ecritures_des_journees`, extrait de `ecritures_de_l_export` : le FEC et
   la balance appellent la même fonction). Aucun calcul refait. Mêmes refus que le FEC
   (compte manquant, écriture déséquilibrée), avec le même message, affiché à la place
   du tableau. Bouton « Télécharger la balance (CSV) » (« ; », UTF-8 avec BOM, montants
   à la française, comme l'export CSV d'une clôture). Réservée aux administrateurs du
   lieu.
   / Trial balance over a period, figures from the FEC code (same J selection, same
   entries), same refusals, CSV download.
4. **Une aide repliable en FALC en tête de chaque page** (balance, comptes, moyens de
   paiement, monnaies) : `<details>` fermé par défaut, `<summary>` lisible au clavier.
   Les numéros cités sont ceux du plan par défaut (vérifiés par un test). Corrections
   des exemples du cahier des charges : la carte bancaire va au **512100** (pas 512000
   « Banque »), le paiement en ligne au **517100** (Stripe) ; les jetons cadeau sont
   rangés au **419100** (comme la monnaie locale) et c'est le jeton DÉPENSÉ qui va au
   **707900** (un compte de vente ne peut pas être le compte d'une monnaie).
   / A closed plain-language help on each page; numbers checked against the default
   plan; examples corrected (card 512100, online 517100, gift tokens 419100 then 707900
   when spent).

**Pourquoi / Why :** le bénévole d'une association n'est pas comptable : un seul point
d'entrée, les sommes d'abord (la balance), les réglages ensuite, et des explications
simples. / A volunteer is not an accountant: one entry, the sums first, settings next,
simple explanations.

## Fichiers / Files
- `Administration/admin/dashboard.py` — une entrée de menu, `_onglets_du_plan_comptable`.
- `Administration/admin/laboutik.py` — vues `balance`, `balance_csv`, période.
- `comptabilite/balance.py` (nouveau) — la balance et son CSV.
- `comptabilite/ventilation.py` — `ecritures_des_journees` (extraite, comportement du
  FEC inchangé) et `journees_datees_entre`.
- `Administration/templates/admin/comptable/balance.html`,
  `sous_onglets_configurer.html` (nouveaux) ; `changelist_before.html`,
  `moyens_changelist_before.html`, `monnaies_changelist_before.html` (aide, second
  niveau).
- Tests : `tests/pytest/test_admin_plan_comptable_aide_et_onglets.py` (nouveau),
  `tests/pytest/test_fec_equilibre.py` (section « La balance »), mis à jour :
  `test_plan_comptable_unique.py`, `test_admin_vente.py`,
  `test_admin_alignements_et_fiche_vente.py`, `tests/e2e/test_admin_plan_comptable.py`.

## Non fait / Not done
- **Refus avant la bascule (Q-R3)** : la règle n'existe pas encore dans le code du FEC
  (chantier R, aucune marque de « J reprise » ni de date de bascule en base). La balance
  appelle la même fonction que le FEC (`ecritures_des_journees`) : le refus, posé là par
  le chantier R, s'appliquera aux deux. / The pre-switch refusal is not in the FEC code
  yet; adding it in the shared function will cover both.

## Traductions / Translations
Nouvelles chaînes (source en français) à passer par `makemessages` (mainteneur) : titres
des onglets et du second niveau (« Gérer », « Configurer », « Comptes », « Moyens de
paiement », « Monnaies »), titres et phrases des quatre aides, « Balance des comptes »,
« Période », « Du », « Au », « Afficher », « Télécharger la balance (CSV) », en-têtes
du tableau (« Compte », « Libellé », « Débit », « Crédit », « Solde débiteur », « Solde
créditeur », « Total »), noms des familles, messages du refus, du déséquilibre, de la
page vide et du nombre de clôtures (pluriel).
