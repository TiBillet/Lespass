### Tâche 5 : les Z à joindre, « y a-t-il du contenu ? », les destinataires

**Fichiers :** modifier `Administration/recap_quotidien.py` ; test : classe `TestZContenuDestinataires`.

**Interfaces — produit :**

```python
def clotures_j_a_joindre(seuil_de_la_veille, seuil_d_aujourd_hui) -> list[ClotureCaisse]:
    """Les J dont seuil_de_la_veille < datetime_fin <= seuil_d_aujourd_hui, sauf celles qui
    finissent à ou avant la mise en service (comptabilite.tasks.mise_en_service_du_lieu()).
    Ordre : numero_sequentiel croissant."""

def le_recap_a_du_contenu(rubriques, clotures) -> bool:
    """Vrai s'il y a au moins un Z, ou une rubrique qui n'est pas un stock, ou un stock avec
    nombre_de_nouveaux > 0."""

def destinataires_du_recap(tenant, configuration) -> list[str]:
    """Admins du lieu (TibilletUser.client_admin=tenant), sinon configuration.email ; plus
    rapport_emails si rapport_periodicite == PERIODICITE_JOURNALIER. Minuscules, sans espaces,
    sans doublon, dans l'ordre d'apparition."""
```

- [ ] **Étape 1 : tests qui échouent** (J fabriquées par `generer_cloture_pour_tenant` après des
  ventes de `fabriquer_vente_encaissee`, motif `_vendre_des_jus_a` / `_cloturer_a` de
  `test_cloture_unique.py`) :
  - `test_le_z_manuel_d_hier_soir_et_le_filet_de_ce_matin_sont_joints` : vente lundi 20h, Z manuel lundi 23h ; vente lundi 23h30, filet mardi 4h → les deux J, dans l'ordre.
  - `test_un_z_de_ce_matin_10h_n_est_pas_joint` (il appartient au service d'aujourd'hui).
  - `test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe` (motif : `tests/pytest/test_reprise_clotures.py`).
  - `test_une_cloture_hebdomadaire_n_est_pas_jointe`.
  - `test_sans_rubrique_ni_z_il_n_y_a_pas_de_contenu` → `False`.
  - `test_un_stock_sans_nouveau_n_est_pas_du_contenu` → `False`.
  - `test_un_stock_avec_un_nouveau_est_du_contenu` → `True`.
  - `test_un_z_seul_est_du_contenu` → `True`.
  - `test_les_destinataires_sont_les_admins_du_lieu` ; `test_sans_admin_le_mail_du_lieu_sert_de_secours` ;
    `test_rapport_emails_ajoute_en_periodicite_journaliere` ; `test_rapport_emails_ignore_hors_periodicite_journaliere` ;
    `test_un_admin_aussi_dans_rapport_emails_n_est_compte_qu_une_fois` (« Admin@Example.org » et « admin@example.org »).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS**, ruff (fichier neuf).
- [ ] **Étape 5 : commit suggéré** : `feat(recap): tickets Z de la veille, contenu, destinataires`.

---

