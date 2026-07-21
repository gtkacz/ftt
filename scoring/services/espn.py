import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils import timezone

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ftt-live-scoring"}
_TIMEOUT_SECONDS = 20


def et_today() -> date:
	"""NBA schedule days are US Eastern calendar dates, not local ones."""  # noqa: DOC201
	return timezone.now().astimezone(ET).date()


def fetch_scoreboard(day: date | None = None) -> dict:
	"""Fetch the scoreboard for ``day`` (ET); ESPN defaults to the nearest game day when omitted."""  # noqa: DOC201
	params = {"dates": day.strftime("%Y%m%d")} if day else {}
	response = requests.get(f"{BASE_URL}/scoreboard", params=params, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
	response.raise_for_status()
	return response.json()


def fetch_summary(event_id: str) -> dict:
	"""Fetch the full game summary (box score, plays, win probability)."""  # noqa: DOC201
	response = requests.get(f"{BASE_URL}/summary", params={"event": event_id}, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
	response.raise_for_status()
	return response.json()


def save_snapshot(payload: dict, event_id: str) -> Path:
	"""Persist raw ESPN JSON to MEDIA_ROOT for replay and debugging."""  # noqa: DOC201
	now = timezone.now().astimezone(ET)
	directory = Path(settings.MEDIA_ROOT) / "espn_snapshots" / now.strftime("%Y-%m-%d")
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / f"{event_id}_{now.strftime('%H%M%S')}.json"
	path.write_text(json.dumps(payload))
	return path
