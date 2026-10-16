"""Hora peninsular: días naturales, sus límites y su duración real.

El corte de decisión y los días que se piden a las fuentes se definen en hora peninsular
(Europe/Madrid), que cambia de desfase dos veces al año. Las duraciones se calculan en UTC:
al restar dos ``datetime`` con la misma ``tzinfo``, Python resta horas de reloj e ignora el
cambio de hora, así que un día de 25 horas saldría de 24.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def local_midnight(day: date) -> datetime:
    """Medianoche peninsular de ``day``, con la zona horaria explícita.

    En España el cambio de hora es de madrugada (02:00 y 03:00), nunca a medianoche, así
    que la medianoche siempre existe y es única.
    """
    return datetime(day.year, day.month, day.day, tzinfo=MADRID)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Inicio y fin del día peninsular ``day``, como intervalo semiabierto ``[inicio, fin)``."""
    return local_midnight(day), local_midnight(day + timedelta(days=1))


def day_length(day: date) -> timedelta:
    """Duración real del día peninsular ``day``: 23, 24 o 25 horas."""
    start, end = day_bounds(day)
    return end.astimezone(UTC) - start.astimezone(UTC)


def intervals_in_day(day: date, step: timedelta) -> int:
    """Número de intervalos de ``step`` que caben en el día peninsular ``day``.

    Con cuartos de hora, 92, 96 o 100; con horas, 23, 24 o 25. Lanza ``ValueError`` si
    ``step`` no es positivo o no divide el día exactamente.
    """
    length = day_length(day)
    if step <= timedelta(0) or length % step:
        raise ValueError(f"{step} no divide el día {day} ({length})")
    return length // step


def target_day(captured_at: datetime) -> date:
    """Día D al que apunta una captura hecha en D-1: el día peninsular siguiente.

    Exige un ``datetime`` con zona horaria: uno ingenuo no dice qué día era en la península.
    """
    if captured_at.utcoffset() is None:
        raise ValueError("captured_at necesita zona horaria")
    return captured_at.astimezone(MADRID).date() + timedelta(days=1)


# Hora de decisión: la predicción del día D solo usa lo disponible antes de las 12:00
# peninsulares de D-1.
DECISION_TIME = time(12)


def decision_cutoff(day: date) -> datetime:
    """Corte de decisión del día ``day``: las 12:00 peninsulares de D-1.

    Solo cuenta lo disponible estrictamente antes de este instante. Los cambios de hora son
    de madrugada, así que las 12:00 siempre existen y son únicas.
    """
    return datetime.combine(day - timedelta(days=1), DECISION_TIME, tzinfo=MADRID)


def last_decided_day(now: datetime) -> date:
    """Último día D cuyo corte ya ha pasado en ``now``: mañana si son las 12:00 o más, y si no, hoy.

    Exige un ``datetime`` con zona horaria: uno ingenuo no dice qué hora era en la península.
    """
    if now.utcoffset() is None:
        raise ValueError("now necesita zona horaria")
    tomorrow = now.astimezone(MADRID).date() + timedelta(days=1)
    return tomorrow if now >= decision_cutoff(tomorrow) else tomorrow - timedelta(days=1)
