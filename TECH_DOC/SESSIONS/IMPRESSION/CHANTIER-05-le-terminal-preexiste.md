# CHANTIER 05 — Le terminal préexiste, le claim le remplit

> **Statut : FAIT (2026-07-14).** 866 tests verts. Cycle complet vérifié dans Chrome :
> créer un terminal → lire son code PIN dans la colonne « État » → l'appairer → « ✓ Appairé ».
>
> **Ce chantier RÉVISE les chantiers [01](./CHANTIER-01-terminal-et-routage.md) et
> [03](./CHANTIER-03-unification-appairage.md)**, où le claim *créait* le terminal.
>
> ⚠️ **Lui-même révisé par le [CHANTIER 06](./CHANTIER-06-extraction-tpe.md).** Ce document
> dit « pas de page TPE bancaires, le TPE est une capacité du terminal » et parle de
> `Terminal.stripe_id`. **C'est faux depuis le 06** : le TPE est un modèle à part
> (`TPEBancaire`), avec sa page admin, et c'est lui qui désigne son terminal.

## Le problème : l'admin mentait

Trois écrans parlaient d'appareils, et aucun ne disait la vérité.

| Ce que le gestionnaire cliquait | Ce qu'il obtenait |
|---|---|
| Terminaux matériels → **Terminaux** | `discovery.PairingDevice` — des **codes PIN**, pas du matériel |
| Kiosque → **« TPE Bancaires »** | `laboutik.Terminal` — **le vrai écran des terminaux**, enterré là |

Cause : au chantier 01, `kiosk.Terminal` est devenu `laboutik.Terminal`. J'ai repointé le lien
pour qu'il ne casse pas, mais **sans renommer ni déplacer l'entrée**. Le vrai écran des
terminaux s'est retrouvé sous un menu « TPE » — et invisible pour un lieu sans module kiosque.

Et plus profondément : **le code PIN d'une tireuse s'affichait à deux endroits**. La liste
« Appairage » n'avait aucun filtre : le gestionnaire y voyait apparaître des lignes qu'il
n'avait jamais créées (celles nées du signal des tireuses).

## Pourquoi le PIN ne pouvait pas être sur le terminal

`TerminalAdmin.has_add_permission` renvoyait `False` : **un terminal naissait du claim.**

Il n'existait donc rien, avant l'appairage, sur quoi afficher le code. C'est *pour ça* que
`PairingDevice` était visible — il était le seul objet à exister pendant la fenêtre « j'ai
préparé l'appairage, l'appareil n'est pas encore branché ».

## Le renversement

**Le terminal existe AVANT l'appareil physique.** Le claim ne le crée plus — il le **remplit**.

```
Admin → Terminaux → « Créer un terminal »
    nom  : « Caisse Bar 1 »
    type : Caisse LaBoutik / Kiosque
         ↓  save_model appelle fabriquer_le_code_pin_d_appairage()
    Un PairingDevice naît dans le schéma public, avec cible_uuid = terminal.id
         ↓
    Colonne « État » du terminal :  880 425     ← le code, là où on le cherche
         ↓  l'appareil tape le code
    Le claim pose le compte (term_user) et la clé sur le terminal qui l'attendait
         ↓
    Colonne « État » :  ✓ Appairé
    Le PairingDevice est consommé (pin + cible vidés) → supprimable
```

`term_user` vide = **en attente**. `term_user` posé = **appairé**. C'est tout le modèle d'état.

## Décisions

| Décision | Raison |
|---|---|
| **`Terminal.terminal_role`** (LB / KI / TI) | Le terminal existe avant le compte : il doit savoir seul quelle sorte d'appareil il attend. C'est ce rôle qui décide **quelle classe de clé** le claim délivrera. Les *choices* viennent de `TibilletUser` — pas de troisième copie. |
| **`PairingDevice` retiré de l'admin** | Ce n'est pas un objet qu'on manipule, c'est un code. `discovery/admin.py` est volontairement **vide**, et le dit. |
| **Le rôle « Tireuse » exclu du formulaire** | Une tireuse porte du métier (fût, débitmètre, prix). Elle se crée depuis son écran, et **fabrique elle-même son terminal**. Un terminal TI créé ici n'aurait aucune tireuse derrière : l'appairage échouerait. |
| **Pas de page « TPE bancaires »** | Un TPE n'est pas un objet, c'est une **capacité** du terminal. On l'active en éditant le terminal. La sidebar tient en deux entrées : Terminaux + Imprimantes. |
| **`Terminal.stripe_id` unique** | Un lecteur physique n'appartient qu'à **un** terminal. Sans ça, deux caisses croiraient piloter le même TPE — et un client verrait s'afficher, sur le lecteur devant lui, le montant de la vente d'à côté. |
| **Action « Générer un nouveau code PIN »** | Le Pi crame. Elle révoque l'ancien appareil (**compte ET clé** — la clé est stockée dessus), détache le compte, et refabrique un code. **Le terminal survit** : il garde son imprimante, et la tireuse qui le désigne garde tout son historique. |

