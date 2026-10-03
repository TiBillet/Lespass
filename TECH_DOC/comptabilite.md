# Comptabilité — Guide utilisateur

> Pour la trésorière ou le trésorier d'un lieu : les clôtures, le rapport
> des ventes, le FEC, le plan comptable, l'envoi par email, l'audit.

## Vue d'ensemble

L'application **Comptabilité** rassemble **toutes les ventes** de votre
lieu dans des **clôtures** : la caisse, la tireuse, les ventes en ligne,
les adhésions, les avoirs faits dans l'admin. Une clôture est le rapport
des ventes d'une période. Une fois créée, elle ne change plus : c'est ce
que votre comptable vérifie.

Il y a quatre sortes de clôtures :

| Niveau | Période | Quand est-elle créée ? |
|---|---|---|
| **J** Journée | Un service : de la fin de la J précédente à la fin du service | Au « Z » de fin de service, sinon par le filet automatique (voir plus bas) |
| **H** Semaine | Du lundi au dimanche | Après la fin de la semaine |
| **M** Mois | Du 1ᵉʳ au dernier jour du mois | Après la fin du mois |
| **A** Année | Du 1ᵉʳ janvier au 31 décembre | Après la fin de l'année |

Toutes les dates sont **à l'heure de votre lieu** (le fuseau horaire de
la configuration).

### La journée (J) et le filet automatique

- Le **« Z » de fin de service** crée la J : elle va de la fin de la J
  précédente jusqu'à maintenant.
- Si personne ne fait le Z, le **filet automatique** le fait. Il passe
  **deux heures après votre heure de fermeture** (réglage « heure de
  fermeture » de la configuration, 2 h par défaut, donc filet à 4 h).
  La J du filet s'arrête à cette heure-là : un service n'est jamais
  coupé en deux.
- Pas de vente depuis la dernière J : pas de nouvelle J.

### La semaine, le mois, l'année (H, M, A)

- Elles comptent **toutes les ventes de la période**, à leur heure
  d'encaissement. Ce n'est pas la somme des J.
- Elles sont créées **après le filet du jour où la période finit** :
  par exemple, le mois d'avril est clôturé le 1ᵉʳ mai à 4 h, après la J
  de la dernière soirée d'avril.
- **Une période sans vente n'a pas de clôture.**
- Si le serveur s'est arrêté plusieurs semaines, les périodes manquées
  sont toutes créées au premier passage, dans l'ordre du calendrier.

Vous pouvez aussi lancer une clôture à la main (voir « Génération
manuelle »).

## Accès dans l'admin

Dans la barre de gauche de l'admin, section **Ventes & comptabilité** :

- **Rapport des ventes** — la liste des clôtures, la fiche d'une
  clôture, ses exports, et le rapport en temps réel.
- **Ancien rapport caisse** — les clôtures de l'ancienne caisse (si le
  module caisse est actif). Il disparaîtra quand toutes les caisses
  utiliseront le rapport des ventes.
- **Plan comptable**, **Comptes des moyens de paiement**, **Comptes des
  monnaies** — voir « Le plan comptable du lieu ».

## Consulter une clôture

Cliquez sur une clôture dans la liste pour voir son **rapport**. Il est
figé : c'est celui calculé au moment de la clôture. L'essentiel vient
d'abord, le détail ensuite :

1. **En-tête** — le lieu et ses mentions légales (adresse, SIREN, TVA),
   la période, le numéro de la clôture, les numéros de la première et de
   la dernière vente, le nombre d'opérations, le total perpétuel.
2. **Chiffre d'affaires** — TTC, HT et TVA ; par taux de TVA, par
   catégorie, par origine (caisse, en ligne…) et par journal.
3. **Règlements** — l'argent reçu par moyen de paiement (espèces, carte,
   chèque, Stripe, virement), le cashless par monnaie (monnaie locale,
   jetons cadeau…), et ce qui n'est pas de l'argent (offerts, points).
4. **Caisse espèces** (journée seulement) — fond de caisse, espèces
   reçues, espèces rendues, sorties de caisse, solde théorique.
5. **Réconciliation** — une phrase qui explique l'argent reçu : ventes
   payées en argent + recharges − remboursements − cartes vidées ± écarts
   d'encaissement.
6. **Offerts** — ce qui a été offert avec le bouton OFFRIR : quantité,
   valeur, coût d'achat.
7. **Annexe** — les avoirs (dont retours de consigne et remboursements
   Stripe à faire à la main), les recharges et les cartes vidées, les
   écarts d'encaissement (en rouge s'il y en a), les corrections de
   moyen de paiement.
8. **Points** — les ventes et les cadeaux en points, par monnaie.
9. **Marge brute** — chiffre d'affaires HT moins le coût d'achat ; le
   nombre d'articles vendus sans prix d'achat est signalé.
