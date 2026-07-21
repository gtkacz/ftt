from typing import Literal, NamedTuple


class FieldSpec(NamedTuple):
	"""One stat field exposed to scoring formulas; drives ingest, engine names, and the UI palette."""

	name: str
	label: str
	description: str
	example: float
	source: Literal["box", "derived", "pbp", "context"]


_BOX = (
	FieldSpec("MIN", "MIN", "Minutes played", 33, "box"),
	FieldSpec("PTS", "PTS", "Points scored", 25, "box"),
	FieldSpec("FGM", "FG made", "Field goals made", 9, "box"),
	FieldSpec("FGA", "FG att.", "Field goals attempted", 18, "box"),
	FieldSpec("TPM", "3PT made", "Three-pointers made (display: 3PM)", 3, "box"),
	FieldSpec("TPA", "3PT att.", "Three-pointers attempted (display: 3PA)", 8, "box"),
	FieldSpec("FTM", "FT made", "Free throws made", 4, "box"),
	FieldSpec("FTA", "FT att.", "Free throws attempted", 5, "box"),
	FieldSpec("OREB", "Off. reb.", "Offensive rebounds", 2, "box"),
	FieldSpec("DREB", "Def. reb.", "Defensive rebounds", 6, "box"),
	FieldSpec("REB", "Rebounds", "Total rebounds", 8, "box"),
	FieldSpec("AST", "Assists", "Assists", 7, "box"),
	FieldSpec("STL", "Steals", "Steals", 2, "box"),
	FieldSpec("BLK", "Blocks", "Blocks", 1, "box"),
	FieldSpec("TO", "Turnovers", "Turnovers", 3, "box"),
	FieldSpec("PF", "Fouls", "Personal fouls", 2, "box"),
	FieldSpec("PLUS_MINUS", "+/-", "Plus-minus while on court", -4, "box"),
)

_DERIVED = (
	FieldSpec("FG_MISS", "FG missed", "Field goals missed (FGA - FGM)", 9, "derived"),
	FieldSpec("TP_MISS", "3PT missed", "Three-pointers missed (TPA - TPM)", 5, "derived"),
	FieldSpec("FT_MISS", "FT missed", "Free throws missed (FTA - FTM)", 1, "derived"),
	FieldSpec("DD", "Double-double", "1 if 2+ of PTS/REB/AST/STL/BLK hit 10 (triple-double also counts)", 0, "derived"),
	FieldSpec("TD", "Triple-double", "1 if at least three of PTS/REB/AST/STL/BLK reached 10", 0, "derived"),
)

_PBP = (
	FieldSpec("TF", "Tech. fouls", "Technical fouls, from play-by-play", 0, "pbp"),
	FieldSpec("FLAGRANT", "Flagrant fouls", "Flagrant fouls, from play-by-play", 0, "pbp"),
	FieldSpec("EJECTION", "Ejections", "Ejections, from play-by-play", 0, "pbp"),
)

_CONTEXT = (
	FieldSpec("STARTED", "Started", "1 if the player started the game", 1, "context"),
	FieldSpec("WON", "Team won", "1 if the player's NBA team won the game", 1, "context"),
)

FIELD_CATALOG: dict[str, FieldSpec] = {spec.name: spec for spec in (*_BOX, *_DERIVED, *_PBP, *_CONTEXT)}

_TEN_CATEGORIES = ("PTS", "REB", "AST", "STL", "BLK")


def derive_fields(stats: dict[str, float]) -> dict[str, float]:
	"""Return a copy of ``stats`` with the derived catalog fields filled in."""
	out = dict(stats)
	out["FG_MISS"] = out.get("FGA", 0) - out.get("FGM", 0)
	out["TP_MISS"] = out.get("TPA", 0) - out.get("TPM", 0)
	out["FT_MISS"] = out.get("FTA", 0) - out.get("FTM", 0)
	tens = sum(1 for key in _TEN_CATEGORIES if out.get(key, 0) >= 10)
	out["DD"] = 1 if tens >= 2 else 0
	out["TD"] = 1 if tens >= 3 else 0
	return out
