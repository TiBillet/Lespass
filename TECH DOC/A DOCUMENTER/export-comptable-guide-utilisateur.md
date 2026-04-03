# Export comptable — Guide utilisateur

> Ce guide explique comment configurer l'export comptable de LaBoutik
> pour que votre comptable puisse importer directement vos données de caisse.

---

## 1. C'est quoi un compte comptable ?

En comptabilité, chaque opération financière est enregistrée dans des **comptes numérotés**.
Ces numéros suivent le **Plan Comptable Général (PCG)**, un référentiel officiel français.

### Les grandes familles de comptes

Le premier chiffre du numéro indique la famille :

| Premier chiffre | Famille | Ce que ça représente | Exemple |
|-----------------|---------|---------------------|---------|
| **4** | Tiers | Les taxes (TVA collectée) | `445710` = TVA à 20% |
| **5** | Trésorerie | Où est l'argent (banque, caisse) | `530000` = Caisse espèces |
| **6** | Charges | Les dépenses | `658000` = Écart de gestion |
| **7** | Produits | Les recettes (ventes) | `707000` = Ventes de marchandises |

### Pourquoi débit = crédit ?

Chaque opération s'écrit **deux fois** : une fois en débit, une fois en crédit.
C'est le principe de la **partie double** — les deux colonnes doivent toujours être égales.

**Exemple concret** : vous vendez une bière à 5,00 € en espèces (TVA 20%).

```
DÉBIT (où arrive l'argent) :
  530000 Caisse espèces           5,00 €

CRÉDIT (d'où vient l'argent) :
  707200 Ventes boissons          4,17 € (hors taxe)
  445710 TVA collectée 20%        0,83 € (la taxe)
                                  ------
  Total débits = Total crédits =  5,00 €
```

**Vous n'avez pas besoin de comprendre la comptabilité en détail.**
LaBoutik fait tout le travail — vous configurez juste quels comptes utiliser,
et le logiciel génère les fichiers que votre comptable importe directement.

---

## 2. Pourquoi configurer un mapping ?

Aujourd'hui, quand vous transmettez vos données de caisse au comptable, il doit
**ressaisir manuellement** chaque total dans son logiciel. C'est long et source d'erreurs.

Avec le mapping comptable, LaBoutik génère un **fichier FEC** (Fichier des Écritures
Comptables) que le comptable importe en un clic. Plus de ressaisie, plus d'erreurs.

Le mapping, c'est simplement dire à LaBoutik :
- "Mes ventes de **boissons** vont dans le compte **707200**"
- "Les paiements en **espèces** vont dans le compte **530000**"
- "La **TVA à 20%** va dans le compte **445710**"

---

## 3. Étape 1 : charger un plan par défaut

Plutôt que de créer chaque compte à la main, LaBoutik propose deux jeux pré-configurés.

### Depuis l'interface d'administration

1. Allez dans **Administration** → **Comptes comptables**
2. En haut de la page, un bandeau propose deux options :
   - **Bar / Restaurant** — 15 comptes adaptés aux structures commerciales
   - **Association / Tiers-lieu** — 10 comptes adaptés aux structures associatives
3. Cliquez sur le bouton correspondant à votre activité
4. Les comptes sont créés automatiquement

### Depuis la ligne de commande

```bash
docker exec lespass_django poetry run python manage.py charger_plan_comptable \
    --schema=<nom_de_votre_lieu> --jeu=bar_resto
```

Remplacez `bar_resto` par `association` si vous êtes une association.

### Quels comptes sont créés ?

**Jeu "Bar / Restaurant"** :

