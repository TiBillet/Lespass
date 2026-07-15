"""
discovery/admin.py — VOLONTAIREMENT VIDE.
/ discovery/admin.py — INTENTIONALLY EMPTY.

LOCALISATION : discovery/admin.py

Le PairingDevice n'est PAS dans l'admin, et c'est un choix.

Ce n'est pas un objet que le gestionnaire manipule : c'est un code PIN, une plomberie qui
ne vit que le temps de faire entrer un appareil. Il doit vivre dans le schema `public`
(l'appareil qui tape le code ne connait pas encore son lieu — il appelle une route publique,
et c'est le serveur qui lui apprend ou il atterrit), mais ca ne veut pas dire qu'il doit se
montrer.

TOUT SE PILOTE DEPUIS « Terminaux materiels > Terminaux » :

- creer un terminal fabrique son code PIN (Administration/admin/laboutik.py, save_model) ;
- le code s'affiche dans la colonne « Etat » du terminal ;
- l'action « Generer un nouveau code PIN » en redonne un (appareil perdu, vole ou grille) ;
- l'action « Revoquer le terminal » lui coupe son acces.

Une tireuse, elle, se cree depuis son propre ecran : elle fabrique son terminal, qui
fabrique son code (controlvanne/signals.py).

/ PairingDevice is deliberately NOT in the admin: it is a PIN, plumbing that only lives long
enough to let a device in. Everything is driven from the Terminal admin.
"""
