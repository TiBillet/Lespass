### Tâche 6 : l'envoi, le gabarit, le marqueur, l'heure

**Fichiers :**
- Modifier : `Administration/recap_quotidien.py`
- Créer : `BaseBillet/templates/emails/recap_quotidien.html` (`{% extends 'emails/base.html' %}`, styles inline comme `emails/email_generique.html`)
- Test : classe `TestEnvoiDuRecap`

**Interfaces — consomme :** tâches 3-5. **Produit :**

```python
HEURE_D_ENVOI_DU_RECAP = 7

def preparer_le_recap_du_lieu(maintenant, borne_basse_des_z, borne_haute_des_z) -> dict | None:
    """Calcule le récap du lieu courant, sans rien écrire ni envoyer.
    Rend None s'il n'y a pas de contenu, sinon {"configuration", "date_de_la_veille",
    "rubriques", "clotures", "destinataires"}."""

def envoyer_le_recap(recap) -> bool:
    """Sans destinataire : logger.warning, False. Sinon les PDF des Z, puis le mail. True."""

def envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_de_la_veille, seuil_d_aujourd_hui) -> bool:
    """Appelée par comptabilite/tasks.py, dans le tenant_context du lieu.
    Rend True si un mail est parti."""
```

Les deux premières fonctions servent aussi à la démo du flush (tâche 8). Chacune travaille sous
`translation.override(config.language)` : les titres des rubriques (`preparer…`), le sujet `_()`
et `CeleryMailerClass(...)`, qui rend le gabarit dans son `__init__` (`envoyer…`).

L'ordre de `envoyer_le_recap_du_lieu_si_c_est_l_heure` est imposé (spec §4.1) :
1. `config = Configuration.get_solo()` ; `maintenant = timezone.now()` ; `maintenant_local = timezone.localtime(maintenant, config.get_tzinfo())`.
2. Sortir (`False`) si `maintenant_local.hour < HEURE_D_ENVOI_DU_RECAP`, ou si `maintenant < seuil_d_aujourd_hui`, ou si `Configuration.objects.filter(pk=config.pk, recap_quotidien_traite_le=maintenant_local.date()).exists()` (requête, **pas** `get_solo()`).
3. `recap = preparer_le_recap_du_lieu(maintenant, seuil_de_la_veille, seuil_d_aujourd_hui)`.
4. Poser le marqueur : `Configuration.objects.filter(pk=config.pk).update(recap_quotidien_traite_le=maintenant_local.date())` puis `Configuration.clear_cache()`. **Jamais `config.save()`** (il appelle Stripe).
5. `recap is None` → `False`.
6. `return envoyer_le_recap(recap)`. Les PDF (`generer_pdf_cloture(cloture)` → `(octets, nom_du_fichier, _type)`) ne sont fabriqués **que là**, une fois sûr qu'un mail part : WeasyPrint ne tourne pas pour rien. Puis `CeleryMailerClass(email=destinataires, title=…, template="emails/recap_quotidien.html", context=…, attached_files={nom: octets, …}).send()`.

Sujet : `f"[{config.organisation}] " + _("Le récap du %(date)s") % {"date": <veille au format JJ/MM/AAAA>}`.
Contexte du gabarit : `config`, `date_de_la_veille`, `rubriques`, `clotures` (liste de `dict` :
`numero_sequentiel`, `chiffre_affaires_ttc_en_euros` via `euros_a_la_francaise(total_general)`,
`nombre_transactions`, `fin_en_heure_du_lieu` en `%d/%m/%Y %H:%M`), `lien_admin`. Une rubrique :
titre, nombre (« dont N nouvelles » pour un stock), ses lignes, « et N autres » si besoin, bouton
vers `lien`. Chaînes du gabarit en `{% translate %}`, msgid en français.

Les tests remplacent `Administration.recap_quotidien.CeleryMailerClass` par un `MagicMock` et lisent ses arguments.

- [ ] **Étape 1 : tests qui échouent**
  - `test_a_6h10_rien_ne_part` ; `test_a_7h10_le_recap_part` ; `test_un_second_passage_a_8h10_n_envoie_rien`.
  - `test_fermeture_a_6h_rien_a_7h10_envoi_a_8h10` (`heure_de_fermeture=time(6, 0)` : seuil à 8 h).
  - `test_sans_contenu_aucun_pdf_n_est_genere` : `patch("Administration.recap_quotidien.generer_pdf_cloture")` jamais appelé.
  - `test_sans_contenu_pas_de_mail_mais_le_marqueur_est_pose`.
  - `test_sans_destinataire_pas_de_mail_un_avertissement_et_le_marqueur` (`assertLogs`).
  - `test_le_marqueur_est_pose_sans_configuration_save` : `patch.object(Configuration, "save")` → jamais appelé.
  - `test_une_erreur_de_calcul_ne_pose_pas_le_marqueur` : une rubrique qui lève → l'exception remonte, `recap_quotidien_traite_le` reste `None`.
  - `test_les_z_sont_en_piece_jointe` : `attached_files` contient les noms des PDF des deux J.
  - `test_le_mail_est_dans_la_langue_du_lieu` : `language="en"` → un `side_effect` sur le mock de `CeleryMailerClass` relève `translation.get_language()` **au moment de la construction** du mailer → `"en"` (la traduction EN des nouvelles chaînes n'est pas encore compilée : on teste la langue active, pas le texte).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichiers neufs). Contrôle visuel : rendre le gabarit avec un contexte de test et l'ouvrir dans un navigateur (fichier HTML dans le dossier scratchpad), clair et lisible.
- [ ] **Étape 5 : commit suggéré** : `feat(recap): envoi du récap du matin`.

---

