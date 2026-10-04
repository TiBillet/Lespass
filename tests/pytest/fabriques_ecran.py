"""
Outils des tests qui lisent un écran : montants attendus écrits à la française, et
lecture d'un élément HTML par son `data-testid`.
/ Helpers for tests reading a screen: expected French amounts, and reading an HTML
element by its data-testid.

LOCALISATION : tests/pytest/fabriques_ecran.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_ecran import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

CE QUE PORTE CE MODULE
- `euros("15,50")` → « 15,50 € », avec les espaces insécables du format à la
  française (`comptabilite/presentation.py` `euros_a_la_francaise`) ;
- `moins_euros("2,00")` → « −2,00 € », avec le signe moins typographique ;
- `lire_l_element(page, testid)` → (texte, attributs) du premier élément qui porte ce
  `data-testid` ;
- `textes_des_elements(page, testid)` → le texte de CHAQUE élément qui porte ce
  `data-testid`, dans l'ordre, espaces (insécables comprises) ramenées à une seule ;
- `attributs_des_elements(page, testid)` → les attributs de chaque élément qui porte
  ce `data-testid` ;
- `LecteurDesLiens` → chaque lien `<a>` d'un morceau de page (adresse, `aria-label`,
  texte) ;
- `tableaux_de_la_page(page)` → chaque `<table>` de la page, dans l'ordre : une liste
  de rangées, chaque rangée la liste des textes de ses cellules (`<th>` et `<td>`) ;
- `texte_sans_espaces_en_trop(texte)` → le texte, espaces ramenées à une seule.
C'est le seul endroit des lecteurs HTML des tests d'écran.
Les montants attendus sont écrits par le test, jamais par le code testé.
/ The single place of the screen tests' HTML readers. Expected amounts are written
by the test, never by the tested code.
"""

import re
from html.parser import HTMLParser

# L'espace insécable et le signe moins typographique du format à la française.
# / The non-breaking space and the typographic minus of the French format.
ESPACE_INSECABLE = chr(0xA0)
SIGNE_MOINS = chr(0x2212)

# Les éléments HTML qui n'ont pas de balise de fin.
# / HTML elements without an end tag.
ELEMENTS_HTML_SANS_BALISE_DE_FIN = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "source", "track", "wbr",
}


def euros(nombre_en_texte):
    """
    Un montant attendu, écrit à la main : « 15,50 » → « 15,50 € » avec les espaces
    insécables. Le texte est écrit par le test, jamais par le code testé.
    / An expected amount, hand-written, with non-breaking spaces.
    """
    nombre_avec_espaces_insecables = nombre_en_texte.replace(" ", ESPACE_INSECABLE)
    return f"{nombre_avec_espaces_insecables}{ESPACE_INSECABLE}€"


def moins_euros(nombre_en_texte):
    """
    Un montant négatif attendu, écrit à la main : « 2,00 » → « −2,00 € » (signe moins
    typographique, espaces insécables).
    / An expected negative amount, hand-written.
    """
    return f"{SIGNE_MOINS}{euros(nombre_en_texte)}"


class LecteurDUnElementParSonTestid(HTMLParser):
    """
    Lit, dans une page HTML, le PREMIER élément qui porte `data-testid=<testid>` :
    ses attributs et tout le texte qu'il contient (ses enfants compris).
    / Reads the FIRST element carrying this data-testid: its attributes and its text.
    """

    def __init__(self, testid_cherche):
        super().__init__(convert_charrefs=True)
        self.testid_cherche = testid_cherche
        self.attributs_de_l_element = None
        self.profondeur_dans_l_element = 0
        self.morceaux_de_texte = []

    def handle_starttag(self, tag, attrs):
        # Déjà dans l'élément : on compte les balises ouvertes, pour savoir quand il
        # se ferme.
        # / Already inside: count open tags to know when the element closes.
        if self.profondeur_dans_l_element > 0:
            if tag not in ELEMENTS_HTML_SANS_BALISE_DE_FIN:
                self.profondeur_dans_l_element += 1
            return

        attributs = dict(attrs)
        element_deja_trouve = self.attributs_de_l_element is not None
        if element_deja_trouve:
            return
        if attributs.get("data-testid") != self.testid_cherche:
            return

        self.attributs_de_l_element = attributs
        if tag not in ELEMENTS_HTML_SANS_BALISE_DE_FIN:
            self.profondeur_dans_l_element = 1

    def handle_startendtag(self, tag, attrs):
        # Une balise auto-fermante (`<br/>`) n'ouvre rien : elle ne change pas la
        # profondeur. Elle peut être l'élément cherché.
        # / A self-closing tag opens nothing; it may be the searched element.
        if self.profondeur_dans_l_element > 0:
            return
        attributs = dict(attrs)
        element_deja_trouve = self.attributs_de_l_element is not None
        if not element_deja_trouve and attributs.get("data-testid") == self.testid_cherche:
            self.attributs_de_l_element = attributs

    def handle_endtag(self, tag):
        if self.profondeur_dans_l_element > 0:
            self.profondeur_dans_l_element -= 1

    def handle_data(self, data):
        if self.profondeur_dans_l_element > 0:
            self.morceaux_de_texte.append(data)


