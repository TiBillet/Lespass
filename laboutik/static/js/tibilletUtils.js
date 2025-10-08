let currentConfiguration = null
const logTypes = ['DANGER', 'WARNING', 'INFO']

function tibilletConvDjangoToJs(value) {
	const convList = {
		'True': true,
		'False': false,
		'None': null
	}
	let retour
	if (convList[value]) {
		return convList[value]
	} else {
		console.log(`tibilletConvDjandoToJs.js, variable "${value}" inconnue dans la list "convlist".`);
	}
}


function log({ tag, msg }) {
	const arg0 = arguments[0]
	const arg1 = arguments[1]
	const typeArgument0 = typeof (arg0)
	const typeArgument1 = typeof (arg1)
	// tag + msg
	if (typeArgument0 === 'object' && logTypes.includes(tag)) {
		console.log(msg)
	} else {
		let formatMsg = ''
		// string
		if (typeArgument0 === 'string') {
			formatMsg += arg0
		}
		// string + object
		if (typeArgument1 === 'object') {
			formatMsg += JSON.stringify(arg1)
		}
		// string + string
		if (typeArgument1 === 'string') {
			formatMsg += ' ' + arg1
		}
		console.log(formatMsg)
	}
}

function spinnerOff() {
	document.querySelector('#spinner-container').style.display = 'none'
}

function spinnerOn() {
	document.querySelector('#spinner-container').style.display = 'flex'
}

function bigToFloat(value) {
	try {
		return parseFloat(new Big(value).valueOf())
	} catch (error) {
		console.log('-> bigToFloat, ', error)
	}
}
/**
 * Send custum ecent
 * @param {string} name event name 
 * @param {string} selector css selector
 * @param {object} data 
 */
function sendEvent(name, selector, data) {
	try {
		const event = new CustomEvent(name, { detail: data })
		document.querySelector(selector).dispatchEvent(event)
		console.log(`-> sendEvent "${name}"`);
		
	} catch (error) {
		console.log('sendEvent,', error);

	}
}