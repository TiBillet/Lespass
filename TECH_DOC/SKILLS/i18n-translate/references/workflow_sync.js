export const meta = {
  name: 'i18n-sync-fr-en',
  description: 'Corrige fuzzy + fuites de langue dans locale/fr et locale/en (TiBillet)',
  phases: [{ title: 'Translate', detail: 'lots Sonnet, lecture tranche / ecriture fragment' }],
}

// args attendu : { workdir, starts: [0,45,90,...] }
// Defensif : selon l'appel, args peut arriver en objet OU en chaine JSON.
// / Defensive: args may arrive as an object or as a JSON string.
const A = typeof args === 'string' ? JSON.parse(args) : args
const workdir = A.workdir
const starts = A.starts

const SCHEMA = {
  type: 'object',
  properties: {
    start: { type: 'integer' },
    written: { type: 'integer', description: 'nb d items ecrits dans le fragment' },
  },
  required: ['start', 'written'],
  additionalProperties: false,
}

function prompt(start) {
  return `Tu corriges les traductions i18n du projet TiBillet (Django, multi-tenant).

## REGLE DURE — A LIRE EN PREMIER
N'execute JAMAIS de commande git (add/commit/checkout/stash/reset/restore/clean).
Tu ne modifies AUCUN fichier .po. Tu ecris UNIQUEMENT ton fragment de sortie.

## Donnees
Lis le fichier JSON: ${workdir}/in_${start}.json  (un tableau d'items).
Chaque item :
- i   : index
- id  : le msgid (texte source)
- ctx : msgctxt eventuel (souvent vide)
- src : langue SOURCE du msgid -> "fr", "en" ou "amb"
- nfr : true s'il faut produire la chaine FRANCAISE (champ "fr")
- nen : true s'il faut produire la chaine ANGLAISE (champ "en")
- bad_fr / bad_en : ancienne traduction FAUSSE (fuzzy) a IGNORER et remplacer

## Ce que tu produis, par item -> { "i":<index>, "fr":<...|null>, "en":<...|null> }
Champ "fr" (si nfr==true, sinon null) :
- src=="fr"  : le msgid est DEJA francais -> "fr" = le msgid VERBATIM.
- src=="en"/"amb" : traduis le msgid en FRANCAIS clair et naturel (UI logiciel, FALC).
Champ "en" (si nen==true, sinon null) :
- src=="en"  : le msgid est DEJA anglais -> "en" = le msgid VERBATIM.
- src=="fr"/"amb" : traduis le msgid en ANGLAIS clair et naturel (software UI).

## REGLES ABSOLUES (sinon le logiciel casse)
1. PRESERVE EXACTEMENT placeholders et balises, sans les traduire ni les renommer :
   %(name)s, %s, %d, %% | {name}, {0}, {obj.attr} | <a href="...">, <br>, </a> | \\n, &nbsp;
   Le NOM interne d'un placeholder ne se traduit JAMAIS.
2. Garde les espaces de bord et la ponctuation de bord identiques au msgid.
3. Calque la forme (pas de point/guillemet ajoute ou retire abusivement).
4. Ignore totalement bad_fr/bad_en (fuzzy errones).
5. Si src=="amb", choisis la langue la plus plausible d'apres le sens.

## Sortie
Ecris ${workdir}/out_${start}.json : un tableau JSON STRICT (UTF-8, pas de BOM,
pas de texte autour) : [ {"i":..,"fr":..,"en":..}, ... ] pour TOUS les items de ta tranche.
Puis renvoie {start:${start}, written:<nb ecrits>}.`
}

const results = await pipeline(
  starts,
  (s) => agent(prompt(s), { label: `sync:${s}`, phase: 'Translate', model: 'sonnet', schema: SCHEMA })
)

const ok = results.filter(Boolean)
const written = ok.reduce((n, r) => n + (r.written || 0), 0)
log(`${ok.length}/${starts.length} lots OK, ${written} items ecrits`)
return { lots: starts.length, ok: ok.length, written }
