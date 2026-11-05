# Les mails ont un Reply-To vers l'adresse du lieu, sans en-tête de désabonnement / Emails get a Reply-To to the venue address, no unsubscribe header

**Date :** 2026-11-04
**Migration :** Non

## Resume / Summary
**Quoi / What :** Tous les mails envoyés par `CeleryMailerClass` depuis un lieu portent l'en-tête `Reply-To: <Configuration.email>`. Le `From` ne change pas. Pas de Reply-To dans le schéma public ni quand le lieu n'a pas d'email. Un appelant peut imposer une autre adresse avec `reply_to=` : le formulaire de contact met le visiteur en Reply-To, pour que le lieu lui réponde.
/ Every email sent by `CeleryMailerClass` from a venue carries `Reply-To: <Configuration.email>`. The `From` is unchanged. No Reply-To in the public schema or when the venue has no email. A caller can force another address with `reply_to=`: the contact form sets the visitor.

**Adresse visible / Visible address :** `Configuration.email` (l'email public du lieu, modifiable dans sa configuration) apparaît désormais dans chaque mail reçu par les clients.
/ `Configuration.email` is now visible to every customer receiving an email.

**Désabonnement / Unsubscribe :** l'en-tête `List-Unsubscribe` est retiré de tous les mails envoyés par `CeleryMailerClass`. Ils sont tous transactionnels (billets, achats, réservations, bénévolat, codes de connexion) : on ne s'en désabonne pas, et Gmail ou Yahoo affichaient un lien « Se désabonner » inutile.
/ The `List-Unsubscribe` header is removed: every email sent by `CeleryMailerClass` is transactional.

**Logo TiBillet en PNG / TiBillet logo as PNG :** `seo/static/assets/logo-couleur.png` (même dessin que le SVG, 218×96). Gmail n'affiche pas les SVG. Il sert d'en-tête aux mails envoyés depuis le schéma public (voir CHANGELOG/2026-11-05-mails-nouvelle-base-da-v7.md).
/ PNG TiBillet logo, used as the header of public-schema emails.

**Pourquoi / Why :** Quand une personne répond à un mail (billet, adhésion, bénévolat…), sa réponse arrive au lieu, et plus à l'adresse d'expédition (souvent noreply). SPF, DKIM et DMARC contrôlent le `From` : ils ne sont pas touchés. Limite connue : SpamAssassin ajoute 0,1 point quand le Reply-To est une messagerie gratuite (gmail, orange, free…) et le `From` non, et 2 points si le corps contient une autre adresse de messagerie gratuite (seuil par défaut : 5).
/ Replies reach the venue instead of the noreply sender. SPF/DKIM/DMARC check the From and are unaffected. Known limit: SpamAssassin FREEMAIL_FORGED_REPLYTO (+0.1) and FREEMAIL_REPLYTO (+2.0).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | `CeleryMailerClass(reply_to=…)`, `adresse_de_reponse()` + `reply_to=` dans `send()` |
| `BaseBillet/tasks.py` | `contact_mailer` : Reply-To = le visiteur |
| `seo/static/assets/logo-couleur.png` | Nouveau : le logo TiBillet en PNG |
| `BaseBillet/tasks.py` | En-tête `List-Unsubscribe` retiré |
| `tests/pytest/test_mail_reply_to.py` | 5 tests : adresse du lieu, lieu sans email, schéma public, pas d'en-tête de désabonnement, formulaire de contact |

---

## Comment tester (a la main) / Manual test
### Test 1 — scénario nominal
1. Dans l'admin du lieu, vérifier que la Configuration a un email (ex. `contact@lieu.test`).
2. Déclencher un mail (inscription bénévole, achat d'un billet…).
3. Dans Mailpit (port 8025), ouvrir le mail, onglet « Headers » : `Reply-To: contact@lieu.test`, `From` inchangé.
4. Cliquer « Répondre » : le destinataire proposé est l'adresse du lieu.

### Test 2 — cas limites
- Lieu sans email dans sa Configuration : pas d'en-tête `Reply-To`.
- Mail envoyé depuis le schéma public : pas d'en-tête `Reply-To`.
- Formulaire de contact du site : le mail reçu par le lieu a `Reply-To: <adresse du visiteur>`.

### Déploiement / Deployment
- `collectstatic` obligatoire : sans lui, `logo-couleur.png` répond 404 et l'en-tête des mails du schéma public perd son logo.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_mail_reply_to.py"`