def lire_l_element(page_html, testid):
    """
    Le texte et les attributs de l'élément `data-testid=<testid>` de la page. Les
    blancs ordinaires (espaces, retours à la ligne) sont réduits à une espace ; les
    espaces insécables des montants sont gardées. Échoue si l'élément est absent.
    / The text and attributes of the element; plain whitespace collapsed, non-breaking
    spaces kept. Fails when the element is missing.

    :return: (texte, dictionnaire des attributs)
    """
    lecteur = LecteurDUnElementParSonTestid(testid)
    lecteur.feed(page_html)
    lecteur.close()
    if lecteur.attributs_de_l_element is None:
        raise AssertionError(f'Élément data-testid="{testid}" absent de la page.')
    texte_brut = "".join(lecteur.morceaux_de_texte)
    texte = re.sub(r"[ \t\r\n]+", " ", texte_brut).strip()
    return texte, lecteur.attributs_de_l_element


def texte_sans_espaces_en_trop(texte):
    """
    Le texte avec ses espaces (y compris insécables) ramenés à un seul.
    / The text with its spaces (non-breaking included) collapsed to one.
    """
    return " ".join(texte.replace(ESPACE_INSECABLE, " ").split())


class LecteurDesTextesParDataTestid(HTMLParser):
    """
    Lit une page HTML et garde le texte de chaque élément qui porte
    `data-testid="<data_testid>"` (texte des enfants compris, entités décodées).
    / Reads an HTML page and keeps the text of each element carrying that data-testid.
    """

    def __init__(self, data_testid):
        super().__init__(convert_charrefs=True)
        self.data_testid_cherche = data_testid
        self.profondeur_dans_l_element = 0
        self.texte_de_l_element_en_cours = []
        self.textes_des_elements = []

    def handle_starttag(self, balise, attributs):
        if balise in ELEMENTS_HTML_SANS_BALISE_DE_FIN:
            return
        if self.profondeur_dans_l_element > 0:
            self.profondeur_dans_l_element += 1
            return
        for nom_de_l_attribut, valeur_de_l_attribut in attributs:
            est_l_element_cherche = (
                nom_de_l_attribut == "data-testid"
                and valeur_de_l_attribut == self.data_testid_cherche
            )
            if est_l_element_cherche:
                self.profondeur_dans_l_element = 1
                self.texte_de_l_element_en_cours = []

    def handle_endtag(self, balise):
        if balise in ELEMENTS_HTML_SANS_BALISE_DE_FIN:
            return
        if self.profondeur_dans_l_element == 0:
            return
        self.profondeur_dans_l_element -= 1
        if self.profondeur_dans_l_element == 0:
            texte_complet = " ".join(self.texte_de_l_element_en_cours)
            self.textes_des_elements.append(texte_sans_espaces_en_trop(texte_complet))

    def handle_data(self, texte):
        if self.profondeur_dans_l_element > 0:
            self.texte_de_l_element_en_cours.append(texte)


def textes_des_elements(contenu_html, data_testid):
    """
    Le texte de chaque élément de la page qui porte ce `data-testid`, dans l'ordre.
    / The text of each page element carrying this data-testid, in order.
    """
    lecteur = LecteurDesTextesParDataTestid(data_testid)
    lecteur.feed(contenu_html)
    lecteur.close()
    return lecteur.textes_des_elements


