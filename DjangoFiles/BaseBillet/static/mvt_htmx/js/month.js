export class Month {
  constructor(year, month) {
    this.month = month
    this.year = year
    this.start = new Date(this.year, this.month)
  }

  getName() {
    return this.start.toLocaleString('fr-fr', {month: 'long'})
  }

  static getDays(year,month) {
    let daysBefore = null, lastDayDateMontBefore = null
    if (month === 0) {
      lastDayDateMontBefore = new Date((year - 1), 0,0);
    } else {
      lastDayDateMontBefore = new Date(year, month ,0);
    }
    daysBefore = lastDayDateMontBefore.getDate()
    const firstDayDate = new Date(year, month, 1);
    const lastDayDate = new Date(year, month + 1, 0);
    const days = lastDayDate.getDate()
    let weekDay = firstDayDate.getDay()
    if (weekDay === 0 ) {
      weekDay = 6
    } else {
      weekDay -= 1
    }
    return {weekDay, daysBefore, days, month, year}
  }

  static getMonthsOfYear(year) {
    let months = []
    for (let i = 0; i < 12; i++) {
      months.push(new Month(year, i))
    }
    return months
  }
}