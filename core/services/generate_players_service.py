from datetime import date
from json import dumps

import pandas as pd
import requests
from django.db.transaction import atomic

from core.models import NBATeam, Player


def parse_response_to_dataframe(
	response_dict: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
	"""Parse NBA API response to pandas DataFrame"""
	result_set = response_dict["resultSets"][0]
	headers = result_set["headers"]
	rows = result_set["rowSet"]

	players_df = pd.DataFrame(rows, columns=headers)

	position_split = players_df["POSITION"].str.split("-", expand=True)
	players_df["POSITION"] = position_split[0]
	players_df["SECONDARY_POSITION"] = position_split[1]

	players_df.rename(
		columns={
			"PERSON_ID": "nba_id",
			"PLAYER_LAST_NAME": "last_name",
			"PLAYER_FIRST_NAME": "first_name",
			"POSITION": "primary_position",
			"SECONDARY_POSITION": "secondary_position",
			"ROSTER_STATUS": "roster_status",
			"TEAM_ABBREVIATION": "real_team",
			"PLAYER_SLUG": "slug",
		},
		inplace=True,
	)

	players_df = players_df[players_df["TO_YEAR"].astype(int) >= date.today().year - 5]
	players_df["real_team"] = players_df.apply(
		lambda x: x["real_team"] if pd.notnull(x["roster_status"]) else None,
		axis=1,
	)

	teams_df = pd.DataFrame(rows, columns=headers)[
		[
			"TEAM_CITY",
			"TEAM_NAME",
			"TEAM_ABBREVIATION",
		]
	]

	teams_df = teams_df.drop_duplicates(subset=["TEAM_ABBREVIATION"])
	teams_df = teams_df[teams_df["TEAM_ABBREVIATION"].notnull()]
	teams_df.rename(
		columns={
			"TEAM_CITY": "city",
			"TEAM_NAME": "name",
			"TEAM_ABBREVIATION": "abbreviation",
		},
		inplace=True,
	)

	return players_df, teams_df


def run():
	url = "https://stats.nba.com/stats/playerindex?College=&Country=&DraftPick=&DraftRound=&DraftYear=&Height=&Historical=1&LeagueID=00&Season=2025-26&SeasonType=Preseason&TeamID=0&Weight="

	payload = {}
	headers = {
		"Accept-Encoding": "gzip, deflate, br, zstd",
		"Accept-Language": "en-US,en;q=0.6",
		"Connection": "keep-alive",
		"Host": "stats.nba.com",
		"Origin": "https://www.nba.com",
		"Referer": "https://www.nba.com/",
		"Sec-Fetch-Dest": "empty",
		"Sec-Fetch-Mode": "cors",
		"Sec-Fetch-Site": "same-site",
		"Sec-GPC": "1",
		"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
		"sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"',
		"sec-ch-ua-mobile": "?0",
		"sec-ch-ua-platform": '"Windows"',
		"Cookie": "ak_bmsc=75E63D34D98CBE33BA60F827BD28D7A2~000000000000000000000000000000~YAAQ+H4SAoRN9BSYAQAAclbRFRwZK+ABCcHpy3MenVOqwfFt5LVkweoyR2sadeguo76N67NXiC5OBn/vLF9KIZ/zSyX19eJopup6RSu0lnP6tLngDp8TG7LVrb+qAtaf+9NQKrDisYEAllCi82VlX3YVXQSWUag5XCwftCztOtrriwjDab8xzvYesfA45V95feMpLVogKFl11/Gp+zzLHLCktooqHQcnmGyQLBbBEI5d7Ejt1NyTKkhy3dYWtJnjJN+CyK4v+qBXa2IoZ5ZKxbUofmbZ+7n2FlSgT11YwiwF2C3eGC/dBbme3+z1CjRDgOYa+Wg18ttG2gBs8fIIHQ0kUfABHKJ4Gg==",
	}

	try:
		response = requests.request("GET", url, headers=headers, data=payload, timeout=5)
		response.raise_for_status()

		players_df, teams_df = parse_response_to_dataframe(response.json())

	except requests.exceptions.ReadTimeout:
		print("Request timed out, using backup data.")

		from json import loads

		with open("core/services/backup.json") as file:
			response_dict = loads(file.read())

		players_df, teams_df = parse_response_to_dataframe(response_dict)

	with atomic():
		NBATeam.objects.bulk_create(
			[NBATeam(**row) for row in teams_df.to_dict(orient="records")],
			update_conflicts=True,
			unique_fields=["abbreviation"],
			batch_size=1000,
		)

		players_df["real_team"] = players_df["real_team"].apply(
			lambda x: NBATeam.objects.get(abbreviation=x) if pd.notnull(x) else None,
		)

		player_needed_cols = [
			"nba_id",
			"last_name",
			"first_name",
			"primary_position",
			"secondary_position",
			"real_team",
			"slug",
		]

		players_df["metadata"] = players_df[
			[col for col in players_df.columns if col not in player_needed_cols and col not in teams_df.columns]
		].apply(lambda row: dumps(row.to_dict()), axis=1)
		players_df = players_df[player_needed_cols + ["metadata"]]

		Player.objects.bulk_create(
			[
				Player(**row)
				for row in players_df[~players_df["primary_position"].isnull()][
					player_needed_cols + ["metadata"]
				].to_dict(orient="records")
			],
			update_conflicts=True,
			unique_fields=["nba_id"],
			batch_size=1000,
		)
