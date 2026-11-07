"""Beijing 04:00 game-day boundaries, independent of the host timezone."""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def local_now(now=None):
    if now is None:
        return datetime.now(BEIJING)
    if isinstance(now, (int, float)):
        return datetime.fromtimestamp(now, BEIJING)
    return now.replace(tzinfo=BEIJING) if now.tzinfo is None else now.astimezone(BEIJING)


def game_date(now=None):
    return (local_now(now) - timedelta(hours=4)).date()


def day_key(now=None):
    return game_date(now).isoformat()


def week_key(now=None):
    day = game_date(now)
    return (day - timedelta(days=day.weekday())).isoformat()


def day_bounds(now=None):
    day = game_date(now)
    start = datetime(day.year, day.month, day.day, 4, tzinfo=BEIJING)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())
