from dataclasses import dataclass
from datetime import datetime

from scoring.fields import derive_fields

_PAIR_KEYS = {
	"fieldGoalsMade-fieldGoalsAttempted": ("FGM", "FGA"),
	"threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("TPM", "TPA"),
	"freeThrowsMade-freeThrowsAttempted": ("FTM", "FTA"),
}

_SCALAR_KEYS = {
	"minutes": "MIN",
	"points": "PTS",
	"rebounds": "REB",
	"assists": "AST",
	"turnovers": "TO",
	"steals": "STL",
	"blocks": "BLK",
	"offensiveRebounds": "OREB",
	"defensiveRebounds": "DREB",
	"fouls": "PF",
	"plusMinus": "PLUS_MINUS",
}


@dataclass(frozen=True)
class GameInfo:
	event_id: str
	starts_at: datetime
	state: str
	period: int
	clock: str
	home_abbr: str
	away_abbr: str


@dataclass(frozen=True)
class PlayerLine:
	espn_id: str
	display_name: str
	team_abbr: str
	stats: dict[str, float]


def _to_number(value: object) -> float:
	if isinstance(value, (int, float)):
		return value

	text = str(value).strip().lstrip("+")

	if not text or text in {"-", "--"}:
		return 0

	if ":" in text:
		# Minutes occasionally arrive as MM:SS; the league scores whole minutes.
		text = text.split(":", 1)[0]

	try:
		return int(text)

	except ValueError:
		try:
			return float(text)

		except ValueError:
			return 0


def extract_games(scoreboard: dict) -> list[GameInfo]:
	"""Flatten an ESPN scoreboard payload into GameInfo rows."""
	games = []

	for event in scoreboard.get("events", ()):
		competition = (event.get("competitions") or [{}])[0]
		home_abbr = away_abbr = ""

		for competitor in competition.get("competitors", ()):
			abbr = (competitor.get("team") or {}).get("abbreviation", "")

			if competitor.get("homeAway") == "home":
				home_abbr = abbr

			else:
				away_abbr = abbr

		status = event.get("status") or {}
		status_type = status.get("type") or {}

		games.append(
			GameInfo(
				event_id=str(event["id"]),
				starts_at=datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00")),
				state=str(status_type.get("state") or "pre"),
				period=int(status.get("period") or 0),
				clock=str(status.get("displayClock") or ""),
				home_abbr=home_abbr,
				away_abbr=away_abbr,
			),
		)

	return games


def _winning_abbrs(summary: dict) -> set[str]:
	competitors = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors", ())
	return {
		(competitor.get("team") or {}).get("abbreviation", "") for competitor in competitors if competitor.get("winner")
	}


def _box_stats(keys: list[str], raw_values: list[str]) -> dict[str, float]:
	stats: dict[str, float] = {}

	for key, raw in zip(keys, raw_values):
		if key in _PAIR_KEYS:
			made_key, attempted_key = _PAIR_KEYS[key]
			made, _, attempted = str(raw).partition("-")
			stats[made_key] = _to_number(made)
			stats[attempted_key] = _to_number(attempted)

		elif key in _SCALAR_KEYS:
			stats[_SCALAR_KEYS[key]] = _to_number(raw)

	return stats


def _pbp_counters(summary: dict, names_by_id: dict[str, str]) -> dict[str, dict[str, int]]:
	counters = {espn_id: {"TF": 0, "FLAGRANT": 0, "EJECTION": 0} for espn_id in names_by_id}
	names_longest_first = sorted(names_by_id.items(), key=lambda item: -len(item[1]))

	for play in summary.get("plays", ()):
		text = str(play.get("text") or "")
		lowered = text.lower()
		is_technical = "technical foul" in lowered and "technical free throw" not in lowered
		is_flagrant = "flagrant foul" in lowered
		is_ejection = "ejected" in lowered or "ejection" in lowered

		if not (is_technical or is_flagrant or is_ejection):
			continue

		espn_id = None

		for participant in play.get("participants") or ():
			candidate = str((participant.get("athlete") or {}).get("id") or "")

			if candidate in counters:
				espn_id = candidate
				break

		if espn_id is None:
			# Older payloads omit participants; fall back to the attributed name in the play text.
			for candidate_id, name in names_longest_first:
				if name and name in text:
					espn_id = candidate_id
					break

		if espn_id is None:
			continue

		if is_technical:
			counters[espn_id]["TF"] += 1

		if is_flagrant:
			counters[espn_id]["FLAGRANT"] += 1

		if is_ejection:
			counters[espn_id]["EJECTION"] += 1

	return counters


def extract_player_lines(summary: dict) -> list[PlayerLine]:
	"""Flatten an ESPN game summary into catalog-complete PlayerLine rows."""
	winning_abbrs = _winning_abbrs(summary)
	team_blobs = (summary.get("boxscore") or {}).get("players", ())
	entries = []
	names_by_id: dict[str, str] = {}

	for team_blob in team_blobs:
		team_abbr = (team_blob.get("team") or {}).get("abbreviation", "")
		statistics = team_blob.get("statistics") or [{}]
		keys = statistics[0].get("keys") or []

		for athlete_entry in statistics[0].get("athletes", ()):
			athlete = athlete_entry.get("athlete") or {}
			espn_id = str(athlete.get("id") or "")

			if not espn_id:
				continue

			names_by_id[espn_id] = str(athlete.get("displayName") or "")
			entries.append((espn_id, team_abbr, athlete_entry, keys))

	counters = _pbp_counters(summary, names_by_id)
	lines = []

	for espn_id, team_abbr, athlete_entry, keys in entries:
		raw_values = athlete_entry.get("stats") or []
		stats = _box_stats(keys, raw_values) if raw_values and not athlete_entry.get("didNotPlay") else {}
		stats["STARTED"] = 1 if athlete_entry.get("starter") else 0
		stats["WON"] = 1 if team_abbr in winning_abbrs else 0
		stats.update(counters[espn_id])
		full_stats = derive_fields(stats)

		for name in _SCALAR_KEYS.values():
			full_stats.setdefault(name, 0)

		for made_key, attempted_key in _PAIR_KEYS.values():
			full_stats.setdefault(made_key, 0)
			full_stats.setdefault(attempted_key, 0)

		lines.append(
			PlayerLine(espn_id=espn_id, display_name=names_by_id[espn_id], team_abbr=team_abbr, stats=full_stats)
		)

	return lines