10. **Détail des ventes** — billets par événement, adhésions, ventes par
    produit.
11. **Intégrité** (journée seulement) — « OK » si les ventes de la
    journée n'ont pas été modifiées, sinon la liste des anomalies.

L'**empreinte de la clôture** est affichée au-dessus du rapport (voir
« Audit d'intégrité »).

## Rapport temps réel

URL : `/admin/comptabilite/cloturecaisse/rapport-temps-reel/`
(bouton en haut de la liste des clôtures).

Cette page calcule le rapport **en direct**, sans rien enregistrer. Par
défaut, elle montre le service en cours : depuis la fin de la dernière J
jusqu'à maintenant. Vous pouvez choisir d'autres dates (à l'heure du
lieu). Elle ajoute deux sections qui ne sont pas dans les clôtures :
l'habitude des cartes cashless et les ventes par opérateur.

Pratique pour suivre une soirée sans faire le Z. Pour actualiser,
rechargez la page.

## Exports

Sur la fiche d'une clôture, **4 boutons d'export** :

| Format | À quoi ça sert |
|---|---|
| **CSV** | Le rapport de la clôture, à ouvrir dans un tableur |
| **Tableur** (`.xlsx`) | Le même rapport, en plusieurs sections, pour Excel ou LibreOffice |
| **PDF** | Le rapport sur une page A4, à imprimer ou à archiver |
| **FEC** | Les écritures comptables, à importer dans votre logiciel comptable |

## Le FEC : vos écritures comptables

Le FEC (Fichier des Écritures Comptables) est le format légal français
(article A47 A-1 du Livre des procédures fiscales). C'est le **seul
export comptable** de Lespass. Tous les logiciels comptables l'importent :
Sage, EBP, PennyLane, Paheko, Odoo…

### Ce que contient le FEC

- **Une écriture par journal et par journée.** Une journée, c'est une
  clôture journalière (le « Z » de fin de service). Un journal, c'est
  un point de vente (par exemple « BAR »), ou bien « CAISSE », « WEB »,
  « TIREUSE », « ADMIN » pour les ventes sans point de vente.
- **Chaque écriture est équilibrée** : le total des débits égale le
  total des crédits.
  - Au débit : l'argent reçu, un compte par moyen de paiement et par
    monnaie (espèces, carte bancaire, Stripe, monnaie locale…).
  - Au crédit : les ventes hors taxes, la TVA (un compte par taux),
    les recharges de cartes.
  - Un remboursement passe de l'autre côté.
  - Les cadeaux (bouton OFFRIR) et les ventes en points n'ont pas
    d'écriture : aucun argent n'a bougé.
- **La date** d'une écriture est le jour où le service a commencé. Une
  soirée du 31 à 22 h au 1ᵉʳ à 2 h est datée du 31.
- **Le FEC d'un mois** (ou d'une semaine, d'une année) contient les
  écritures des journées datées dans ce mois.
- Le fichier est en UTF-8, avec une tabulation entre les colonnes.

### Importer le FEC dans votre logiciel comptable

1. Ouvrez la clôture (journée ou mois), puis cliquez sur **FEC**.
2. Dans votre logiciel comptable, choisissez « Importer un FEC ».
3. Votre logiciel numérote les écritures à sa façon : c'est normal.
4. Le FEC est **recalculé à chaque export**, avec le plan comptable du
   moment. Une fois importé, c'est votre logiciel comptable qui fige les
   écritures. Voyez avec votre comptable quand exporter.

### Quand le FEC est refusé

Lespass refuse de produire un FEC faux. Rien n'est téléchargé, et un
message rouge explique pourquoi :

- **Un compte manque** : un produit vendu sans compte, un moyen de
  paiement sans compte, un taux de TVA sans compte… Le message nomme la
  journée en cause et renvoie à « Plan complet ? ».
- **Deux points de vente ont le même code journal** (par exemple « Bar 1 »
  et « Bar 2 » donnent tous deux BAR), ou un point de vente prend un code
  réservé (un point de vente nommé « Caisse » prend CAISSE). Donnez à
  chacun un code différent.
- **Une écriture n'est pas équilibrée** : c'est le signe d'une donnée
  modifiée à la main dans la base. Prévenez la coopérative.

## Le plan comptable du lieu

Dans la barre de gauche, section **Ventes & comptabilité** :

- **Plan comptable** : vos comptes, rangés par nature (ventes, TVA,
  trésorerie, tiers, charges).
- **Comptes des moyens de paiement** : le compte de chaque moyen
  (espèces → 530000, carte bancaire → 512100, Stripe → 517100…).
- **Comptes des monnaies** : le compte de chaque monnaie (monnaie
  locale, monnaie fédérée…).

