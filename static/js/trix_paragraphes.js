/**
 * Éditeur de texte de l'admin (Trix) : garde les paragraphes séparés
 * / Admin text editor (Trix): keeps paragraphs separate
 *
 * LOCALISATION : static/js/trix_paragraphes.js
 * Chargé sur toutes les pages de l'admin par UNFOLD["SCRIPTS"] (TiBillet/settings.py).
 *
 * Unfold ajoute à Trix un bloc « paragraphe » (<p>) sans l'option group: false
 * (unfold/contrib/forms/static/unfold/forms/js/trix.config.js). Sans elle, Trix
 * fusionne les <p> qui se suivent dès l'ouverture de la fiche :
 * <p>Un.</p><p>Deux.</p> devient <p>Un.Deux.</p>, puis est enregistré ainsi.
 * Les titres d'Unfold (h2, h3, h4) ont déjà group: false.
 *
 * FLUX : Trix émet « trix-before-initialize » pour chaque éditeur, avant de lire
 * le contenu. À ce moment, la config d'Unfold est chargée : on la corrige.
 * Sur une page sans éditeur, l'évènement n'arrive jamais.
 */
document.addEventListener("trix-before-initialize", function () {
    Trix.config.blockAttributes.p.group = false;
});
