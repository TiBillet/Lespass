# Le lecteur de carte bancaire devient un objet déplaçable / The card reader becomes a movable object

**Date :** 2026-07-15
**Migration :** **Oui** — `laboutik/0005` (extraction) et `kiosk/0006` (snapshot du lecteur).
`migrate_schemas --executor=multiprocessing`
**Spec :** [`TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-06`](TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-06-extraction-tpe.md)

### 1. Deux périphériques, deux traitements

**Quoi / What :** l'imprimante était un modèle qu'on **lie** à un terminal. Le TPE, lui, était
**trois champs collés** sur `Terminal` (`registration_code`, `stripe_id`, `type`). Il devient un
modèle à part, **`TPEBancaire`**.

**Pourquoi / Why :** deux arguments.
- **Il sera typé.** Aujourd'hui Stripe ; demain SumUp, Stancer — comme `Printer.printer_type`.
- **Il se déplace.** On débranche un lecteur d'une caisse Pi, on le rebranche sur une borne.
  C'est un objet physique.

**C'est le lecteur qui désigne son terminal** (`TPEBancaire.terminal`, OneToOne), pas l'inverse
— parce que c'est le lecteur qu'on déplace. Le débrancher/rebrancher est **une seule édition**,
sur l'objet qu'on a en main. Le `OneToOne` garantit qu'un lecteur ne se branche que sur un
appareil : sinon deux caisses croiraient piloter le même TPE.

### 2. À qui appartient un paiement : à la borne, jamais au lecteur

**Quoi / What :** `PaymentsIntent.terminal` reste la **borne**. Nouveau champ `reader_stripe_id`
qui fige le lecteur au moment de l'envoi.

**Pourquoi / Why :** si le paiement pointait le lecteur, débrancher celui-ci en pleine
transaction ferait perdre à la borne la propriété de son propre paiement — 404 sur son écran,
carte peut-être déjà débitée. Et annuler un paiement plus tard (timeout) viserait le lecteur
**actuellement** branché — qui pourrait servir un autre client. Le snapshot vise le bon.

### 3. Le compte d'un terminal n'est plus modifiable

**Quoi / What :** `Terminal.term_user` sort du formulaire et passe en **lecture seule**.

**Pourquoi / Why :** le compte est posé par l'appairage (le claim), avec un email synthétique.
Le rattacher à un autre compte à la main casserait le lien avec la clé API et la révocation.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/models.py` | **Nouveau** `TPEBancaire`. `Terminal` perd ses 3 champs Stripe |
| `kiosk/models.py` | Le lecteur résolu à l'envoi. **Nouveau** `reader_stripe_id`, utilisé pour l'annulation |
| `kiosk/views.py` | Refus clair si la borne n'a pas de lecteur actif |
| `Administration/admin/laboutik.py` | **Nouveaux** `TPEBancaireForm` + `TPEBancaireAdmin`. `Terminal.term_user` en lecture seule |
| `Administration/admin/dashboard.py` | 3e entrée « TPE bancaires » |
| `Administration/management/commands/demo_data_v2.py` | La borne démo a un `TPEBancaire` branché |

**Sidebar « Terminaux matériels » : Terminaux + Imprimantes + TPE bancaires.**

### À signaler / Heads-up

Le label du champ « Actif » d'un TPE s'affiche « Action » dans l'admin : c'est une traduction
**fuzzy erronée** dans `locale/fr/LC_MESSAGES/django.po` (`msgid "Actif"` → `msgstr "Action"`),
sans rapport avec ce chantier. À corriger au prochain passage i18n.
