export const meta = {
  name: 'i18n-newlang',
  description: 'Cree une nouvelle langue depuis zero (double ref FR+EN + glossaire fige)',
  phases: [{ title: 'Translate', detail: 'lots Sonnet, tranche -> fragment' }],
}

// args attendu : { workdir, starts, langName, langCode, glossary }
// glossary = texte du glossaire metier fige (identique pour tous les lots -> coherence).
// Defensif : args peut arriver en objet OU en chaine JSON.
// / Defensive: args may arrive as an object or as a JSON string.
const A = typeof args === 'string' ? JSON.parse(args) : args
const workdir = A.workdir
const starts = A.starts
const langName = A.langName
const langCode = A.langCode
const glossary = A.glossary || '(aucun glossaire fourni)'

const SCHEMA = {
  type: 'object',
  properties: {
    start: { type: 'integer' },
    written: { type: 'integer' },
  },
  required: ['start', 'written'],
  additionalProperties: false,
}

function prompt(start) {
  return `Tu traduis l'interface du logiciel TiBillet (Django, multi-tenant) vers le ${langName} (code ${langCode}).

## REGLE DURE — A LIRE EN PREMIER
N'execute JAMAIS de commande git (add/commit/checkout/stash/reset/restore/clean).
Tu ne modifies AUCUN fichier .po. Tu ecris UNIQUEMENT ton fragment de sortie.

## Donnees
Lis le fichier JSON: ${workdir}/in_${start}.json (un tableau d'items).
Chaque item :
- i   : index
- id  : le msgid brut (source, parfois FR parfois EN selon l'historique)
- ctx : msgctxt eventuel (sens d'usage si present)
- fr  : rendu FRANCAIS de reference
- en  : rendu ANGLAIS de reference
fr ET en te donnent le sens exact. Traduis le SENS vers le ${langName}, pas mot a mot.

## GLOSSAIRE METIER — A RESPECTER PARTOUT (coherence entre lots)
${glossary}
Noms propres a NE PAS traduire : TiBillet, LaBoutik, Fedow, Lespass, Code Commun,
Cascade, Stripe, SEPA, NFC, QR code, FEC, LNE.

## REGLES ABSOLUES (sinon le logiciel casse)
1. PRESERVE EXACTEMENT placeholders et balises, sans les traduire ni les renommer :
   %(name)s, %s, %d, %% | {name}, {0}, {obj.attr} | <a href="...">, <br>, </a> | \\n, &nbsp;
   Le NOM interne d'un placeholder ne se traduit JAMAIS.
2. Conserve les espaces de bord et la ponctuation de bord identiques a la source.
3. Calque la forme : un label court reste court, pas de point/guillemet ajoute.
4. Registre = UI logiciel, clair et simple (FALC). Vouvoiement si la langue le distingue.
5. Si "id" est uniquement un placeholder/URL/symbole, recopie-le tel quel.

## EXEMPLES (preservation)
- id "Solde : %(montant)s €"           -> "<trad> : %(montant)s €"
- id 'Voir <a href="/x">le détail</a>' -> '<trad> <a href="/x">...</a>'

## Sortie
Ecris ${workdir}/out_${start}.json : un tableau JSON STRICT (UTF-8, pas de BOM,
pas de texte autour) : [ {"i":<index>, "tr":"<traduction ${langCode}>"}, ... ]
un objet par item de ta tranche. Puis renvoie {start:${start}, written:<nb ecrits>}.`
}

const results = await pipeline(
  starts,
  (s) => agent(prompt(s), { label: `${langCode}:${s}`, phase: 'Translate', model: 'sonnet', schema: SCHEMA })
)

const ok = results.filter(Boolean)
const written = ok.reduce((n, r) => n + (r.written || 0), 0)
log(`${ok.length}/${starts.length} lots OK, ${written} items ecrits`)
return { lots: starts.length, ok: ok.length, written }
