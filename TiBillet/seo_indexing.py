"""
Helper pour decider si une reponse doit etre marquee `noindex, nofollow`.
/ Helper to decide if a response must be marked `noindex, nofollow`.

LOCALISATION : TiBillet/seo_indexing.py

Une reponse HTTP est marquee non-indexable quand AU MOINS UN flag
d'environnement est a "1" : DEBUG, TEST, DEMO.
Les instances de prod ont ces 3 flags a "0" dans leur .env.

/ A response is marked non-indexable when AT LEAST ONE env flag is
set to "1": DEBUG, TEST, DEMO.

Voir TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md pour la
justification de cette regle (et pour les regles ecartees, comme
la verification du host).
/ See TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md for the
rationale and discarded alternatives.

Utilise par :
- seo/views_common.py:robots_txt — pour servir Disallow: /
- BaseBillet/views_robots.py:robots_txt — meme logique cote tenant
- Le context processor noindex_context — pour exposer noindex_seo
  aux bases templates qui rendent un <meta name="robots">.
"""

import os


# Flags d'env qui declenchent le noindex : un seul a "1" suffit.
# `STRIPE_TEST` en est volontairement absent — il decrit le mode
# d'encaissement, pas l'environnement. Une prod publique peut encaisser en
# test tant que sa billetterie n'est pas ouverte.
# / One flag at "1" is enough. `STRIPE_TEST` is deliberately excluded: it
# describes the payment mode, not the environment.
_NOINDEX_FLAGS = ("DEBUG", "TEST", "DEMO")


def should_noindex():
    """
    Retourne True si la reponse doit etre marquee `noindex, nofollow`.
    / Returns True if the response must be marked `noindex, nofollow`.

    LOCALISATION : TiBillet/seo_indexing.py

    Lit directement os.environ : c'est uniforme pour les 4 flags, et
    ca permet aux tests de basculer les flags avec monkeypatch.setenv
    sans toucher a Django settings.
    / Reads os.environ directly: uniform for the 4 flags, and lets
    tests toggle flags via monkeypatch.setenv without touching
    Django settings.
    """
    for flag in _NOINDEX_FLAGS:
        if os.environ.get(flag) == "1":
            return True
    return False


def noindex_context(request):
    """
    Context processor Django : expose `noindex_seo: bool` a tous les
    templates qui heritent du base template.
    / Django context processor: exposes `noindex_seo: bool` to every
    template that extends the base template.

    LOCALISATION : TiBillet/seo_indexing.py

    A enregistrer dans settings.TEMPLATES[0]['OPTIONS']['context_processors'].
    Les templates l'utilisent ainsi :

        <meta name="robots"
              content="{% if noindex_seo %}noindex, nofollow{% else %}index, follow{% endif %}">

    Note : `request` est requis par la signature Django mais inutilise
    (la decision est globale a l'instance, pas par requete).
    / Note: `request` is required by Django's signature but unused
    (the decision is instance-wide, not per-request).
    """
    return {"noindex_seo": should_noindex()}