class LecteurDesAttributsParDataTestid(HTMLParser):
    """
    Lit une page HTML et garde les attributs de chaque élément qui porte
    `data-testid="<data_testid>"`.
    / Reads an HTML page and keeps the attributes of each element with that testid.
    """

    def __init__(self, data_testid):
        super().__init__(convert_charrefs=True)
        self.data_testid_cherche = data_testid
        self.attributs_des_elements = []

    def handle_starttag(self, balise, attributs):
        attributs_de_l_element = dict(attributs)
        if attributs_de_l_element.get("data-testid") == self.data_testid_cherche:
            self.attributs_des_elements.append(attributs_de_l_element)


def attributs_des_elements(contenu_html, data_testid):
    """
    Les attributs de chaque élément de la page qui porte ce `data-testid`.
    / The attributes of each page element carrying this data-testid.
    """
    lecteur = LecteurDesAttributsParDataTestid(data_testid)
    lecteur.feed(contenu_html)
    lecteur.close()
    return lecteur.attributs_des_elements


class LecteurDesLiens(HTMLParser):
    """
    Lit une page HTML et garde chaque lien `<a>` : son adresse, son `aria-label` et
    son texte (entités décodées).
    / Reads an HTML page and keeps each link: its address, aria-label and text.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.liens = []
        self.lien_en_cours = None

    def handle_starttag(self, balise, attributs):
        if balise != "a":
            return
        attributs_du_lien = dict(attributs)
        self.lien_en_cours = {
            "href": attributs_du_lien.get("href", ""),
            "aria_label": attributs_du_lien.get("aria-label"),
            "texte": [],
        }

    def handle_endtag(self, balise):
        if balise != "a" or self.lien_en_cours is None:
            return
        self.lien_en_cours["texte"] = texte_sans_espaces_en_trop(
            " ".join(self.lien_en_cours["texte"])
        )
        self.liens.append(self.lien_en_cours)
        self.lien_en_cours = None

    def handle_data(self, texte):
        if self.lien_en_cours is not None:
            self.lien_en_cours["texte"].append(texte)


class LecteurDesTableaux(HTMLParser):
    """
    Lit une page HTML et garde chaque tableau `<table>` : ses rangées `<tr>`, et pour
    chaque rangée le texte de ses cellules `<th>` et `<td>` (entités décodées). Un
    tableau dans un tableau n'est pas lu à part.
    / Reads an HTML page and keeps each table: its rows, and each row's cell texts.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tableaux = []
        self.tableau_en_cours = None
        self.rangee_en_cours = None
        self.cellule_en_cours = None

    def handle_starttag(self, balise, attributs):
        if balise == "table":
            self.tableau_en_cours = []
            return
        if balise == "tr" and self.tableau_en_cours is not None:
            self.rangee_en_cours = []
            return
        cellule_qui_commence = balise in ("th", "td")
        if cellule_qui_commence and self.rangee_en_cours is not None:
            self.cellule_en_cours = []

    def handle_endtag(self, balise):
        cellule_qui_finit = balise in ("th", "td")
        if cellule_qui_finit and self.cellule_en_cours is not None:
            texte_de_la_cellule = texte_sans_espaces_en_trop(
                " ".join(self.cellule_en_cours)
            )
            self.rangee_en_cours.append(texte_de_la_cellule)
            self.cellule_en_cours = None
            return
        if balise == "tr" and self.rangee_en_cours is not None:
            self.tableau_en_cours.append(self.rangee_en_cours)
            self.rangee_en_cours = None
            return
        if balise == "table" and self.tableau_en_cours is not None:
            self.tableaux.append(self.tableau_en_cours)
            self.tableau_en_cours = None

    def handle_data(self, texte):
        if self.cellule_en_cours is not None:
            self.cellule_en_cours.append(texte)


def tableaux_de_la_page(contenu_html):
    """
    Chaque tableau de la page, dans l'ordre : une liste de rangées, chaque rangée la
    liste des textes de ses cellules (espaces ramenées à une seule).
    / Each table of the page, in order: a list of rows, each row its cell texts.
    """
    lecteur = LecteurDesTableaux()
    lecteur.feed(contenu_html)
    lecteur.close()
    return lecteur.tableaux
