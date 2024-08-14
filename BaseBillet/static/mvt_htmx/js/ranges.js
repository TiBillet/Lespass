stepEvalRange = 'unknown'
window.ranges = []

function valider () {
  console.log('-> ranges =', JSON.stringify(ranges, null, 2))
  renderRanges()
}

// delete all tempo-* class
function deleteTempoClass () {
  document.querySelectorAll('.agenda-day').forEach(element => {
    element.classList.remove('tempo-end-range')
    element.classList.remove('tempo-start-range')
    element.classList.remove('tempo-element-range')
  })
}

// delete all range class
function deleteRangeClass () {
  document.querySelectorAll('.agenda-day').forEach(element => {
    element.classList.remove('end-range')
    element.classList.remove('start-range')
    element.classList.remove('element-range')
  })
}

function renderOver (range) {
  deleteTempoClass()
  // update tempo-* class
  document.querySelectorAll('.agenda-day').forEach(element => {
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

function renderRanges () {
  deleteTempoClass()
  deleteRangeClass()
  // update range class
  for (let r = 0; r < ranges.length; r++) {
    const range = ranges[r]
    document.querySelectorAll('.agenda-day').forEach(element => {
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

function removeRangeFromRanges (range) {
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

function removeRangeByTime (evt) {
  evt.preventDefault()
  evt.stopPropagation()
  const element = evt.target
  const time = parseInt(element.getAttribute('data-time'))
  for (let i = 0; i < ranges.length; i++) {
    const range = ranges[i]
    if (time >= range.start && time <= range.end) {
      removeRangeFromRanges(range)
      renderRanges()
      break
    }
  }

}

function pushRange (currentRange) {
  // console.log('-> pushRange, currentRange =', currentRange);
  // identique
  let startRangeIn = { state: false, index: null }
  let endRangeIn = { state: false, index: null }
  let inRange = { state: false, index: null }
  let neighbors = []

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

  // neighbor from left
  for (let i = 0; i < ranges.length; i++) {
    const iRange = ranges[i]
    const startNewRange = new Date(currentRange.start)
    const leftNeighbor = startNewRange.getDate() - 1
    if (leftNeighbor === new Date(iRange.end).getDate()) {
      console.log('vous avez un voisin à gauche')
      neighbors.push({ state: 'left', index: i })
      break
    }
  }

  // neighbor from right
  for (let i = 0; i < ranges.length; i++) {
    const iRange = ranges[i]
    const endNewRange = new Date(currentRange.end)
    const rightNeighbor = endNewRange.getDate() + 1
    if (rightNeighbor === new Date(iRange.start).getDate()) {
      console.log('vous avez un voisin à doite')
      neighbors.push({ state: 'right', index: i })
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

  // merge two ranges linked
  if (startRangeIn.state === true && endRangeIn.state === true && inRange.state === false) {
    const newRange = { start: ranges[startRangeIn.index].start, end: ranges[endRangeIn.index].end }
    const firstRange = ranges[startRangeIn.index]
    const secondRange = ranges[endRangeIn.index]
    removeRangeFromRanges(firstRange)
    removeRangeFromRanges(secondRange)
    ranges.push(newRange)
  }

  // merge ranges contiguous
  if (neighbors.length === 1 && neighbors[0].state === 'left') {
    ranges[neighbors[0].index].end = currentRange.start
  }
  if (neighbors.length === 1 && neighbors[0].state === 'right') {
    ranges[neighbors[0].index].start = currentRange.end
  }
  if (neighbors.length === 2) {
    const cpLeft = JSON.parse(JSON.stringify(ranges[neighbors[0].index]))
    const cpRight = JSON.parse(JSON.stringify(ranges[neighbors[1].index]))
    removeRangeFromRanges(cpLeft)
    removeRangeFromRanges(cpRight)
    ranges.push({ start: cpLeft.start, end: cpRight.end })
  }

  // console.log('startRangeIn =', JSON.stringify(startRangeIn, null, 2))
  // console.log('endRangeIn =', JSON.stringify(endRangeIn, null, 2))
  // console.log('inRange =', JSON.stringify(inRange, null, 2))

  if (neighbors.length === 0 && startRangeIn.state === false && endRangeIn.state === false && inRange.state === false) {
    ranges.push(currentRange)
  }
  renderRanges()
}

function initRange() {
	// start range
	document.addEventListener('pointerdown', evt => {
		evt.preventDefault()
		evt.stopPropagation()
		const element = evt.target
		const dataTime = element.getAttribute('data-time')
		if (dataTime === null) {
			return
		}
		const time = parseInt(dataTime)
		currentRangeStart = time
		stepEvalRange = 'start'
	})

	// over
	document.addEventListener('pointerover', evt => {
		evt.preventDefault()
		evt.stopPropagation()
		const element = evt.target
		const dataTime = element.getAttribute('data-time')
    console.log('dataTime =', dataTime, '  --  stepEvalRange =', stepEvalRange)
		if (stepEvalRange === 'start' && dataTime !== null) {
			const time = parseInt(dataTime)
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
	document.addEventListener('pointerup', evt => {
		evt.preventDefault()
		evt.stopPropagation()
		const element = evt.target
		const dataTime = element.getAttribute('data-time')
		if (stepEvalRange === 'start' && dataTime !== null) {
			stepEvalRange = 'end'
			const time = parseInt(element.getAttribute('data-time'))
			let currentRange
			if (currentRangeStart < time) {
				currentRange = { start: currentRangeStart, end: time, direction: 'plus' }
			} else {
				currentRange = { start: time, end: currentRangeStart, direction: 'moins' }
			}
			pushRange(currentRange)
		}
		if (stepEvalRange === 'start' && dataTime === null) {
			stepEvalRange = 'unknown'
			deleteTempoClass()
		}

	})

	// delete range
	document.addEventListener('dblclick', removeRangeByTime)

	// method "valider"
	document.querySelector('#valider').addEventListener('click', valider)
}