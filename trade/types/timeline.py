from datetime import datetime
from typing import Optional, TypedDict

from core.models import User
from trade.enums.trade_statuses import TradeStatuses


class TimelineEntry(TypedDict):
	"""A timeline entry for a trade."""
	status: TradeStatuses
	timestamp: datetime
	actioned_by: Optional[User]
	description: str
