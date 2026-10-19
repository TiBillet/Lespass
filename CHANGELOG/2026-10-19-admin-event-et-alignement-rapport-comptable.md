# Admin événements allégée, alignement du rapport comptable / Lighter event admin, accounting report alignment

**Date :** 2026-10-19
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Liste des événements (`/admin/BaseBillet/event/`) : colonne « Afficher l'heure » retirée.
  / Event list: "show time" column removed.
- Liste des événements : nouvelle colonne « Ressource utilisée » (oui/non), vraie si l'événement bloque une ressource (`ressource_bloquee`). Affichée seulement si le module réservation est actif.
  / Event list: new "Resource used" boolean column, booking module only.
- L'action groupée « Approuver et publier les propositions » (cases à cocher) devient une action de ligne, dans le menu « ... » : « Approuver et publier la proposition », une par une. La liste n'a plus de cases à cocher.
  / The bulk approve action becomes a row action ("..." menu), one event at a time.
- Rapport comptable (fiche de clôture admin, rapport temps réel, PDF joint au mail) : le titre de chaque colonne est aligné comme son contenu. Colonne de nombres → à droite ; colonne de texte ou mixte (« Valeur » de l'en-tête) → à gauche, partout.
  / Accounting report: column headers share their cells' alignment (admin, live report, emailed PDF).

**Pourquoi / Why :** les titres étaient toujours à gauche alors que les montants étaient à droite : on lisait mal quel titre allait avec quel chiffre. / Headers were always left while amounts were right.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `EventAdmin` : `show_time` retiré de `list_display` ; `approuver_propositions` (bulk) → `approuver_proposition` (`actions_row`) ; colonne `display_ressource_utilisee` + `get_list_display` (retirée sans module réservation) |
| `comptabilite/presentation.py` | `_tableau` calcule l'alignement par colonne : `entetes` + `cellule["a_droite"]` |
| `comptabilite/templates/comptabilite/admin/_contenu_section_rapport.html` | Titres et cases suivent `a_droite` |
| `comptabilite/templates/comptabilite/pdf/rapport_comptable.html` | Idem (classe `a-droite`) |
| `tests/pytest/test_event_proposal_admin.py` | Tests passés sur l'action de ligne |
| `tests/pytest/test_seo_cache_fragments.py` | Appel de la nouvelle action de ligne |

---

## Comment tester (a la main) / Manual test

### Test 1 — liste des événements
1. `/admin/BaseBillet/event/` : plus de colonne « Afficher l'heure », plus de cases à cocher à gauche.
2. Menu « ... » d'une proposition en attente (filtre « Propositions ») → « Approuver et publier la proposition » : message de succès, l'événement est publié.
3. Même action sur un événement ordinaire : message « Cet événement n'est pas une proposition en attente. », rien ne change.
4. Colonne « Ressource utilisée » : coche verte sur un événement dont « Ressource bloquée » est remplie, croix sinon. Clic sur l'en-tête : tri.
5. Désactiver le module réservation (Configuration) : la colonne disparaît.

### Test 2 — rapport comptable
1. Ouvrir une clôture : `/admin/comptabilite/cloturecaisse/<uuid>/change/`.
2. Dans chaque tableau : « Montant », « TTC », « HT », « TVA », « Quantité »… sont à droite, au-dessus des chiffres ; « Libellé », « Moyen », « Produit »… à gauche.
3. Section En-tête : la colonne « Valeur » (texte et nombres mêlés) est entièrement à gauche.
4. Bouton PDF (ou le PDF reçu par mail à la clôture) : même alignement.

### Verifs DB / Playwright
- Pytest : `test_event_proposal_admin.py`, `test_seo_cache_fragments.py` (18 verts) ; tests clôture/rapport/exports comptables (244 verts).
- PDF de dev converti en image et relu (alignement correct).
