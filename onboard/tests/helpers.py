"""
Helpers partages pour les tests onboard.
/ Shared helpers for onboard tests.

LOCALISATION: onboard/tests/helpers.py

Pourquoi pas un fixture conftest ? Les helpers `_create_wc_at_*`
(present dans test_step_place / descriptions / events / launch) sont
des fonctions module-level (pas des fixtures pytest). Pour eviter de
dupliquer la logique de login dans chaque helper, on l'expose ici en
fonction simple importable.

/ Why not a conftest fixture? The `_create_wc_at_*` helpers (in each
test_step_*.py) are module-level functions, not pytest fixtures. To
avoid duplicating the login logic in each helper, we expose it as a
plain importable function here.
"""

from django.contrib.auth import get_user_model


def login_test_user_for_email(client, email):
    """
    Cree (idempotent) un TibilletUser pour `email`, le marque
    `email_valid=True` + `is_active=True`, et le logue dans le
    `client` de test via `force_login`.

    Sert aux tests des steps post-verify (place / descriptions / events /
    launch) qui exigent maintenant `is_authenticated` (cf. enforce dans
    `_get_confirmed_wc_or_redirect` du onboard/views.py, refacto
    2026-05-15).

    / Idempotently creates a TibilletUser for `email`, marks it
    `email_valid=True` + `is_active=True`, and logs it in via
    `client.force_login`. Used by post-verify step tests that now
    require `is_authenticated` (cf. enforce in
    `_get_confirmed_wc_or_redirect`, 2026-05-15 refactor).

    :param client: instance `django.test.Client`.
    :param email: str — email du user (utilise comme username aussi).
    :return: instance TibilletUser.
    """
    User = get_user_model()
    # `username=email` : convention `AuthBillet.utils.get_or_create_user`.
    # / `username=email`: project convention.
    user, _created = User.objects.get_or_create(
        email=email,
        defaults={"username": email},
    )
    # Marque email_valid + is_active si pas deja. Sans is_active=True,
    # `force_login` raise "Inactive user cannot log in".
    # / Mark email_valid + is_active if not already (else force_login
    # raises "Inactive user cannot log in").
    update_fields = []
    if not user.email_valid:
        user.email_valid = True
        update_fields.append("email_valid")
    if not user.is_active:
        user.is_active = True
        update_fields.append("is_active")
    if update_fields:
        user.save(update_fields=update_fields)

    client.force_login(user)
    return user
