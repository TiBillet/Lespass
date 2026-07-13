# Module Newsletter : activation, modale de contact, sidebar

## Ce qui a été fait

Le module **Newsletter** apparaît maintenant dans le dashboard :

> **Newsletter** — *Evènements, rappels d'adhésions, résumé de vos activités, pilotez votre
> newsletter avec TiBillet !*

**Désactivé par défaut**, et **activable par un superadmin seulement**. La raison : le module
pilote une instance **Ghost** auto-hébergée, qui doit d'abord être installée et **dimensionnée**
(la charge serveur dépend du volume de mails envoyés).

Un gestionnaire ordinaire qui clique ne reçoit **pas un refus sec**. Une modale l'invite à
contacter l'équipe TiBillet — c'est une porte d'entrée, pas un mur.

Quand le module est actif, un groupe **« Newsletter »** apparaît dans la sidebar, et la config
**Ghost y déménage** (elle était perdue dans « Outils externes », entre Webhook et Brevo).

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | `Configuration.module_newsletter` (défaut False) |
| `BaseBillet/migrations/0221_…` | **Migration à appliquer** |
| `Administration/admin/dashboard.py` | Carte du module · groupe sidebar · Ghost déplacé |
| `Administration/admin_tenant.py` | Blocage superadmin (modale **et** POST) |
| `…/templates/admin/dashboard_module_modal_contact.html` | **Nouveau** |
| `tests/pytest/test_module_newsletter_activation.py` | **Nouveau** — 7 tests |

---

## ⚠️ Migration à appliquer

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

Le module est à **False** sur tous les tenants : aucun n'est impacté tant qu'un superadmin ne
l'active pas.

---

## Tests à réaliser

### Test 1 : superadmin (le chemin nominal)

1. Se connecter en **superadmin** (`admin@admin.com`), aller sur `/admin/`
2. **Attendu :** la carte **« Newsletter »**, toggle **désactivé**, avec le texte ci-dessus
3. **Attendu :** **aucun** groupe « Newsletter » dans la sidebar
4. Cliquer le toggle → **modale de confirmation normale** (« Voulez-vous vraiment activer
   "Newsletter" ? »)
5. Confirmer. ⏳ *La page peut geler quelques secondes : `Configuration.save()` appelle l'API
   Stripe.*
6. **Attendu après rechargement :**
   - le toggle est **activé**
   - un groupe **« Newsletter »** est apparu dans la sidebar
   - il contient **« Serveur Ghost »** (icône enveloppe)
   - **« Ghost » a disparu** de « Outils externes »
7. Désactiver le module → le groupe « Newsletter » **disparaît** de la sidebar

### Test 2 : gestionnaire ordinaire (le chemin qui compte)

> Un « gestionnaire ordinaire » = un utilisateur **admin du tenant** (M2M `client_admin`) mais
> **pas superadmin**. Attention : `is_staff` ne suffit pas — sans le `client_admin`, il n'a même
> pas accès à l'admin.

1. Se connecter avec un tel utilisateur, aller sur `/admin/`
2. Cliquer le toggle **« Newsletter »**
3. **Attendu : la modale de CONTACT**, et non celle de confirmation :
   - *« L'équipe de TiBillet peut vous aider à installer votre serveur de newsletter Ghost. »*
   - *« Contactez-les pour leur indiquer combien de mails vous comptez envoyer, afin de calculer
     la charge serveur. »*
   - trois liens : **contact@tibillet.re**, **Salon Matrix**, **Discord**
   - un seul bouton : **« J'ai compris »**
4. **Attendu : AUCUN bouton d'activation.** Le module reste désactivé.

### Test 3 : la sécurité (à ne pas sauter)

La modale n'est que de l'affichage — une requête forgée la contournerait. Le POST doit refuser
tout seul.

Connecté en **gestionnaire ordinaire**, dans la console du navigateur :

```javascript
fetch('/admin/BaseBillet/configuration/module-toggle/module_newsletter/', {
  method: 'POST',
  headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
}).then(r => console.log('HTTP', r.status));
```

**Attendu : `HTTP 403`**, et le module **toujours désactivé** en base.

---

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_module_newsletter_activation.py -v
```

**7 tests.** Ils **créent** un gestionnaire ordinaire (la base de dev n'en contient aucun) et le
**suppriment** ensuite ; ils restaurent aussi l'état initial du module.

Deux pièges y sont documentés, et ils ont coûté du temps :
- **`force_login` et les requêtes doivent être dans le `tenant_context`** — sinon la session
  n'est pas retrouvée, et l'admin répond `302 /admin/login/`. Un échec trompeur : ça ressemble à
  un refus de permission, c'est un problème de schéma.
- **Ne jamais utiliser `Configuration.objects.update()`** pour poser l'état du module :
  django-solo **met `get_solo()` en cache**. L'`update()` écrit en base mais laisse le cache
  périmé — la vue lit alors l'**ancienne** valeur et bascule dans le mauvais sens.

Suite complète : **340 tests**.

---

## Chaînes traduisibles

~8 chaînes ajoutées (msgid en français) : le nom et la description du module, les textes et les
libellés de la modale de contact, le titre du groupe de sidebar.

**Le workflow i18n est à lancer par le mainteneur.**
