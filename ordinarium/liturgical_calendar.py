from datetime import date, timedelta


def easter_date(year):
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def advent_start(year):
    nov_27 = date(year, 11, 27)
    days_until_sunday = (6 - nov_27.weekday()) % 7
    return nov_27 + timedelta(days=days_until_sunday)


def resolve_season(service_date):
    if not service_date:
        return None

    easter = easter_date(service_date.year)
    ash_wednesday = easter - timedelta(days=46)
    palm_sunday = easter - timedelta(days=7)
    maundy_thursday = easter - timedelta(days=3)
    ascension = easter + timedelta(days=39)
    pentecost = easter + timedelta(days=49)
    trinity_sunday = easter + timedelta(days=56)

    advent = advent_start(service_date.year)
    christ_king = advent - timedelta(days=7)

    if service_date.month == 12 and service_date.day >= 25:
        return "Christmastide"
    if service_date.month == 1 and service_date.day <= 5:
        return "Christmastide"

    if service_date == christ_king:
        return "Christ the King"

    if advent <= service_date <= date(service_date.year, 12, 24):
        return "Advent"

    if date(service_date.year, 1, 6) <= service_date < ash_wednesday:
        return "Epiphanytide"

    if service_date == maundy_thursday:
        return "Maundy Thursday"

    if palm_sunday <= service_date < easter:
        return "Holy Week"

    if service_date == ascension:
        return "Ascension"

    if service_date == pentecost:
        return "Pentecost"

    if service_date == trinity_sunday:
        return "Trinity Sunday"

    if easter <= service_date < pentecost:
        return "Easter"

    if ash_wednesday <= service_date < palm_sunday:
        return "Lent"

    return "Ordinary Time"
