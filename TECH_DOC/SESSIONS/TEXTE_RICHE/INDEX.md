# TEXTE_RICHE — Hub permanent

**Date d'ouverture :** 2026-11-27

Ce hub regroupe les chantiers sur les **champs de texte riche** de Lespass :
la saisie dans l'admin (éditeur Trix d'Unfold), le nettoyage à l'enregistrement
(`clean_html`, nh3), les entrées en texte brut (wizard public, API) et le rendu
sur le site public.

Point de départ : la page d'un évènement de La Filature affichait une description
moitié grise sur une colonne, moitié noire sur toute la largeur, après un
copier-coller depuis Protonmail.

## Suivi des chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Description longue des évènements : rendu, éditeur, nettoyage, texte brut | ✅ Parties A, B (simplifiée), C, D et E codées le 2026-11-27, non commitées — reste : commande de réparation à lancer en prod (§3 E) | [SPEC.md](SPEC.md) |

## Comment ajouter un chantier futur

1. Créer `CHANTIER-NN-<slug>.md` à la racine du hub (slug kebab-case).
2. Ajouter une ligne dans le tableau ci-dessus.
3. Si le chantier est non trivial, écrire un plan avec le skill `writing-plans`
   (`PLAN-NN-<slug>.md`).

La section « Hors périmètre » de la SPEC liste les candidats pour un chantier 02.

## Liens utiles

- Éditeur : Unfold 0.89, `unfold/contrib/forms/widgets.py` (`WysiwygWidget`),
  Trix 2.1.1, config Unfold `unfold/forms/js/trix.config.js`.
- Nettoyage : `Administration/utils.py` (`ALLOWED_TAGS`, `clean_html`),
  `Administration/admin/site.py` (`sanitize_textfields`).
- Tests de sécurité existants : `tests/pytest/test_securite_textes_riches_et_personnalisation.py`.
