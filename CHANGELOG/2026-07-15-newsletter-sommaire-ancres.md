# Newsletter : sommaire « Au programme » avec ancres

**Date :** 2026-07-15
**Migration :** Non

## Ce qui a été fait

Le brouillon de newsletter commence maintenant par un **sommaire** :

> **Au programme**
> - Concert jazz — 18 juillet
> - Atelier cuisine — 20 juillet
> - Marché fermier — 22 juillet

C'est une **liste à puce** (`<ul>`), une puce par évènement, dans l'ordre. Chaque puce est un
**lien d'ancre** `#evt-N` qui saute vers la carte de l'évènement plus bas.

### Modifications
| Fichier | Changement |
|---|---|
| `newsletter/templates/newsletter/email_evenements.html` | Sommaire + liens `#evt-N` · cible d'ancre `<div id="evt-N">` en carte HTML brute avant chaque carte product |
| `tests/pytest/test_newsletter_ghost.py` | 3 tests de rendu ajoutés |

---

## ⚠️ Le point important : où les ancres fonctionnent

| Contexte | Le lien d'ancre saute ? |
|---|---|
| **Post web publié** (Ghost) | ✅ Oui |
| **« Voir dans le navigateur »** (lien auto-ajouté par Ghost en tête de newsletter) | ✅ Oui |
| **Client mail** (Gmail, Outlook, app Apple Mail) | ❌ Non — inerte |

**Ce n'est pas un bug de notre HTML.** Les clients mail ne supportent pas les sauts d'ancre
internes — c'est confirmé par un modérateur Ghost sur le forum officiel. Dans un mail, le lecteur
passe par le **« Voir dans le navigateur »** de Ghost, où le sommaire est pleinement cliquable.

> **Pourquoi pas une URL absolue vers le post pour que ça marche dans le mail ?**
> Parce qu'un **brouillon n'a pas d'URL publique stable** : il est inaccessible tant que le
> gestionnaire ne l'a pas publié, et son slug peut changer à la publication. Une URL absolue bakée
> au moment du brouillon serait donc fausse dans une partie des cas. Le « Voir dans le navigateur »
> de Ghost reste le chemin fiable.

---

## Détail technique : pourquoi une carte HTML brute pour la cible

Une **carte product native de Ghost ne conserve aucun `id`** d'ancre (les nœuds Lexical ne portent
pas d'`id` arbitraire). La seule cible fiable est l'échappatoire documentée
`<!--kg-card-begin: html-->…<!--kg-card-end: html-->`, que Ghost **préserve verbatim**. On y place
un `<div id="evt-N"></div>` vide, juste avant chaque carte. L'`id` est ainsi **contrôlé à 100 %**
(`evt-1`, `evt-2`…), sans avoir à reproduire l'algorithme de slug des titres de Ghost.

---

## Tests à réaliser

### Test 1 : rendu (automatique)
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py::TestRendu -v
```
**13 tests** (dont 3 nouveaux : sommaire, cibles d'ancre, pas de sommaire à vide).

### Test 2 : bout-en-bout sur une vraie instance Ghost
1. Configurer une instance Ghost, générer un brouillon (bouton « Brouillon des N prochains jours »).
2. Ouvrir le brouillon dans l'éditeur Ghost : le sommaire apparaît en tête, en liste à puce.
3. **Publier** le post (ou utiliser l'aperçu web), puis **cliquer une puce** :
   - **Attendu :** la page saute à la carte de l'évènement correspondant.
4. Envoyer/prévisualiser en email, ouvrir dans Gmail :
   - **Attendu :** les puces ne sautent pas (normal) ; via « Voir dans le navigateur », elles sautent.

> ⚠️ À **vérifier sur l'instance réelle** : que Ghost conserve bien les liens `#evt-N` de la liste
> (les listes et liens sont des nœuds Lexical de base — attendu OK) et les `<div id>` des cartes HTML
> brutes. Si un jour Ghost normalisait/supprimait les `href` d'ancre de la liste native, le repli
> serait d'envelopper AUSSI le sommaire dans une carte HTML brute.

---

## Chaînes traduisibles

1 chaîne ajoutée (msgid FR) : **« Au programme »**. **Le workflow i18n est à lancer par le
mainteneur.**
