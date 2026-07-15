# Impact du chantier IMPRESSION sur `kiosk`

> **Statut : FAIT (2026-07-14).** Le déplacement est effectué, migrations appliquées,
> 846 tests verts. Ce document décrit ce qui a bougé.
>
> Spec complète : [`../IMPRESSION/`](../IMPRESSION/INDEX.md)
>
> **`StripeLocation` a suivi `Terminal`** : elle n'est utilisée que par
> `Terminal.get_stripe_id()`. La laisser dans `kiosk` aurait créé un couplage circulaire
> (`laboutik` → `kiosk` pour la location, `kiosk` → `laboutik` pour la FK `PaymentsIntent`).

## Ce qui change : `kiosk.Terminal` déménage

**`kiosk.Terminal` (`kiosk/models.py:57`) devient `laboutik.Terminal`.**

### Pourquoi

Le chantier IMPRESSION doit rattacher une imprimante au **terminal** (aujourd'hui elle est
rattachée au point de vente, ce qui est faux : 20 tablettes partagent un PV en festival).

Il lui faut donc un objet « appareil appairé » **côté tenant**, capable de porter une FK vers
`laboutik.Printer`. Et cet objet **existe déjà** : c'est `kiosk.Terminal`. Il porte le `name`,
l'`id` UUID, et surtout le `term_user` (OneToOne vers `TibilletUser`, `related_name="terminal"`).

Créer un second modèle `Terminal` à côté était impossible : deux `related_name="terminal"` sur
`TibilletUser` → **`fields.E304`**, Django refuse de démarrer.

### Et c'est une bonne nouvelle pour kiosk

Un **TPE Stripe n'est pas propre au kiosque**. Une caisse LaBoutik pourrait vouloir un TPE sans
être une borne libre-service. En déplaçant `Terminal` dans `laboutik`, le TPE se libère du
kiosque : il devient une **capacité optionnelle** d'un terminal, au même titre que l'imprimante.

```python
# laboutik/models.py (après le chantier)
class Terminal(models.Model):
    id, name, term_user            # l'identité de l'appareil
    printer                        # capacité « imprime »        — NOUVEAU
    registration_code, stripe_id,  # capacité « encaisse par CB » — venue de kiosk
    type, archived
```

Une borne kiosque aura donc **un seul** `Terminal`, qui porte son TPE *et* (si elle en a une)
son imprimante. Pas deux objets concurrents.

## Fichiers de `kiosk` touchés

| Fichier | Changement |
|---|---|
| `kiosk/models.py:57-135` | La classe `Terminal` part vers `laboutik/models.py` |
| `kiosk/models.py:150` | `PaymentsIntent.terminal` → FK vers `laboutik.Terminal` |
| `kiosk/models.py:194` | `send_to_terminal(self, terminal: "Terminal")` → annotation à mettre à jour |
| `kiosk/admin.py:26, 44, 90, 123` | `TerminalForm` / `TerminalAdmin` → déplacés ou réimportés |
| `kiosk/views.py:11, 106` | `request.user.terminal` — **l'accesseur ne change pas**, seul l'import bouge |
| `kiosk/tasks.py` | imports |
| `wsocket/consumers.py:395` | `payment_intent.terminal.term_user_id` — accesseur inchangé, import à vérifier |

**`related_name="terminal"` est conservé tel quel.** `request.user.terminal` continue de
fonctionner partout : on déplace le modèle, on ne renomme pas l'accesseur.

## Point bloquant à trancher avant de commencer

**Le module `kiosk` est-il déployé en production quelque part ?**

- **Non** → déplacement simple, pas de data migration.
- **Oui** → il faut un `SeparateDatabaseAndState` pour déplacer la table entre apps sans
  perdre les TPE appairés et leurs `PaymentsIntent` (`PaymentsIntent.terminal` est en
  `on_delete=PROTECT`).

## Non-régression à vérifier

Le TPE Stripe doit fonctionner exactement comme avant : appairage du reader
(`get_stripe_id()`), envoi d'un `PaymentsIntent` au terminal (`send_to_terminal()`), et le
`TerminalConsumer` WebSocket (`wsocket/consumers.py:256`).
