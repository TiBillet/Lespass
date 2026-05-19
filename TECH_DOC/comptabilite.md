# Comptabilité — Guide utilisateur

> Documentation des fonctionnalités comptables de Lespass : clôtures
> automatiques, exports, plan comptable paramétrable, envoi par email.

## Vue d'ensemble

L'application **Comptabilité** centralise toutes les recettes de votre
lieu (réservations d'événements + adhésions) dans des **clôtures
comptables** datées. Chaque clôture agrège les transactions d'une
période fermée et reste **immuable** une fois créée — ce qui garantit
la traçabilité pour votre comptable.

Quatre périodicités sont gérées :

| Niveau | Fréquence | Heure auto (UTC) |
|---|---|---|
| **J** Journalier | Tous les jours | 06:00 |
| **H** Hebdomadaire | Tous les lundis | 06:15 |
| **M** Mensuel | 1er du mois | 06:30 |
| **A** Annuel | 1er janvier | 06:45 |

Vous pouvez aussi générer une clôture manuelle à tout moment (cf. plus bas).

## Accès dans l'admin

Dans la sidebar de l'admin, section **Sales & accounting** :

- **Cash closure** — liste des clôtures, fiche détail, exports
- **Entries** — toutes les lignes de vente brutes (`LigneArticle`)
- **Accounting accounts** — plan comptable paramétrable
- **Payment method mapping** — mapping moyen de paiement → compte

## Consulter une clôture

Cliquez sur une clôture dans la liste pour voir le **rapport visuel**
en 8 sections :

1. **Totaux par moyen de paiement** — agrégés en 4 catégories :
   Espèces, CB (TPE), En ligne (Stripe + virement), Cashless (NFC).
   Une catégorie « Autres » apparaît si vous avez des chèques,
   offerts, ou paiements inconnus.
2. **TVA par taux** — ventilation HT / TVA / TTC pour chaque taux.
3. **Détail des ventes par catégorie** — billets vs adhésions, avec
   quantités payantes et offertes.
4. **Adhésions** — par produit, tarif et moyen de paiement.
5. **Billets** — par événement, produit et tarif.
6. **Remboursements** — distingue les avoirs comptables et les
   remboursements effectifs.
7. **Synthèse des opérations** — tableau croisé type × moyen.
8. **Infos légales** — organisation, SIRET, TVA, adresse.

Le **hash SHA-256** affiché en bas de la fiche est une empreinte
cryptographique des lignes. Si quelqu'un modifie une ligne après la
clôture, ce hash sera invalidé (détectable via `verify_clotures`).

## Rapport temps réel

URL : `/admin/comptabilite/cloturecaisse/rapport-temps-reel/`
Bouton en haut de la liste : « Open real-time report ».

Cette page calcule le rapport **en direct** sur une période que vous
choisissez. Par défaut : aujourd'hui 04:00 → maintenant.

- Changez les dates avec les sélecteurs HTML5
- Cliquez « Refresh » pour recalculer
- Pas de polling : F5 manuel si vous voulez actualiser

Idéal pour suivre une soirée en cours sans encore créer de clôture
journalière.

## Exports

Sur la fiche détail d'une clôture, **5 boutons d'export** :

| Format | Usage |
|---|---|
| **CSV** | Tableur générique, séparateur `;`, UTF-8 BOM (s'ouvre dans Excel) |
| **Excel** (`.xlsx`) | Multi-sections avec styles, ouverture native LibreOffice/Excel |
| **PDF** | Page A4 imprimable, footer avec SIREN / TVA / hash |
| **FEC** | Fichier des Écritures Comptables, **norme française légale** (article A47 A-1) |
| **Accounting CSV** | CSV adapté à votre logiciel comptable (8 profils disponibles) |

### Profils CSV comptables

Au clic sur **Accounting CSV**, choisissez votre logiciel :

| Logiciel | Format | Encodage | Mode |
|---|---|---|---|
| Sage 50 | `;` | UTF-8 BOM | Débit/Crédit |
| EBP Compta | `,` | CP1252 | Montant + Sens |
| Paheko / Garradin | `;` | UTF-8 | Montant unique |
| Dolibarr ERP | `,` | UTF-8 | Débit/Crédit |
| PennyLane | `;` | UTF-8 | Débit/Crédit |
| CIEL Compta | tabulation | CP1252 | Débit/Crédit |
| Odoo | `,` | UTF-8 | Débit/Crédit |
| DOKO | `;` | UTF-8 | Débit/Crédit |

Le CSV produit ventile chaque clôture en lignes comptables :

- 1 ligne **débit** par moyen de paiement (compte de trésorerie)
- 1 ligne **crédit 706** pour les billets (HT)
- 1 ligne **crédit 756** pour les adhésions (HT)
- 1 ligne **crédit 4457X** par taux TVA

## Configurer le plan comptable

URL admin : **Accounting accounts**.

À l'installation de l'app, **9 comptes par défaut** sont créés selon
le PCG français standard :

- 411000 Clients
- 512000 Banque
- 530000 Caisse (espèces)
- 511000 Chèques à encaisser
- 4457100 TVA 5,5%
- 4457200 TVA 10%
- 4457300 TVA 20%
- 706000 Prestations - Billets
- 756000 Cotisations - Adhésions

Vous pouvez modifier les numéros pour correspondre à votre plan
comptable local (par exemple Québec ou autre pays).

## Configurer le mapping moyens de paiement

URL admin : **Payment method mapping**.

À l'installation, **13 mappings par défaut** sont créés. Vous pouvez
les modifier si votre comptable préfère, par exemple, dissocier les
Stripe SEPA (`SP`) sur un compte distinct.

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

Pour vérifier que personne n'a modifié des données après une clôture,
lancez :

```bash
manage.py verify_clotures
manage.py verify_clotures --tenant=mon-lieu
```

La commande vérifie :

1. **Continuité des numéros séquentiels** — détecte si une clôture a
   été supprimée (trou dans la séquence).
2. **Hash chain** — recalcule le hash SHA-256 de chaque clôture et
   le compare au hash stocké. Si une ligne a été modifiée après la
   clôture, le hash recalculé sera différent.

Sortie type :

```
[tenant=lespass]
  12 cloture(s), numeros 1-12 continus
[tenant=chantefrein]
  3 cloture(s), numeros 1-3 continus

Audit complet : aucune anomalie detectee.
```

## Génération manuelle

```bash
# Clôture journalière pour tous les tenants
manage.py generer_cloture --niveau=J

# Pour un tenant précis
manage.py generer_cloture --niveau=J --tenant=mon-lieu

# Avec une période custom
manage.py generer_cloture --niveau=M \
    --datetime-debut=2026-04-01T00:00:00+00:00 \
    --datetime-fin=2026-05-01T00:00:00+00:00
```

La génération est **idempotente** : si une clôture existe déjà pour
cette période et ce niveau, elle est retournée sans recréation.

## FAQ

**Q : Que se passe-t-il si je modifie une `LigneArticle` après sa
clôture ?**
R : Les données dans le rapport stocké (`rapport_json`) ne changent
pas — c'est un snapshot immuable. Mais si vous lancez
`verify_clotures`, le hash sera détecté comme invalide.

**Q : Puis-je supprimer une clôture ?**
R : L'admin Unfold est en lecture seule. Pour supprimer une clôture,
il faut passer par le shell Django (déconseillé). Si vous supprimez,
la séquence aura un trou détecté par `verify_clotures`.

**Q : Et les ventes POS de LaBoutik ?**
R : LaBoutik n'est pas encore migrée en V1 (planifiée plus tard).
Les `LigneArticle` avec `sale_origin=LABOUTIK` sont **exclues** des
rapports comptables V1 actuels. Quand LaBoutik débarquera, les
rapports incluront naturellement ces ventes.

**Q : Les emails partent à 6h du matin, mais mes utilisateurs ne
sont pas sur UTC...**
R : Pour l'instant les horaires Celery sont en UTC. Une amélioration
future pourrait permettre de choisir le fuseau horaire par tenant.
