import fs from "node:fs"
import { exec } from "child_process"
import { env } from '../env.js'

const root = process.cwd(), confFileName = 'configLaboutik.json'


export function readfile(path) {
  // console.log('-> readfile, path =', path)
  try {
    const fileExists = fs.existsSync(path)
    if (fileExists) {
      const data = fs.readFileSync(path, 'utf8')
      return data
    } else {
      throw new Error("File doesn't exist.")
    }
  } catch (error) {
    console.log(`Read file ${path} :`, error.message)
    return null
  }
}

function readJson(path) {
  // console.log('-> readJson, path =', path)
  try {
    const fileExists = fs.existsSync(path)
    if (fileExists) {
      const data = fs.readFileSync(path, 'utf8')
      const obj = JSON.parse(data)
      return obj
    } else {
      throw new Error("The file doesn't exist")
    }
  } catch (error) {
    console.log("readJson -", error.message)
    return null
  }
}

/**
 * 
 * @param {string} path 
 * @param {string} data 
 * @returns {object} - object.stasus = true|false , object.msg ...success|...error
 */
export function writeJson(path, data) {
  if (typeof(data) !== 'string') {
    data = JSON.stringify(data)
  }
  try {
    const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
    fs.writeFileSync(path, content, 'utf8')
    return { status: true, msg: 'Update/create file - backup success.' }
  } catch (error) {
    console.log("sauvegarde fichier de configuration,", error.message)
    return { status: false, msg: 'Update/create file - backup error.' }
  }
}

export function startBrowser(url) {
  // desktop
  const start = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start' : 'xdg-open'
  exec(start + ' ' + url, (error, stdout, stderr) => {
    console.log(stdout)
    if (error) {
      throw error;
    }
  })
}

export async function testNetworkStatus(timeout = 3000) {
  const urls = [
    "https://clients3.google.com/generate_204",
    "https://1.1.1.1",
    "https://api.github.com"
  ]
  const promises = urls.map(async (url) => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeout)
    try {
      const response = await fetch(url, {
        method: "GET",
        signal: controller.signal,
        cache: "no-store"
      })
      clearTimeout(timer)
      return response
    } catch (error) {
      // console.log('-> testNetworkOk - fetch', error)
      return null
    }
  })
  const responses = await Promise.all(promises);

  if (responses.filter(item => item !== null).length >= 1) {
    return 'available'
  }
  return 'disable'
}

/**
 * Retour le fichier de configuration si il existe, sinon env
 * @returns {object|null}
 */
export function readConfigFile() {
  try {
  let configFile
  const configFromFile = readJson(root + '/' + confFileName)
  // console.log('-> readConfigFile - configFromFile =', configFromFile)

  if (configFromFile !== null) {
    configFile = configFromFile
  } else {
    configFile = env
    configFile['version'] = env.version
    // création du fichier de configuration
    const result = writeJson(root + '/' + confFileName, env)
    if(result.status === false) {
      throw new Error(result.msg)
    }
  }
  return configFile    
  } catch (error) {
    console.log('readConfigFile,',error)
    return null
  }
}


export function writeConfigFile(content) {
  console.log('-> writeConfigFile, content =', content)
  return writeJson(root + '/' + confFileName, content)
}
