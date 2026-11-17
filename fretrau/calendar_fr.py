"""Jours livrables en France : week-ends et jours fériés exclus ; estimation de la date de livraison au plus tôt."""
import math
from datetime import date, timedelta

KM_PER_DAY = 600          # ~9 h de conduite (réglementation sociale européenne) à vitesse moyenne PL


def easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(year: int) -> set:
    e = easter(year)
    return {date(year, 1, 1), e + timedelta(days=1), date(year, 5, 1), date(year, 5, 8), e + timedelta(days=39),
            e + timedelta(days=50), date(year, 7, 14), date(year, 8, 15), date(year, 11, 1), date(year, 11, 11),
            date(year, 12, 25)}


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def next_business_day(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def earliest_delivery(pickup: date, km: float, urgent: bool = False) -> date:
    """Livraison au plus tôt : jours de route (600 km/jour) + 1 jour de manutention hors express, jour ouvré."""
    days = max(1, math.ceil(km / KM_PER_DAY)) - (1 if urgent else 0) + (0 if urgent else 1)
    return next_business_day(pickup + timedelta(days=max(0, days)))


def transit_days(km: float, urgent: bool = False) -> int:
    """Nombre de jours de transit annoncé (hors week-ends) : jours de route + 1 jour de manutention hors express."""
    return max(1, math.ceil(km / KM_PER_DAY)) + (0 if urgent else 1)
