"""
Le Terminal porte desormais son propre role (caisse, kiosque, tireuse).
/ The Terminal now carries its own role (POS, kiosk, tap).

Le role etait jusqu'ici porte par le compte du terminal (TermUser), donc il n'existait
qu'APRES l'appairage. Or le terminal est maintenant cree AVANT — c'est sa creation qui
fabrique le code PIN — et il doit savoir des ce moment-la quelle sorte d'appareil il attend :
c'est ce role qui decide quelle classe de cle d'API le claim delivrera.

Voir TECH_DOC/SESSIONS/IMPRESSION/.
"""

from django.db import connection, migrations, models


def reprendre_le_role_depuis_le_compte(apps, schema_editor):
    """
    Donne aux terminaux DEJA appaires le role de leur compte.
    / Gives already-paired terminals the role of their account.

    Sans cela, ils prendraient tous le defaut « caisse LaBoutik » — y compris les Raspberry
    Pi des tireuses, dont la sorte serait alors fausse dans l'admin.

    Le champ terminal_role du compte vit dans le schema public (TibilletUser) ; le Terminal
    dans le schema du lieu. La cle etrangere entre les deux existe deja, la lecture est donc
    directe.
    """
    # Les tables de laboutik n'existent pas dans le schema public.
    # / laboutik tables do not exist in the public schema.
    if connection.schema_name == 'public':
        return

    Terminal = apps.get_model('laboutik', 'Terminal')

    terminaux_deja_appaires = Terminal.objects.filter(
        term_user__isnull=False,
    ).select_related('term_user')

    nombre_de_terminaux_corriges = 0
    for terminal in terminaux_deja_appaires:
        role_du_compte = terminal.term_user.terminal_role
        if role_du_compte and role_du_compte != terminal.terminal_role:
            terminal.terminal_role = role_du_compte
            terminal.save(update_fields=['terminal_role'])
            nombre_de_terminaux_corriges += 1

    if nombre_de_terminaux_corriges:
        print(
            f"  -> [{connection.schema_name}] "
            f"{nombre_de_terminaux_corriges} terminal(aux) : role repris depuis le compte"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0002_stripelocation_remove_pointdevente_printer_terminal'),
    ]

    operations = [
        migrations.AddField(
            model_name='terminal',
            name='terminal_role',
            field=models.CharField(choices=[('LB', 'LaBoutik POS'), ('TI', 'Connected tap'), ('KI', 'Kiosk / self-service')], default='LB', help_text='Ce que cet appareil sait faire. Ne change plus une fois appaire.', max_length=2, verbose_name="Type d'appareil"),
        ),
        migrations.RunPython(
            reprendre_le_role_depuis_le_compte,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
