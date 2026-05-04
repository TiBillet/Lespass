import fs from "node:fs"
import { exec } from "child_process"
import { env } from '../env.js'

const root = process.cwd(), confFileName = 'configLaboutik.json'

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
    console.log("Lecture fichier de configuration,", error.message)
    return null
  }
}

export function writeJson(path, data) {
  try {
    fs.writeFileSync(path, JSON.stringify(data, null, 2), 'utf8')
    return { status: true, msg: '' }
  } catch (error) {
    console.log("sauvegarde fichier de configuration,", error.message)
    return { status: false, msg: error.message }
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

export function readConfigFile() {
  // console.log('-> readConfigFile, headers =', headers)
  let configFile
  const configFromFile = readJson(root + '/' + confFileName)
  if (configFromFile !== null) {
    configFile = JSON.parse(configFromFile)
  } else {
    configFile = env
  }
  configFile['version'] = env.version
  return configFile
}
