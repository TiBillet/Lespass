"""
La classe de base des ModelAdmin du projet.
/ The project's base ModelAdmin class.

LOCALISATION : Administration/admin/base.py

POURQUOI CE FICHIER EXISTE
Le projet compte ~57 classes d'admin qui heritaient toutes directement du
`ModelAdmin` d'Unfold. Il n'y avait donc AUCUN endroit ou poser un
comportement commun : chaque besoin transverse aurait demande de toucher les
57 declarations.

On interpose une classe a nous. Les modules d'admin importent desormais
`ModelAdmin` d'ici plutot que d'`unfold.admin` — meme nom, meme usage, aucun
changement dans les classes elles-memes.
/ ~57 admin classes inherited straight from Unfold's ModelAdmin, leaving no
  place for shared behaviour. This class is that place.

CE QU'ON N'A PAS FAIT, ET POURQUOI
On pouvait surcharger `StaffAdminSite.register()` pour injecter le
comportement sur chaque classe enregistree : UNE seule edition au lieu de
quinze imports. C'est rejete — muter des classes tierces au moment de
l'enregistrement est le genre de magie que la regle du projet demande
d'eviter (« explicit, readable, no magic abstractions »), et le jour ou le
placeholder se comporterait bizarrement, personne ne saurait ou regarder.
/ Rejected: mutating classes at register() time is invisible magic.
"""

from django.contrib.admin.utils import label_for_field
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

# Au-dela, le placeholder est tronque par le CSS d'Unfold (champ en `lg:w-96`,
# classe `truncate`) : autant s'arreter nous-memes, proprement, sur trois
# libelles suivis de points de suspension.
# / Beyond this the CSS truncates it anyway; stop cleanly at three.
NOMBRE_DE_CHAMPS_AFFICHES = 3


def _libelle_du_champ_de_recherche(modele, chemin):
    """
    Le nom lisible d'une entree de `search_fields`.
    / The human label of one `search_fields` entry.

    LOCALISATION : Administration/admin/base.py

    Une entree de `search_fields` n'est pas un nom de champ : c'est une
    expression de recherche Django. Trois choses a demeler.

    1. LES PREFIXES `^`, `=`, `@` (« commence par », « egal a », « recherche
       plein texte »). Aucun n'est utilise dans le projet aujourd'hui, mais les
       afficher tels quels serait absurde le jour ou quelqu'un en met un.

    2. LES LOOKUPS LIES : `user__email`, et jusqu'a
       `pricesold__productsold__product__name` (trois niveaux). On suit la
       relation pour resoudre le VRAI champ terminal — « e-mail » plutot que
       « user email ».

    3. LES CHAMPS INTROUVABLES (annotations, proprietes) : on se rabat sur le
       dernier segment, embelli. Mieux vaut un libelle approximatif qu'une
       exception sur une page de liste.
    / Search entries carry lookup prefixes and relation paths; resolve the
      terminal field, and never raise on a page that must render.

    :param modele: la classe de modele de l'admin
    :param chemin: une entree de search_fields (ex. « user__email »)
    :return: un libelle lisible, ou None si rien d'exploitable
    """
    chemin = (chemin or "").lstrip("^=@")
    if not chemin:
        return None

    segments = chemin.split("__")
    modele_courant = modele

    # On descend la chaine des relations jusqu'a l'avant-dernier segment.
    # / Walk the relation chain down to the last but one segment.
    for segment in segments[:-1]:
        try:
            champ = modele_courant._meta.get_field(segment)
        except Exception:
            modele_courant = None
            break
        modele_lie = getattr(champ, "related_model", None)
        if modele_lie is None:
            modele_courant = None
            break
        modele_courant = modele_lie

    dernier = segments[-1]
    if modele_courant is not None:
        try:
            return str(label_for_field(dernier, modele_courant))
        except Exception:
            pass

    # Repli : le dernier segment, rendu lisible.
    # / Fallback: the last segment, made readable.
    return dernier.replace("_", " ")


class ModelAdmin(UnfoldModelAdmin):
    """
    Le ModelAdmin du projet. Voir l'en-tete du fichier.
    / The project's ModelAdmin. See the file header.
    """

    @property
    def search_help_text(self):
        """
        Dit SUR QUOI porte la recherche, dans le champ lui-meme.
        / Says what the search actually covers, inside the field itself.

        LOCALISATION : Administration/admin/base.py

        Unfold rend `search_help_text` COMME PLACEHOLDER du champ de recherche
        (unfold/templates/admin/search_form.html), avec un repli sur « Type to
        search ». C'est un detournement propre a Unfold : l'admin Django natif
        l'affiche en petit sous le champ. Resultat : il n'y a AUCUN gabarit a
        surcharger pour obtenir ce qu'on veut.
        / Unfold renders search_help_text as the input's placeholder, so no
          template override is needed.

        Cote Django, l'attribut est lu tel quel dans
        `get_changelist_instance()` — il n'existe pas de `get_search_help_text()`
        et aucun system check ne le valide. Une property suffit donc, et elle a
        acces a `self.search_fields`.

        Sur 82 classes d'admin, 55 ont un `search_fields` : l'information
        existait deja partout, elle n'etait simplement jamais montree.

        :return: le texte du placeholder, ou None pour laisser le repli d'Unfold
        """
        # Note : une sous-classe qui ecrit `search_help_text = _("...")` masque
        # naturellement cette property (attribut de classe prioritaire dans le
        # MRO). Il n'y a donc rien a prevoir pour respecter une valeur
        # explicite — Python s'en charge.
        # / A subclass setting the attribute shadows this property natively.
        champs = self.search_fields
        if not champs:
            # Sans search_fields, Unfold n'affiche meme pas la barre.
            # / Without search_fields Unfold hides the search bar entirely.
            return None

        # `search_fields` est tantot une liste, tantot un tuple selon les
        # classes du projet : on normalise avant de boucler.
        # / The project mixes lists and tuples.
        libelles = []
        for chemin in list(champs):
            libelle = _libelle_du_champ_de_recherche(self.model, chemin)
            if not libelle:
                continue
            libelle = libelle.lower()
            # Dedoublonnage en preservant l'ordre. Sur HumanUserAdmin,
            # `first_name` et `memberships__first_name` donnent tous deux
            # « prenom » : sans ceci le placeholder radoterait.
            # / Deduplicate, order preserved: two entries can share a label.
            if libelle not in libelles:
                libelles.append(libelle)

        if not libelles:
            return None

        retenus = libelles[:NOMBRE_DE_CHAMPS_AFFICHES]
        suite = "…" if len(libelles) > NOMBRE_DE_CHAMPS_AFFICHES else ""

        # str() explicite : la valeur part dans un attribut HTML, et le projet
        # s'est deja fait mordre par un proxy paresseux rendu tel quel
        # (Configuration.__str__ -> 500). / Explicit str(): lazy proxies have
        # already caused a 500 in this project.
        return str(
            _("Rechercher : %(champs)s") % {"champs": ", ".join(retenus) + suite}
        )
