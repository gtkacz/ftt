import pandas as pd
import requests


def parse_response_to_dataframe(response_dict):
	"""Parse NBA API response to pandas DataFrame"""
	result_set = response_dict['resultSets'][0]
	headers = result_set['headers']
	rows = result_set['rowSet']

	df = pd.DataFrame(rows, columns=headers)

	return df


def run():
	url = 'https://stats.nba.com/stats/playerindex?College=&Country=&DraftPick=&DraftRound=&DraftYear=&Height=&Historical=1&LeagueID=00&Season=2025-26&SeasonType=Preseason&TeamID=0&Weight='

	payload = {}
	headers = {
		'Accept-Encoding': 'gzip, deflate, br, zstd',
		'Accept-Language': 'en-US,en;q=0.6',
		'Connection': 'keep-alive',
		'Host': 'stats.nba.com',
		'Origin': 'https://www.nba.com',
		'Referer': 'https://www.nba.com/',
		'Sec-Fetch-Dest': 'empty',
		'Sec-Fetch-Mode': 'cors',
		'Sec-Fetch-Site': 'same-site',
		'Sec-GPC': '1',
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
		'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"',
		'sec-ch-ua-mobile': '?0',
		'sec-ch-ua-platform': '"Windows"',
		'Cookie': 'ak_bmsc=75E63D34D98CBE33BA60F827BD28D7A2~000000000000000000000000000000~YAAQ+H4SAoRN9BSYAQAAclbRFRwZK+ABCcHpy3MenVOqwfFt5LVkweoyR2sadeguo76N67NXiC5OBn/vLF9KIZ/zSyX19eJopup6RSu0lnP6tLngDp8TG7LVrb+qAtaf+9NQKrDisYEAllCi82VlX3YVXQSWUag5XCwftCztOtrriwjDab8xzvYesfA45V95feMpLVogKFl11/Gp+zzLHLCktooqHQcnmGyQLBbBEI5d7Ejt1NyTKkhy3dYWtJnjJN+CyK4v+qBXa2IoZ5ZKxbUofmbZ+7n2FlSgT11YwiwF2C3eGC/dBbme3+z1CjRDgOYa+Wg18ttG2gBs8fIIHQ0kUfABHKJ4Gg==',
	}

	response = requests.request('GET', url, headers=headers, data=payload)

	response.raise_for_status()

	return parse_response_to_dataframe(response.json())