| Numéro | Intitulé | Type |
|--------|----------|------|
| 7072000 | Boissons à 20% | Vente |
| 7071000 | Boissons à 10% | Vente |
| 7011000 | Alimentaire à 10% | Vente |
| 7010500 | Alimentaire à emporter 5,5% | Vente |
| 51120001 | Paiement CB | Trésorerie |
| 5300000 | Paiement Espèces | Trésorerie |
| 51120002 | Paiement Tickets Restaurants | Trésorerie |
| 51120000 | Paiement en chèque | Trésorerie |
| 445712 | TVA 20% | TVA |
| 445710 | TVA 10% | TVA |
| 445705 | TVA 5,5% | TVA |
| 709000 | Remises | Spécial |
| 5811000 | Caisse | Spécial |
| 758000 | Écart de gestion + | Exceptionnel |
| 658000 | Écart de gestion - | Charge |

**Jeu "Association / Tiers-lieu"** :

| Numéro | Intitulé | Type |
|--------|----------|------|
| 706000 | Prestations de services | Vente |
| 707000 | Ventes de marchandises | Vente |
| 706300 | Billetterie | Vente |
| 756000 | Cotisations | Vente |
| 512000 | Banque | Trésorerie |
| 530000 | Caisse | Trésorerie |
| 419100 | Avances clients (cashless) | Tiers |
| 445710 | TVA collectée 20% | TVA |
| 445712 | TVA collectée 5,5% | TVA |
| 709000 | Remises | Spécial |

---

## 4. Étape 2 : vérifier les comptes

Les comptes par défaut sont un point de départ. Votre comptable peut vous demander
d'utiliser des numéros différents. Dans ce cas :

1. Allez dans **Administration** → **Comptes comptables**
2. Cliquez sur un compte pour le modifier (numéro, intitulé)
3. Vous pouvez aussi en ajouter de nouveaux ou en désactiver

**Conseil** : envoyez la liste des comptes par défaut à votre comptable et demandez-lui
s'il veut des modifications. C'est une opération à faire une seule fois.

---

## 5. Étape 3 : mapper les catégories d'articles

Chaque catégorie de votre caisse (Boissons, Alimentaire, Billetterie...) doit être
associée à un compte de vente.

1. Allez dans **Administration** → **Catégories de produits**
2. Cliquez sur une catégorie (ex : "Boissons")
3. Dans la section **Comptabilité**, choisissez le compte de vente approprié
   (ex : "7072000 — Boissons à 20%")
4. Enregistrez
5. Répétez pour chaque catégorie

**Si une catégorie n'a pas de compte** : l'export fonctionne quand même, mais un
avertissement s'affiche et les ventes de cette catégorie apparaissent sous
"NON MAPPÉ" dans le fichier. Le comptable devra les ventiler manuellement.

---

## 6. Étape 4 : mapper les moyens de paiement

Chaque moyen de paiement (espèces, CB, chèque...) doit être associé à un compte
de trésorerie.

1. Allez dans **Administration** → **Mapping moyens de paiement**
2. Vous verrez la liste des moyens avec leur compte associé
3. Modifiez si nécessaire

### Détail des mappings par défaut

| Moyen de paiement | Code | Compte par défaut | Explication |
|---|---|---|---|
| Espèces | CA | `530000` Caisse | Argent physique dans le tiroir |
| Carte bancaire (TPE) | CC | `512000` Banque | Encaissement sur le compte bancaire |
| Chèque | CH | `512000` Banque | Encaissement sur le compte bancaire |
| Stripe (en ligne) | SN | `512000` Banque | Paiement en ligne, arrive sur le compte |
| QR / NFC (paiement) | QR | `512000` Banque | Paiement en ligne en vrais euros |
| Cashless monnaie locale | LE | `4191` Avances clients | Argent déjà encaissé à la recharge — la vente "consomme" l'avance |
| Cashless cadeau | LG | *(vide — ignoré)* | Pas d'argent échangé, c'est un cadeau |
| Offert | NA | *(vide — ignoré)* | Pas d'argent échangé |

**Cashless monnaie locale (LE)** : quand un client recharge sa carte cashless,
l'argent est encaissé à ce moment-là (le comptable enregistre l'encaissement lors
de la recharge). Quand le client paie ensuite avec sa carte, il "consomme" son
crédit prépayé. Dans le FEC, cela apparaît comme un débit sur le compte `4191`
(Avances clients) — l'avance diminue.

