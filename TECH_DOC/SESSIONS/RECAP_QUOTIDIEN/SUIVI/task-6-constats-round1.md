1. (Important) Gabarit : « dont N nouvelle(s) hier » en blocktrans count, affiché seulement si nombre_de_nouveaux > 0 ; assertion du test mise à jour.
2. (Important) Test qui verrouille « marqueur posé AVANT l'envoi » : le mailer lève RuntimeError à l'envoi → l'exception remonte ET le marqueur vaut la date du jour.
3. (Mineur) « et 1 autre / et N autres » en blocktrans count.
4. (Mineur) test_sans_contenu_aucun_pdf_n_est_genere a un sens : stock sans nouveau + Z hors fenêtre → aucun mail, aucun PDF, marqueur posé.
5. (Mineur) envoyer_le_recap rend le résultat réel de send(), docstring juste.
6. (Mineur) domaine calculé une seule fois (dans le dict de preparer, relu par envoyer).
7. (Mineur) un seul msgid pour le bouton d'administration.
8. (Mineur) test d'échappement : `<b>x</b>` dans une ligne sort échappé dans le HTML rendu.
