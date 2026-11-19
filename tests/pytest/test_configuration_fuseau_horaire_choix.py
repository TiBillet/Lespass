"""
La liste des fuseaux horaires vit dans le formulaire de l'admin, jamais dans le modele.
/ The timezone list lives in the admin form, never in the model.

LOCALISATION : tests/pytest/test_configuration_fuseau_horaire_choix.py

CE QUE CES TESTS PROTEGENT
--------------------------

La liste des fuseaux vient de `zoneinfo.available_timezones()`. Elle depend des
fichiers de fuseaux installes sur la machine (paquet Debian `tzdata`, paquet pip
`tzdata`). Deux machines n'ont donc pas toujours la meme liste.

Si cette liste est posee en `choices=` sur le champ du modele, Django la recopie
dans la migration. Sur une machine dont la liste differe, `migrate` affiche alors
« Your models in app(s): 'BaseBillet' have changes that are not yet reflected in
a migration ». Le champ du modele ne doit donc porter AUCUN `choices`.

Le menu deroulant et la validation restent assures par le formulaire de l'admin,
qui calcule la liste a chaque affichage.
/ The model field must carry no choices (they would be copied into migrations and
  differ between machines). The admin form builds the list at display time.
"""

import zoneinfo

import pytest
from django import forms

from Administration.admin.site import staff_admin_site
from BaseBillet.models import Configuration


def _champ_du_formulaire_admin_pour_le_fuseau():
    """
    Construit le champ de formulaire que l'admin de Configuration utilise.
    / Builds the form field used by the Configuration admin.
    """
    admin_de_la_configuration = staff_admin_site._registry[Configuration]
    champ_du_modele = Configuration._meta.get_field("fuseau_horaire")
    return admin_de_la_configuration.formfield_for_dbfield(champ_du_modele, request=None)


def test_le_champ_du_modele_ne_porte_aucune_liste_de_fuseaux():
    """
    Le champ du modele n'a pas de `choices` : la migration ne fige aucune liste.
    / The model field has no choices: migrations freeze no list.
    """
    champ_du_modele = Configuration._meta.get_field("fuseau_horaire")

    assert not champ_du_modele.choices


def test_le_formulaire_admin_propose_les_fuseaux_de_la_machine():
    """
    Le menu deroulant de l'admin liste les fuseaux connus de la machine, tries.
    / The admin dropdown lists the machine's timezones, sorted.
    """
    champ_du_formulaire = _champ_du_formulaire_admin_pour_le_fuseau()

    fuseaux_attendus = sorted(zoneinfo.available_timezones())
    fuseaux_proposes = [valeur for valeur, _libelle in champ_du_formulaire.choices]

    assert isinstance(champ_du_formulaire, forms.ChoiceField)
    assert fuseaux_proposes == fuseaux_attendus


def test_le_formulaire_admin_accepte_un_fuseau_connu():
    """
    Un vrai fuseau, comme « Indian/Reunion », est accepte.
    / A real timezone is accepted.
    """
    champ_du_formulaire = _champ_du_formulaire_admin_pour_le_fuseau()

    assert champ_du_formulaire.clean("Indian/Reunion") == "Indian/Reunion"


def test_le_formulaire_admin_refuse_un_fuseau_inconnu():
    """
    Un nom qui n'est pas un fuseau est refuse : la validation n'a pas disparu
    avec les `choices` du modele.
    / An unknown name is rejected: validation did not vanish with the model choices.
    """
    champ_du_formulaire = _champ_du_formulaire_admin_pour_le_fuseau()

    with pytest.raises(forms.ValidationError):
        champ_du_formulaire.clean("Planete/Mars")
