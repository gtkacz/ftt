import json

import pandas as pd
import unidecode
from django.db import transaction

from core.models import Player


def parse_positions(pos_str: str) -> tuple[str, str | None]:
	pos_str = pos_str.removesuffix(",Flx")
	parts = pos_str.split(",")
	primary = parts[0]
	secondary = parts[1] if len(parts) > 1 else None

	return primary, secondary


def main(csv_path):
	df = pd.read_csv(csv_path, usecols=["Player", "Position", "FP/G", "FPts"])

	with transaction.atomic():
		for _, row in df.iterrows():
			csv_name = row["Player"]
			norm_csv_name = csv_name

			# Find matching player
			player = None
			for p in Player.objects.all():
				full_name = f"{p.first_name} {p.last_name}".removesuffix(" Jr").removesuffix(" Jr.").replace("Cam", "Cameron")
				if unidecode.unidecode(full_name) == norm_csv_name:
					player = p
					break

			if not player:
				print(f"Player not found: {csv_name}")
				continue

			# Parse positions
			primary, secondary = parse_positions(row["Position"])
			player.primary_position = primary
			player.secondary_position = secondary

			# Update metadata
			meta_str = player.metadata or "{}"
			try:
				meta = json.loads(meta_str)
			except json.JSONDecodeError:
				meta = {}

			meta["fpts"] = float(row["FP/G"])
			meta["total_fpts"] = float(row["FPts"])
			player.metadata = json.dumps(meta)

			player.save()
			print(f"Updated {csv_name}: primary={primary}, secondary={secondary}, fpts={row['FP/G']}")
