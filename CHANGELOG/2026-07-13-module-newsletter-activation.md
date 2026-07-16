# Module Newsletter : activation ouverte à tous, mention du serveur Ghost

**Date :** 2026-07-13
**Migration :** Non

## Ce qui a été fait

Le module **Newsletter** s'active désormais **comme les autres modules**, depuis le dashboard,
par **n'importe quel gestionnaire** du lieu (admin du tenant). Le verrou « superadmin seulement »
est supprimé :

- plus de modale « contactez-nous » à la place de la confirmation ;
- plus de refus `403` sur le POST de bascule.

À la place, la **contrainte « il faut un serveur Ghost »** est simplement **rappelée**, à deux
endroits, avec une invitation à contacter l'équipe TiBillet :

1. **Sur la carte du dashboard** (description du module) :
   > *…pilotez votre newsletter avec TiBillet ! Il vous faut un serveur Ghost pour piloter vos
   > newsletters : l'équipe de TiBillet peut vous en héberger un, contactez-nous !*

2. **Sur la page de configuration Ghost** (`/admin/BaseBillet/ghostconfig/`), en tête de la
   section « 1. La connexion à votre serveur Ghost » :
   > *Il vous faut un serveur Ghost pour piloter vos newsletters. L'équipe de TiBillet peut vous
   > en héberger un : contactez-nous à contact@tibillet.re !*

### Modifications
| Fichier | Changement |
|---|---|
| `Administration/admin/dashboard.py` | Retrait du flag `superadmin_seulement` · mention ajoutée à la description |
| `Administration/admin_tenant.py` | Retrait des deux branches `superadmin_seulement` (modale **et** POST) |
| `Administration/templates/admin/ghost/panneau_newsletter.html` | Mention d'hébergement en section 1 |
| `…/templates/admin/dashboard_module_modal_contact.html` | **Supprimé** (modale de contact inutile) |
| `tests/pytest/test_module_newsletter_activation.py` | Tests réécrits (5 tests) |

---

## Tests à réaliser

### Test 1 : un gestionnaire ordinaire peut activer le module

> Un « gestionnaire ordinaire » = un utilisateur **admin du tenant** (M2M `client_admin`) mais
> **pas superadmin**.

1. Se connecter avec un tel utilisateur, aller sur `/admin/`
2. **Attendu :** la carte **« Newsletter »**, toggle désactivé, avec la mention « Il vous faut un
   serveur Ghost… contactez-nous ! »
3. Cliquer le toggle → **modale de confirmation normale** (« Voulez-vous vraiment activer
   "Newsletter" ? »), **et non** une modale de contact
4. Confirmer. ⏳ *La page peut geler quelques secondes : `Configuration.save()` appelle l'API
   Stripe.*
5. **Attendu après rechargement :**
   - le toggle est **activé**
   - un groupe **« Newsletter »** est apparu dans la sidebar
   - il contient **« Serveur Ghost »** (icône enveloppe)
6. Désactiver le module → le groupe « Newsletter » **disparaît** de la sidebar

### Test 2 : la mention sur la page GhostConfig

1. Module actif, aller sur `/admin/BaseBillet/ghostconfig/`
2. **Attendu :** en tête de la section « 1. La connexion à votre serveur Ghost », la phrase
   *« Il vous faut un serveur Ghost… l'équipe de TiBillet peut vous en héberger un : contactez-nous
   à contact@tibillet.re ! »*, avec le lien mailto cliquable.

---

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_module_newsletter_activation.py -v
```

**5 tests.** Ils **créent** un gestionnaire ordinaire (la base de dev n'en contient aucun) et le
**suppriment** ensuite ; ils restaurent aussi l'état initial du module.

Deux pièges y sont documentés :
- **`force_login` et les requêtes doivent être dans le `tenant_context`** — sinon la session n'est
  pas retrouvée, et l'admin répond `302 /admin/login/`.
- **Ne jamais utiliser `Configuration.objects.update()`** pour poser l'état du module : django-solo
  **met `get_solo()` en cache** ; l'`update()` laisse le cache périmé.

---

## Chaînes traduisibles

Textes modifiés/ajoutés (msgid en français) : la description du module (dashboard) et la mention
d'hébergement du panneau Ghost. Des chaînes de l'ancienne modale de contact (template supprimé) ne
sont plus référencées.

**Le workflow i18n est à lancer par le mainteneur.**