Un plan par défaut est chargé tout seul (comptes à 6 chiffres). Le
bouton « Charger le plan par défaut » remet ce qui manque, sans rien
effacer. **Ajoutez des comptes, ne renumérotez pas ceux du plan par
défaut.**

Le compte d'une vente vient de la **catégorie de caisse** du produit.
Pour qu'un produit aille sur un compte précis, rangez-le dans une
catégorie reliée à ce compte.

### « Plan complet ? »

En tête des trois écrans du plan, l'encadré **« Plan complet ? »** dit
ce qui manque pour que le FEC passe : un produit vendu sans compte, un
moyen ou une monnaie sans compte, un taux de TVA sans compte, deux
points de vente au même code journal… Chaque phrase mène à l'écran qui
règle le problème. Quand tout va bien, l'encadré est vert.

## Envoi automatique par email

Dans **Settings → Configuration**, deux champs :

- **Recipient emails for closure reports** — emails séparés par
  virgule (ex: `compta@mon-lieu.fr, tresorier@mon-lieu.fr`).
- **Closure report sending frequency** — choisissez `No email`,
  `Daily`, `Weekly`, `Monthly` ou `Yearly`.

À chaque clôture matchant la fréquence configurée, un email est
envoyé automatiquement avec le **PDF de la clôture en pièce jointe**.

**Important** : la configuration SMTP doit être en place
(`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` en
variables d'environnement). Sans SMTP, les emails ne partent pas
mais aucune erreur n'est levée.

## Audit d'intégrité

Chaque vente et chaque clôture porte une **empreinte** : un code
calculé à partir de son contenu, avec une clé secrète du lieu.

- Les ventes forment une **chaîne** : chaque vente porte aussi
  l'empreinte de la vente d'avant.
- Toutes les clôtures du lieu (J, H, M, A) forment **une seule chaîne**,
  dans l'ordre de leur numéro. Chaque clôture porte l'empreinte de son
  rapport et celle de la clôture d'avant.
- Si quelqu'un modifie une vente ou une clôture dans la base, supprime
  une clôture ou en ajoute une, la chaîne casse et l'empreinte ne
  correspond plus.

Pour vérifier, lancez :

```bash
manage.py verify_clotures
manage.py verify_clotures --tenant=mon-lieu
```

La commande vérifie :

1. les numéros des clôtures se suivent, sans trou ;
2. chaque clôture a la bonne empreinte et est reliée à la précédente ;
3. les journées se suivent : chaque J commence où la précédente finit,
   et sa première vente suit la dernière de la J précédente ;
4. pour chaque J, les ventes de sa plage n'ont pas été modifiées.

Elle finit par « Audit complet : aucune anomalie detectee. », ou par la
liste des anomalies.

## Génération manuelle

```bash
# Le « Z » de tous les lieux (la J, jusqu'à maintenant)
manage.py generer_cloture --niveau=J

# Pour un seul lieu
manage.py generer_cloture --niveau=J --tenant=mon-lieu

# Le mois précédent, à l'heure du lieu
manage.py generer_cloture --niveau=M --tenant=mon-lieu

# Un mois précis : les bornes doivent être un vrai mois du lieu, avec fuseau
manage.py generer_cloture --niveau=M --tenant=mon-lieu \
    --datetime-debut=2026-04-01T00:00:00+02:00 \
    --datetime-fin=2026-05-01T00:00:00+02:00
```

- Une J n'accepte pas de bornes : elle va toujours de la fin de la J
  précédente à maintenant.
- Une période déjà clôturée ne l'est pas deux fois.
- Une période sans vente, ou dont le filet du dernier jour n'est pas
  encore passé, n'est pas clôturée : la commande le dit (« rien a
  cloturer »).

## FAQ

**Q : Que se passe-t-il si une vente est modifiée après sa clôture ?**
R : Le rapport de la clôture ne change pas : il est figé. Mais
`verify_clotures` signale la vente modifiée (sa chaîne casse). Pour
corriger une vente, on ne la modifie jamais : on fait un avoir ou une
correction de moyen de paiement, qui sont de nouvelles ventes.

**Q : Puis-je supprimer une clôture ?**
R : Non. L'admin est en lecture seule. Une clôture supprimée dans la
base casse la chaîne : `verify_clotures` le signale.

**Q : Et les ventes de la caisse (LaBoutik) ?**
R : Elles sont dans le rapport des ventes, comme les ventes en ligne :
une seule clôture couvre tout le lieu. L'« Ancien rapport caisse »
existe encore, le temps que toutes les caisses passent au rapport des
ventes ; une vente de caisse y apparaît aussi.

**Q : À quelle heure partent les emails ?**
R : Juste après la création de la clôture : après le Z ou après le
filet automatique (deux heures après votre heure de fermeture, à l'heure
du lieu).
