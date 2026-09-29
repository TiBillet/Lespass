"""
Les colonnes de l'admin ont un libellé, pas un nom de champ Python.
/ Admin columns carry a label, not a Python field name.

LOCALISATION : tests/pytest/test_admin_verbose_name.py

CE QUE CE FICHIER PROTEGE
-------------------------
Sans `verbose_name`, Django fabrique un libellé à partir du nom du champ :
`last_response` devient « Last response », `created_on` devient « Created on ».
Le résultat s'affiche donc **en anglais**, au milieu d'une interface française,
et aucun test fonctionnel ne le remarque.

Au relevé, **62 champs** de modèles affichés dans l'admin étaient dans ce cas.

CE QUI RESTE, ET POURQUOI. Neuf identifiants techniques (`uuid`, `id`) sont
laissés tels quels : ce sont des champs en lecture seule qui n'intéressent que
le débogage, et les renommer aurait ajouté de la migration pour rien. Ils sont
listés nommément ci-dessous — la liste est une **décision**, pas un oubli, et
c'est ce qui distingue les deux.
/ Eight technical identifiers are deliberately left: the allowlist below is a
  decision, not an oversight.

ATTENTION EN AJOUTANT UN CHAMP. `verbose_name` génère une migration
`AlterField`, à appliquer schéma par schéma sur ce projet multi-tenant. Ce
n'est pas une simple passe de traduction.
/ verbose_name generates an AlterField migration, applied per schema here.
"""

import pytest

from Administration.admin.site import staff_admin_site

# Champs volontairement laissés sans libellé : identifiants techniques,
# affichés en lecture seule, sans valeur pour un utilisateur.
# / Deliberately left: technical identifiers, read-only, of no user value.
TOLERES = {
    ("BaseBillet", "Tag", "uuid"),
    ("BaseBillet", "Ticket", "uuid"),
    ("fedow_core", "Federation", "uuid"),
    ("fedow_public", "AssetFedowPublic", "uuid"),
    ("fedow_core", "Transaction", "id"),
    ("laboutik", "CommandeSauvegarde", "uuid"),
    ("laboutik", "HistoriqueFondDeCaisse", "uuid"),
    ("laboutik", "ImpressionLog", "uuid"),
    ("laboutik", "JournalOperation", "uuid"),
    # Libellé posé par le formulaire, pas par le modèle :
    # FutProductForm.__init__ l'affiche « Caractéristiques (style, degré, IBU…) »
    # (Administration/admin/products.py). Choix fait pour éviter une migration
    # AlterField sur chaque tenant. Ce test lit seulement le verbose_name du modèle.
    # / Label set by the form, not the model, to avoid a per-tenant migration.
    ("BaseBillet", "FutProduct", "tag"),
}


def _champs_cites(admin):
    """
    Tous les noms de champs qu'une classe d'admin affiche.
    / Every field name an admin class displays.
    """
    noms = set()
    for attribut in (
        "list_display",
        "list_editable",
        "readonly_fields",
        "search_fields",
    ):
        noms |= set(getattr(admin, attribut, None) or [])
    for groupe in getattr(admin, "fields", None) or []:
        noms |= set(groupe) if isinstance(groupe, (list, tuple)) else {groupe}
    for _titre, options in getattr(admin, "fieldsets", None) or []:
        for groupe in options.get("fields", ()):
            noms |= set(groupe) if isinstance(groupe, (list, tuple)) else {groupe}
    return noms


def _sans_libelle():
    """
    Les (app, modele, champ) affiches sans `verbose_name` explicite.

    Django pose un `verbose_name` par defaut egal au nom du champ avec les
    underscores remplaces par des espaces. C'est cette egalite qui trahit
    l'absence de libelle — il n'y a pas d'autre marqueur.
    / Django's default verbose_name is the field name with underscores turned
      into spaces; that equality is the only tell.
    """
    trouves = set()
    for modele, admin in staff_admin_site._registry.items():
        for nom in _champs_cites(admin):
            if not isinstance(nom, str) or "__" in nom:
                continue
            try:
                champ = modele._meta.get_field(nom)
            except Exception:
                continue  # methode @display, annotation, propriete
            if not hasattr(champ, "verbose_name"):
                continue
            if str(champ.verbose_name) == nom.replace("_", " "):
                trouves.add((modele._meta.app_label, modele.__name__, nom))
    return trouves


@pytest.mark.django_db
def test_aucun_champ_affiche_n_est_sans_libelle():
    """
    Le garde-fou. Un champ ajoute demain a une `list_display` sans
    `verbose_name` fera echouer ce test, au lieu de s'afficher en anglais
    pendant des mois sans que personne ne le voie.
    / A field added tomorrow without a label fails here instead of silently
      showing in English for months.
    """
    manquants = _sans_libelle() - TOLERES
    assert not manquants, (
        "Ces champs s'afficheront avec un libelle anglais fabrique par Django :\n"
        + "\n".join(f"  {a}.{m}.{c}" for a, m, c in sorted(manquants))
        + '\n\nAjouter verbose_name=_("...") sur le champ du modele (cela genere '
        "une migration AlterField), ou l'inscrire dans TOLERES si c'est un "
        "identifiant technique."
    )


@pytest.mark.django_db
def test_la_liste_des_toleres_ne_contient_pas_de_champ_deja_corrige():
    """
    Une tolerance qui ne sert plus est un mensonge dans le code : elle laisse
    croire qu'un champ est volontairement sans libelle alors qu'il en a un.
    / A stale allowlist entry is a lie left in the code.
    """
    inutiles = TOLERES - _sans_libelle()
    assert not inutiles, (
        f"Ces champs ont desormais un libelle : les retirer de TOLERES. {sorted(inutiles)}"
    )


@pytest.mark.django_db
def test_les_champs_de_la_page_parametres_sont_libelles():
    """
    Cas nomme, parce qu'il etait le plus visible : les cinq champs de
    `Configuration` s'affichaient en anglais dans les onglets de la page
    Parametres, juste apres leur refonte.
    / Named case: five Configuration fields showed in English in the Settings
      tabs, right after they were restyled.
    """
    from BaseBillet.models import Configuration

    for nom in ("email", "site_web", "language", "currency_code", "postal_address"):
        champ = Configuration._meta.get_field(nom)
        assert str(champ.verbose_name) != nom.replace("_", " "), nom
