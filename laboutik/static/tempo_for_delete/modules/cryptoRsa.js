/**
 * @typedef {Object} keyPair
 * @property {string} privateKey - The private key
 * @property {string} publicKey - The publicKey key
 */

/**
 * Convert ArrayBuffer to string
 * @param {ArrayBuffer} buf 
 * @returns {string}
 */
function ab2str(buf) {
  return String.fromCharCode.apply(null, new Uint8Array(buf))
}

/**
 * Convert a string into an ArrayBuffer
 * @param {string} str 
 * @returns {ArrayBuffer}
 */
function str2ab(str) {
  const buf = new ArrayBuffer(str.length)
  const bufView = new Uint8Array(buf)
  for (let i = 0, strLen = str.length; i < strLen; i++) {
    bufView[i] = str.charCodeAt(i)
  }
  return buf
}


/**
 * Export the given key and write it into the "exported-key" space.
 * @param {object} key
 * @param {string} keyType - 'private' or 'public'
 * @returns {string}
 */
async function exportCryptoKeyToPem(key, keyType) {
  let retour = '', format = 'spki'
  if (keyType === 'private') {
    format = 'pkcs8'
  }

  const exported = await window.crypto.subtle.exportKey(format, key)
  const exportedAsString = ab2str(exported)
  const exportedAsBase64 = window.btoa(exportedAsString)

  if (keyType === 'private') {
    retour = `-----BEGIN PRIVATE KEY-----\n${exportedAsBase64}\n-----END PRIVATE KEY-----`
  } else {
    retour = `-----BEGIN PUBLIC KEY-----\n${exportedAsBase64}\n-----END PUBLIC KEY-----`
  }
  return retour
}

/**
 * Test private and public key pem
 * @param {keyPair} keys 
 * @returns {boolean}
 */
async function testPemKeys(keys) {
  const msg = "Ceci est un message de test."
  const cryptMsg = await encryptMessage(keys.publicKey, msg)
  const decryptMsg = await decryptMessage(keys.privateKey, cryptMsg)
  return msg === decryptMsg ? true : false
}

/**
 * generate key pair
 * @returns {keyPair} - keyPair or null
 */
export async function generatePemKeys() {
  const keyPair = await window.crypto.subtle.generateKey(
    {
      name: "RSA-OAEP",
      modulusLength: 2048,
      publicExponent: new Uint8Array([0x01, 0x00, 0x01]),
      hash: { name: "SHA-256" }
    },
    true,
    ["encrypt", "decrypt"]
  )
  const privateKey = await exportCryptoKeyToPem(keyPair.privateKey, 'private')
  const publicKey = await exportCryptoKeyToPem(keyPair.publicKey, 'public')

  const keys = { privateKey, publicKey }
  const resulTest = await testPemKeys(keys)
  if (resulTest) {
    return keys
  } else {
    console.log('-> generatePemKeys, error when generating keys.')
    return null
  }

}

/**
 * Import key pem to Cryptokey
 * @param {string} pem - key pem 
 * @param {Array} usages - ["sign"] or ["verify"] or ["encrypt"] or ["decrypt"]
 * @param {string} algo - RSA-PSS for sign/verify  or 'RSA-OAEP' for encrypt/decrypt
 * @returns 
 */
async function importKey(pem, usages, algo) {
  let pemHeader = '', pemFooter = '', format = 'spki'

  if (pem.includes('-----BEGIN PRIVATE KEY-----')) {
    format = 'pkcs8'
    pemHeader = '-----BEGIN PRIVATE KEY-----'
    pemFooter = '-----END PRIVATE KEY-----'
  } else {
    pemHeader = '-----BEGIN PUBLIC KEY-----'
    pemFooter = '-----END PUBLIC KEY-----'
  }

  const pemContents = pem.substring(pemHeader.length, pem.length - pemFooter.length)
  // base64 decode the string to get the binary data
  const binaryDerString = window.atob(pemContents)
  // convert from a binary string to an ArrayBufferpublicKey
  const binaryDer = str2ab(binaryDerString)
  try {
    return await window.crypto.subtle.importKey(
      format,
      binaryDer,
      {
        name: algo,
        // Consider using a 4096-bit key for systems that require long-term security
        modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: "SHA-256",
      },
      true,
      usages
    )

  } catch (error) {
    console.log('-> importKey, error,', error)
  }
}


/**
 * 
 * @param {keyPair} keyPair 
 * @param {string} message - message to sign
 * @returns {string}
 */
export async function signMessage(keyPair, message) {
  const cryptoKey = await importKey(keyPair.privateKey, ["sign"], 'RSA-PSS')
  const enc = new TextEncoder()
  const messageEncoding = enc.encode(message)

  const signature = await window.crypto.subtle.sign(
    {
      name: "RSA-PSS",
      saltLength: 128,
    },
    cryptoKey,
    messageEncoding
  )

  // console.log('brute =', signature)
  // console.log("new Uint8Array(signature) =", new Uint8Array(signature))

  const ascii = new Uint8Array(signature)
  const b64encoded = btoa(String.fromCharCode.apply(null, ascii))
  // console.log('-> signMessage, b64encoded =', b64encoded)
  return { str: ab2str(signature), b64encoded }
}

/**
 * checks a message based on a signature
 * @param {string} publicKey - public key pem 
 * @param {string} signature 
 * @param {string} message - message to check
 * @returns { boolean}
 */
export async function verifyMessage(publicKey, signature, message) {
  const cryptoKey = await importKey(publicKey, ["verify"], 'RSA-PSS')

  const enc = new TextEncoder()
  const messageEncoding = enc.encode(message)

  return await window.crypto.subtle.verify(
    {
      name: "RSA-PSS",
      saltLength: 128,
    },
    cryptoKey,
    str2ab(signature),
    messageEncoding
  )
}

/**
 * encrypt message
 * @param {string} publicKey - public key pem
 * @param {string} message - message to encrypt
 * @returns {string}
 */
export async function encryptMessage(publicKey, message) {
  const enc = new TextEncoder(), algo = 'RSA-OAEP'
  const cryptoKey = await importKey(publicKey, ["encrypt"], algo)
  const messageEncoding = enc.encode(message)
  const ciphertext = await window.crypto.subtle.encrypt(
    {
      name: algo
    },
    cryptoKey,
    messageEncoding
  )

  return ab2str(ciphertext)
}

/**
 * Decrypt message
 * @param {string} privateKey - private key pem
 * @param {string} message - ciphertext to decrypt
 * @returns {string}
 */
export async function decryptMessage(privateKey, message) {
  const dec = new TextDecoder(), algo = 'RSA-OAEP'
  const ciphertext = str2ab(message)
  const cryptoKey = await importKey(privateKey, ["decrypt"], algo)
  const decrypted = await window.crypto.subtle.decrypt(
    {
      name: algo
    },
    cryptoKey,
    ciphertext
  )
  return dec.decode(decrypted)
}