# Section "Administration" multi-tenant sur "Mon compte"

**Date :** 2026-04-01
**Statut :** Validé

## Objectif

Sur la page "Mon compte", remplacer le bouton unique "Panneau d'administration"
par une section séparée listant explicitement chaque tenant que l'utilisateur
peut administrer, avec le nom du tenant et son adresse (domaine).

Un utilisateur admin de plusieurs tenants doit voir tous ses accès admin,
**même s'il n'est pas admin du tenant courant**.

## Règles d'affichage

| Cas | Comportement |
|-----|-------------|
| User admin de 1+ tenants (pas superuser) | Section "Administration" visible, un bouton rouge par tenant dans `client_admin` |
| Superuser | Un seul bouton rouge pointant vers `/admin/` du tenant courant |
| User admin d'aucun tenant (pas superuser) | Section entièrement masquée |

## Layout

### Position dans la page (template reunion)

```
┌──────────────────────────────────────┐
│  Grille 2 colonnes existante :       │
│  [Ma tirelire]     [Mes abonnements] │
│  [Mes réservations][Ma carte Pass]   │
│  [Mes paramètres]                    │
├──────────────────────────────────────┤
│  Titre : "Administration" (rouge)    │
│  Grille 2 colonnes :                 │
│  [Festival Raffinerie]  [Café asso]  │
│   raffinerie.tibillet…   cafe.tibi…  │
├──────────────────────────────────────┤
│  [Se déconnecter]                    │
└──────────────────────────────────────┘
```

### Chaque bouton admin

- Même format que les boutons existants : `btn btn-lg btn-outline-danger w-100`
- Icône : `bi-key-fill fs-1`
- Ligne 1 : **nom du tenant** (`client.name`)
- Ligne 2 : **domaine principal** (`client.domains.first().domain`), style plus petit et gris
- Lien : `https://<domaine>/admin/` avec `target="_blank"`

### Template HTMX (wizard)

Dans le header du wizard (`my_account.html`), remplacer le lien unique
"Administration" par une liste de liens vers chaque tenant administrable,
avec le même format (nom + domaine).

## Données

### Contexte template

Ajouter dans le contexte de `MyAccount.list()` une variable `tenants_admin`
contenant les tenants administrables avec leurs domaines préchargés.

**Logique :**

```python
if user.is_superuser:
    # Un seul bouton : le tenant courant
    tenants_admin = [connection.tenant]  # prefetch domains
elif user.client_admin.exists():
    tenants_admin = user.client_admin.prefetch_related('domains').all()
else:
    tenants_admin = []
```

### Modèles utilisés (existants, aucune migration)

- `AuthBillet.TibilletUser.client_admin` — M2M vers `Customers.Client`
- `Customers.Client.name` — nom du tenant
- `Customers.Domain.domain` — domaine du tenant (via `DomainMixin`, FK inverse `domains`)

## Fichiers concernés

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/views.py` | Ajouter `tenants_admin` dans le contexte de `MyAccount.list()` |
| `BaseBillet/templates/reunion/views/account/index.html` | Remplacer le bouton admin unique par la section "Administration" |
| `BaseBillet/templates/htmx/views/my_account/my_account.html` | Adapter le lien admin dans le header du wizard |
| `BaseBillet/templatetags/tibitags.py` | Le filtre `can_admin` reste en place (utilisé ailleurs ?), rien à supprimer |

## Hors périmètre

- Aucun changement de libellé ou d'icône sur les boutons existants
- Aucune migration de base de données
- Aucun changement sur le filtre `can_admin` (peut servir ailleurs)
- Pas de gestion de permissions granulaires (initiate_payment, create_event, etc.)
