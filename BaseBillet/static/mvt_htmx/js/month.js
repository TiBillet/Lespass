function getDataMonth (month, year) {
  let daysBefore = null, lastDayDateMontBefore = null
  if (month === 0) {
    lastDayDateMontBefore = new Date((year - 1), 0, 0)
  } else {
    lastDayDateMontBefore = new Date(year, month, 0)
  }
  daysBefore = lastDayDateMontBefore.getDate()
  const firstDayDate = new Date(year, month, 1)
  const lastDayDate = new Date(year, month + 1, 0)
  const days = lastDayDate.getDate()
  let weekDay = firstDayDate.getDay()
  if (weekDay === 0) {
    weekDay = 6
  } else {
    weekDay -= 1
  }
  return { weekDay, daysBefore, days, month, year }
}

// infos jour
// Dim Lun Mar Mer Jeu Ven Sam
//  0   1   2   3   4   5   6

function showMonth (month, year) {
  const weekDayTab = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
  let fragHtml = '<div class="agenda-month-container d-flex flex-column">'
  // mois
  const monthName = new Date(year, month).toLocaleString('fr-FR', { month: 'long' })
  fragHtml += '<div class="agenda-month d-flex flex-row justify-content-center">' + monthName + '</div>'
  // légende des jours
  fragHtml += '<div class="d-flex flex-row">'
  weekDayTab.forEach(day => {
    fragHtml += '<div class="agenda-day-size">' + day + '</div>'
  })
  fragHtml += '</div>'
  let monthTotal = []
  const data = getDataMonth(month, year)
  // console.log('data =', data);

  // jours hors mois "avant"
  for (let j = data.daysBefore - (data.weekDay - 1); j <= data.daysBefore; j++) {
    // console.log('dBefore =', j);
    monthTotal.push({ disable: true })
  }

  // jours du mois
  for (let j = 1; j <= data.days; j++) {
    // console.log('dMonth =', j);
    monthTotal.push({ disable: false, month, dayNumber: j, dayDate: new Date(year, month, j).getTime() })
  }

  // jour de semaine du dernier jour du mois
  // console.log('month =', month, '  --  data.days =', data.days);
  let lastDayOfMonth = new Date(year, month, data.days).getDay()
  let reste = 7 - lastDayOfMonth
  if (lastDayOfMonth === 0) {
    lastDayOfMonth = 6
  } else {
    lastDayOfMonth -= 1
  }
  // jour de semaine appartenant au prochaint mois
  if (lastDayOfMonth !== 6) {
    for (let j = 1; j <= reste; j++) {
      // console.log('reste =', j);
      monthTotal.push({ disable: true })
    }
  }

  let cd = 1
  for (let i = 0; i < monthTotal.length; i++) {
    // début de semaine
    if (cd === 1) {
      fragHtml += '<div class="d-flex flex-row">'
    }
    let day = '00'
    if (monthTotal[i].dayNumber) {
      day = monthTotal[i].dayNumber
      if (day.toString().length === 1) {
        day = '0' + monthTotal[i].dayNumber.toString()
      }
    }
    let classPlus = 'agenda-day-disable ', attributes = ''
    if (monthTotal[i].disable === false) {
      classPlus = `agenda-day `
      attributes = `data-time="${monthTotal[i].dayDate}"`
    }
    fragHtml += `<div class="agenda-day-size ${classPlus}d-flex flex-row justify-content-center align-items-center m-0 p-0" ${attributes}>${day}</div>`
    if (cd === 7) {
      cd = 0
      fragHtml += '</div>'
    }
    cd++
  }

  fragHtml += '</div>'
  return fragHtml
}
