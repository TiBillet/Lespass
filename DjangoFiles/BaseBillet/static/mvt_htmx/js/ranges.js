let currentRangeStart = null, evalRange = false
let ranges = [], cssSelectorDay = ''

function valider() {
	console.log('-> ranges =', JSON.stringify(ranges, null, 2));
	renderRanges()
}

// delete all tempo-* class
function deleteTempoClass() {
	document.querySelectorAll(cssSelectorDay).forEach(element => {
		element.classList.remove('tempo-end-range')
		element.classList.remove('tempo-start-range')
		element.classList.remove('tempo-element-range')
	})
}

// delete all range class
function deleteRangeClass() {
	document.querySelectorAll(cssSelectorDay).forEach(element => {
		element.classList.remove('end-range')
		element.classList.remove('start-range')
		element.classList.remove('element-range')
	})
}


function renderOver(range) {
	deleteTempoClass()
	// update tempo-* class
	document.querySelectorAll(cssSelectorDay).forEach(element => {
		const time = parseInt(element.getAttribute('data-time'))
		// console.log('range =', range)
		if (time >= range.start && time <= range.end) {
			if (range.start === time) {
				element.classList.add('tempo-start-range')
			}
			if (range.end === time) {
				element.classList.add('tempo-end-range')
			}
			if (range.start !== time && range.end !== time) {
				element.classList.add('tempo-element-range')
			}
		}
	})
}

function renderRanges() {
	deleteTempoClass()
	deleteRangeClass()
	// update range class
	for (let r = 0; r < ranges.length; r++) {
		const range = ranges[r];
		document.querySelectorAll(cssSelectorDay).forEach(element => {
			const time = parseInt(element.getAttribute('data-time'))
			if (time >= range.start && time <= range.end) {
				if (range.start === time) {
					element.classList.add('start-range')
				}
				if (range.end === time) {
					element.classList.add('end-range')
				}
				if (range.start !== time && range.end !== time) {
					element.classList.add('element-range')
				}
			}
		})
	}
}

function removeRangeFromRanges(range) {
	if (range !== undefined) {
		let tempoRanges = []
		ranges.forEach(r => {
			if (r.start !== range.start && r.end !== range.end) {
				tempoRanges.push(r)
			}
		})
		ranges = tempoRanges
	}
}

function removeRangeByTime(evt) {
	evt.preventDefault()
	evt.stopPropagation()
	const element = evt.target
	const time = parseInt(element.getAttribute('data-time'))
	for (let i = 0; i < ranges.length; i++) {
		const range = ranges[i];
		if (time >= range.start && time <= range.end) {
			removeRangeFromRanges(range)
			renderRanges()
			break
		}
	}

}

function pushRange(currentRange) {
	// console.log('-> pushRange, currentRange =', currentRange);
	// identique
	let startRangeIn = { state: false, index: null }
	let endRangeIn = { state: false, index: null }
	let inRange = { state: false, index: null }

	// borne gauche de range incluse dans une plage 
	for (let i = 0; i < ranges.length; i++) {
		const iRange = ranges[i]
		if (currentRange.start >= iRange.start && currentRange.start <= iRange.end) {
			startRangeIn = { state: true, index: i }
			break
		}
	}

	// borne droite de range incluse dans une plage 
	for (let i = 0; i < ranges.length; i++) {
		const iRange = ranges[i]
		if (currentRange.end >= iRange.start && currentRange.end <= iRange.end) {
			endRangeIn = { state: true, index: i }
			break
		}
	}

	// fait partie d'un range
	for (let i = 0; i < ranges.length; i++) {
		const iRange = ranges[i]
		if (currentRange.start >= iRange.start && currentRange.end <= iRange.end) {
			inRange = { state: true, index: null }
			break
		}
	}

	// merge by left
	if (startRangeIn.state === false && endRangeIn.state === true && inRange.state === false) {
		ranges[endRangeIn.index].start = currentRange.start
	}

	// merge by right
	if (endRangeIn.state === false && startRangeIn.state === true && inRange.state === false) {
		ranges[startRangeIn.index].end = currentRange.end
	}


	// merge two ranges
	if (startRangeIn.state === true && endRangeIn.state === true && inRange.state === false) {
		const newRange = { start: ranges[startRangeIn.index].start, end: ranges[endRangeIn.index].end }
		const firstRange = ranges[startRangeIn.index]
		const secondRange = ranges[endRangeIn.index]
		removeRangeFromRanges(firstRange)
		removeRangeFromRanges(secondRange)
		ranges.push(newRange)
	}

	// console.log('startRangeIn =', JSON.stringify(startRangeIn, null, 2))
	// console.log('endRangeIn =', JSON.stringify(endRangeIn, null, 2))
	// console.log('inRange =', JSON.stringify(inRange, null, 2))

	if (startRangeIn.state === false && endRangeIn.state === false && inRange.state === false) {
		ranges.push(currentRange)
	}
	renderRanges()
}

function initRange(initCssSelectorDay) {
	cssSelectorDay = initCssSelectorDay

	// set methods to days
	document.querySelectorAll('.agenda-day').forEach(day => {

		// start range
		day.addEventListener('pointerdown', evt => {
			evt.preventDefault()
			evt.stopPropagation()
			const element = evt.target
			const time = parseInt(element.getAttribute('data-time'))
			currentRangeStart = time
			evalRange = true
		})

		// over
		day.addEventListener('pointerover', evt => {
			evt.preventDefault()
			evt.stopPropagation()
			if (evalRange === true) {
				const element = evt.target
				const time = parseInt(element.getAttribute('data-time'))

				let tempoRange
				if (currentRangeStart < time) {
					tempoRange = { start: currentRangeStart, end: time, direction: 'plus' }
				} else {
					tempoRange = { start: time, end: currentRangeStart, direction: 'moins' }
				}
				renderOver(tempoRange)
			}
		})

		// end range
		day.addEventListener('pointerup', evt => {
			evt.preventDefault()
			evt.stopPropagation()
			const element = evt.target
			const time = parseInt(element.getAttribute('data-time'))
			evalRange = false
			let currentRange = null
			if (currentRangeStart < time) {
				currentRange = { start: currentRangeStart, end: time, direction: 'plus' }
			} else {
				currentRange = { start: time, end: currentRangeStart, direction: 'moins' }
			}
			pushRange(currentRange)
		})

		day.addEventListener('dblclick', removeRangeByTime)
	})

	// method "valider"
	document.querySelector('#valider').addEventListener('click', valider)
}