**Cashless cadeau (LG)** : les tokens cadeaux sont offerts au client. Il n'y a pas
d'argent échangé, donc pas d'écriture comptable. Ce moyen est ignoré dans le FEC.

**QR / NFC (QR)** : ce sont de vrais euros échangés via un paiement en ligne. Ils
sont mappés sur le même compte que la CB (trésorerie bancaire).

**Regrouper plusieurs moyens sur un même compte** : si votre comptable ne distingue
pas CB et Stripe (tout va sur le même relevé bancaire), mettez le même compte
(ex : `512000` Banque) pour les deux. C'est le comportement par défaut.

---

## 7. Étape 5 : exporter le FEC

Une fois le mapping configuré, vous pouvez exporter vos données au format FEC.

### Depuis l'interface d'administration

1. Allez dans **Administration** → **Clôtures de caisse**
2. Cliquez sur le bouton **Export FEC** (en haut de la liste)
3. Choisissez les dates de début et fin (optionnel — sans dates, tout est exporté)
4. Cliquez sur **Télécharger le FEC**
5. Envoyez le fichier `.txt` à votre comptable

### Qu'est-ce que le fichier FEC ?

Le FEC (Fichier des Écritures Comptables) est un format **obligatoire en France**.
Il est accepté nativement par les logiciels :

| Logiciel | Import FEC |
|----------|-----------|
| PennyLane | Direct |
| EBP Hubbix | Direct |
| Odoo | Direct |
| Paheko | Direct |
| Sage | Via import paramétrable |
| Dolibarr | Via import paramétrable |

Le fichier contient 18 colonnes séparées par des tabulations. Chaque clôture
journalière (ticket Z) génère une écriture comptable équilibrée.

---

## 8. FAQ

### Le cashless (NFC) apparaît-il dans l'export ?

Il y a deux types de cashless, avec un traitement différent :

- **Cashless monnaie locale (LE)** : **oui, il apparaît** dans le FEC. L'argent a été
  encaissé à la recharge. La vente consomme l'avance → débit sur le compte `4191`
  (Avances clients). Si votre comptable préfère l'ignorer, videz le compte dans
  le mapping du moyen "Cashless local" dans l'administration.

- **Cashless cadeau (LG)** : **non, il est ignoré**. Les tokens cadeaux sont offerts,
  pas d'argent échangé, donc pas d'écriture comptable.

### Et les remises ?

Les remises ne sont pas encore tracées dans l'export FEC (prévu dans une version
future). Pour l'instant, le comptable les voit dans les rapports de clôture
(PDF, CSV, Excel).

### Et les écarts de caisse ?

Même réponse que les remises — pas encore dans le FEC, visible dans les rapports.

### Une catégorie n'a pas de compte — que se passe-t-il ?

L'export fonctionne quand même. Les ventes de cette catégorie apparaissent avec
le numéro `000000` et la mention "NON MAPPÉ". Un avertissement s'affiche avant
le téléchargement pour vous inviter à compléter le mapping.

### Je veux changer de plan comptable — comment faire ?

1. Allez dans **Comptes comptables**
2. Cliquez sur "Association / Tiers-lieu" (ou "Bar / Restaurant")
3. Si des comptes existent déjà, un message vous avertit
4. Utilisez la ligne de commande avec `--reset` pour repartir de zéro :
   ```bash
   docker exec lespass_django poetry run python manage.py charger_plan_comptable \
       --schema=<nom> --jeu=association --reset
   ```

### Mon comptable utilise un format différent du FEC

Le FEC est le format standard accepté par la majorité des logiciels. Si votre
comptable a besoin d'un format CSV spécifique (Sage 50, EBP classique, Dolibarr...),
cette fonctionnalité est prévue dans une prochaine mise à jour (profils CSV
configurables).
