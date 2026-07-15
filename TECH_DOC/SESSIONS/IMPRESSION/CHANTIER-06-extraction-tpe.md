# CHANTIER 06 — Le lecteur de carte bancaire devient un objet

> **Statut : FAIT (2026-07-15).** Vérifié dans Chrome, suite complète verte.
>
> Ce chantier **révise la décision « pas de proxy TPE »** posée aux chantiers 01 et 05.

## Le problème : deux périphériques, deux traitements

L'imprimante est un **modèle** (`Printer`, avec un `printer_type` et des backends dans
`laboutik/printing/`) qu'on **lie** au terminal par une clé étrangère. Le TPE, lui, était
**trois champs collés sur `Terminal`** : `registration_code`, `stripe_id`, `type`.

Le maintainer a vu l'asymétrie, et l'a tranchée avec deux arguments qui n'étaient pas sur la
table aux chantiers précédents :

1. **Le TPE sera typé.** Aujourd'hui Stripe ; demain SumUp, Stancer. Exactement ce que
   `Printer.printer_type` porte déjà pour les imprimantes.
2. **Un lecteur se déplace.** On le débranche d'une caisse Pi, on le rebranche sur une borne.
   C'est un objet physique, avec sa vie propre — pas un attribut de l'appareil.

## D'où venait la fusion

Ce n'est pas ce chantier qui l'avait créée. Vérifié dans l'historique :

- **LaBoutik V1** : `Appareil` (le matériel) + `Terminal` (le TPE, FK → `Appareil`,
  `related_name="terminals"` — un appareil pouvait avoir N TPE).
- **kiosk** a supprimé `Appareil` et fait porter au TPE le lien vers la borne. « 1 borne =
  1 TPE », assumé.
- **Chantier 01** a promu ce `Terminal`=TPE en « appareil appairé » et lui a ajouté
  l'imprimante. Les champs Stripe sont devenus des **résidus** sur un objet qui avait changé
  de nature.

## Le modèle

```python
class Terminal:                       # l'appareil
    printer = FK(Printer)             # capacité « imprime » (partageable → FK)
    # le lecteur pointe vers ICI, via TPEBancaire.terminal

class TPEBancaire:                    # le lecteur de carte
    name
    tpe_type                          # 'SW' Stripe (demain SumUp, Stancer)
    terminal = OneToOne(Terminal, related_name='tpe', SET_NULL)
    registration_code, stripe_id (unique)
    active
```

### Pourquoi le lien est porté par le TPE, pas par le Terminal

C'est **l'inverse de l'imprimante**, et c'est voulu.

| | Imprimante | TPE |
|---|---|---|
| Cardinalité | N terminaux → 1 imprimante (cloud partageable) | 1 lecteur ↔ 1 appareil |
| Lien | `Terminal.printer` (FK) | `TPEBancaire.terminal` (OneToOne) |
| Geste | on assigne une imprimante à un terminal | **on déplace un lecteur** |

Le lien vit du côté de **l'objet qu'on prend en main**. Déplacer un lecteur = **une seule
édition**, sur le lecteur : on l'ouvre, on lui change d'appareil. S'il était porté par le
terminal, il faudrait deux éditions (vider l'ancien, remplir le nouveau — sinon
`IntegrityError` sur la contrainte unique).

Le `OneToOneField` garantit qu'**un lecteur ne se branche que sur un seul appareil** : sans
ça, deux caisses croiraient piloter le même TPE, et un client verrait s'afficher, sur le
lecteur devant lui, le montant de la vente d'à côté.

## Le point délicat : à qui appartient un paiement ?

`PaymentsIntent.terminal` **ne bouge pas** — il pointe la **borne**, pas le lecteur.

Si le paiement pointait le lecteur, la chaîne de sécurité deviendrait
`paiement → tpe → terminal → term_user`, et elle **casserait dès qu'on déplace un lecteur** :
un paiement en cours dont le lecteur est débranché n'appartiendrait plus à personne. La borne
prendrait un 404 sur son propre paiement, écran bloqué, carte peut-être déjà débitée. **La
feature demandée saboterait la garde IDOR des chantiers 02.**

Un paiement appartient à la **borne qui l'a lancé**. Le lecteur est résolu **au moment de
l'envoi** (`send_to_terminal` : `getattr(terminal, "tpe", None)`).

### Le snapshot du lecteur

`PaymentsIntent.reader_stripe_id` retient sur quel lecteur le paiement est **réellement** parti.

Sinon, annuler un paiement plus tard (timeout Celery, annulation manuelle) relirait le lecteur
**actuellement** branché sur la borne. Or un lecteur se déplace : si on l'a débranché
entre-temps, on enverrait le `cancel` au **mauvais** lecteur — coupant le paiement d'un autre
client, en train de payer ailleurs sur ce même lecteur.

## Ce qui a changé

| Fichier | Changement |
|---|---|
| `laboutik/models.py` | **Nouveau** `TPEBancaire` (avec `statut_chez_stripe()`, `appairer_chez_stripe()`). `Terminal` perd ses 3 champs Stripe ; `a_un_tpe()` lit la relation inverse |
| `kiosk/models.py` | `send_to_terminal` résout le lecteur à l'envoi. **Nouveau** `reader_stripe_id`. `annuler_sur_le_terminal` vise le lecteur du snapshot |
| `kiosk/views.py` | Le repli DEMO exige un lecteur ; erreur claire si la borne n'en a pas |
| `Administration/admin/laboutik.py` | **Nouveaux** `TPEBancaireForm` + `TPEBancaireAdmin` (avec « Vérifier le statut chez Stripe »). `TerminalForm` allégé de tout le TPE |
| `Administration/admin/dashboard.py` | 3e entrée « TPE bancaires » dans « Terminaux matériels » |
| `Administration/management/commands/demo_data_v2.py` | La borne démo a un compte, un Terminal, et un TPEBancaire branché |

**Migrations** : `laboutik/0005` (CreateModel → RunPython de copie → RemoveField, **dans cet
ordre**, sinon les lecteurs seraient perdus), `kiosk/0006` (`reader_stripe_id`). Rien en prod.

## Ce qu'on n'a PAS fait, et pourquoi

**Pas de package Strategy** (miroir de `laboutik/printing/`). Il y a **un** fournisseur réel.
SumUp et Stancer n'ont ni API connue ici, ni date. Construire l'abstraction sur un échantillon
de 1 la rendrait fausse le jour où on lira la vraie doc SumUp. Les appels Stripe sont
volontairement rassemblés dans **deux méthodes** de `TPEBancaire` et **deux** de
`PaymentsIntent` — le jour venu, l'extraction sera mécanique. Un commentaire dans le modèle le
dit.

**Un seul flag `active`** sur le TPE, pas `active` + `archived` — comme `Printer`.
