// import your language and add it to "lang" variable.

import { en } from './languages/languageEn.js'
import { fr } from './languages/languageFr.js'

const lang = { en, fr }
let local = localStorage.getItem("language")
const defaultLanguage = (language === '' || language === null) ? 'en' : language
if (local === null || local === '') {
  localStorage.setItem("language", defaultLanguage)
  local = defaultLanguage
}

export function getLanguages() {
  let arrayLanguages = []
  Object.keys(lang).forEach(function (key) {
    arrayLanguages.push({ language: key, infos: lang[key].names, locale: lang[key].locale })
  })
  return arrayLanguages
}

/**
 * retourne la traduction  dans le dom / return the translation in the DOM
 * @param {string} selector - css selecteur/selector: "#id", ".class", "body"
 */
export function translate(selector) {
  try {
    // traduire la portion d'un élement contenant des attributs "data-i8n"
    // console.log('-> translate, local =', local, '  --  selector =', selector)
    document.querySelector(selector).querySelectorAll('[data-i8n]').forEach(element => {
      const data = element.getAttribute('data-i8n').replace(/ /g, '').split(',')
      const index = data[0]
      let trad = lang[local].content[index]

      if (trad === undefined) {
        throw new Error(`Aucune traduction pour "${index}" / No translation for "${index}" .`)
      }

      // capitalize first letter
      if (data.includes('capitalize')) {
        trad = trad.charAt(0).toUpperCase() + trad.slice(1)
      }

      if (data.includes('uppercase')) {
        trad = trad.toUpperCase()
      }
      element.innerText = trad
    })
    //return lang[local].index
  } catch (error) {
    console.log('-> translate ', error.message)
    // console.log('-->', error)
  }
}

/**
 * retourne le text de la traduction / return the translation text
 * @param {string} index - index de traduction
 * @param {string} option - option de traduction : capitalize, uppercase
 * @param {string} method - fonction à appeler pour bypasser la traduction
 * @returns 
 */
export function getTranslate(index, option, method) {
  try {
    let trad
    // bypass by method
    if (method !== undefined) {
      trad = window[method](option)
    } else {
      trad = lang[local].content[index]
      // option existe
      if (option !== undefined && option !== null && typeof (option) === 'string') {

        if (option.includes('capitalize')) {
          trad = trad.charAt(0).toUpperCase() + trad.slice(1)
        }

        if (option.includes('uppercase')) {
          trad = trad.toUpperCase()
        }
      }
    }
    return trad
  } catch (error) {
    // console.log('-> getTranslate,', error)
    return ''
  }
}