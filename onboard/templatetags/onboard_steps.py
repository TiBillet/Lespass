"""
Templatetags pour le wizard d'onboarding.
/ Templatetags for the onboarding wizard.

LOCALISATION: onboard/templatetags/onboard_steps.py

Expose `is_step_done` et `is_step_current` pour simplifier les comparaisons
de steps dans `progress_panel.html`. Avant ce refactor, le template
ecrivait des chaines `step == 'X' or step == 'Y' or ...` dans chaque <li>,
peu lisibles et fragiles a maintenir (oublier une etape decale tout).

/ Provides `is_step_done` and `is_step_current` to simplify step
comparisons in `progress_panel.html`. Before this refactor, the template
had brittle `step == 'X' or step == 'Y' or ...` chains in every <li>,
hard to read and easy to break (forgetting a step skews everything).
"""

from django import template

register = template.Library()


# Ordre canonique des etapes du wizard. Source unique de verite : si on
# ajoute / retire / renomme une step, on touche cette liste seulement.
# Doit rester aligne sur `MetaBillet.WaitingConfiguration.STEP_*` et sur
# la table `onboard.views.STEP_TO_URL_NAME`.
# / Canonical wizard step order. Single source of truth: changing the
# step list happens here only. Must stay aligned with
# `WaitingConfiguration.STEP_*` and `onboard.views.STEP_TO_URL_NAME`.
STEP_ORDER = [
    "identity",
    "verify",
    "venue",
    "place",
    "descriptions",
    "events",
    "launch",
]


@register.simple_tag
def is_step_done(current_step, target_step):
    """
    Renvoie True si `target_step` a deja ete franchie : elle est AVANT
    `current_step` dans l'ordre du wizard. Renvoie False sinon (etape
    courante, future, ou argument inconnu — defense : on ne casse pas la
    page si quelqu'un passe `step="bogus"`).

    / Returns True if `target_step` is BEFORE `current_step` in the wizard
    order. Returns False otherwise (current step, future step, or unknown
    arguments — defensive).

    Exemple en template / Template usage:
        {% load onboard_steps %}
        {% is_step_done step 'identity' as identity_done %}
        {% if identity_done %} <a href="...">...</a> {% endif %}
    """
    # Defense : argument inconnu -> on renvoie False plutot que de lever.
    # / Defensive: unknown argument -> return False instead of raising.
    if current_step not in STEP_ORDER:
        return False
    if target_step not in STEP_ORDER:
        return False
    return STEP_ORDER.index(current_step) > STEP_ORDER.index(target_step)


@register.simple_tag
def is_step_current(current_step, target_step):
    """
    Sucre syntaxique pour `current_step == target_step`. Permet d'eviter
    de melanger `{% if step == "X" %}` et `{% is_step_done %}` dans le
    meme template — plus homogene a la lecture.

    / Sugar for `current_step == target_step`. Keeps the template
    homogeneous (no mix of `{% if step == "X" %}` and `{% is_step_done %}`).
    """
    return current_step == target_step