## Le piège qui a coûté le plus cher

**Une fonction, pas un signal.**

L'idée naturelle était un `post_save` sur `Terminal` pour fabriquer le PIN. Fable l'a bloquée,
et il avait raison : **les tests créent des `Terminal` directement**
(`Terminal.objects.create(name="TEST_Caisse1")`, sans compte, sous `FakeTenant`). Chacun
aurait fabriqué un PIN parasite — ou planté sur la clé étrangère `tenant`, qu'un FakeTenant ne
peut pas satisfaire. Il aurait fallu **trois gardes empilés**. De la magie, l'anti-FALC exact.

À la place : **`discovery/services.py : fabriquer_le_code_pin_d_appairage(terminal)`**, appelée
depuis **trois endroits nommés** et seulement eux :

1. `TerminalAdmin.save_model` — le gestionnaire crée un terminal ;
2. `controlvanne/signals.py` — il crée une tireuse (qui fabrique son terminal) ;
3. `TerminalAdmin.generer_un_nouveau_code_pin` — l'appareil est mort, on en appaire un autre.

Un lecteur voit *où* naît un code PIN. Aucune magie.

## Le bug attrapé grâce au check visuel

Le rôle « Tireuse » restait dans le formulaire de création, malgré mon exclusion.

**Cause** : je testais `self.instance.pk` pour distinguer création et édition. Mais
`Terminal.id` est un **`UUIDField(default=uuid4)`** — le PK est donc **déjà rempli sur une
instance neuve**, avant tout enregistrement. Le test était toujours vrai : le formulaire de
création se croyait en édition.

**Le bon test est `self.instance._state.adding`.** C'est exactement le piège déjà rencontré sur
`AuthBillet.TermUser.save()` (voir `tests/PIEGES.md`). Il ne se voit pas en lisant le code — il
s'est vu en ouvrant la page.

## Ce qui a changé, fichier par fichier

| Fichier | Changement |
|---|---|
| `laboutik/models.py` | `Terminal.terminal_role`. `est_appaire()`, `code_pin_en_attente()`. `stripe_id` **unique** |
| `discovery/services.py` | **Nouveau** — `fabriquer_le_code_pin_d_appairage()`, et le pourquoi d'une fonction plutôt qu'un signal |
| `discovery/views.py` | Le claim **remplit** au lieu de créer : `_remplir_le_terminal()` + `_creer_la_cle_du_terminal()`. Transaction atomique |
| `discovery/admin.py` | **Vidé** — `PairingDevice` sort de l'admin |
| `controlvanne/signals.py` | La tireuse fabrique son `Terminal` (rôle TI) et son code |
| `controlvanne/models.py` | `TireuseBec.terminal` posé **à la création**, plus au claim |
| `controlvanne/admin.py` | Le PIN passe en **change view**. Colonne « Raspberry Pi » dans la liste |
| `Administration/admin/laboutik.py` | Création autorisée, rôle TI exclu (`_state.adding`), colonne « État » avec le PIN, action « Générer un nouveau code PIN », unicité du lecteur |
| `Administration/admin/dashboard.py` | Sidebar : **Terminaux + Imprimantes**. Plus d'entrée « Appairage », plus de « TPE Bancaires » |

**Migrations** : `laboutik/0003` (rôle + data migration depuis le compte), `laboutik/0004`
(unicité du `stripe_id`). Rien en production.

## Ce que ça ne fait pas

**L'écran « tireuse non configurée »** côté kiosk (fût manquant, débitmètre absent, prix à 0)
reste à faire. Le serveur refuse déjà proprement de servir dans ce cas
(`viewsets.py` : « Prix non configuré pour ce fût ») — c'est un problème d'**affichage**, pas
de sécurité. Un champ dans le payload WebSocket suffirait : le `PanelConsumer` pousse déjà un
instantané à chaque enregistrement en admin, donc l'écran du Pi se mettrait à jour **tout seul**
dès qu'on pose le fût. Pas besoin de bouton « recharger ».
