from functools import lru_cache

from core.services.sms import SMSService


@lru_cache(maxsize=1)
def get_sms_service() -> SMSService:
	"""Get a singleton instance of the SMSService."""  # noqa: DOC201
	return SMSService()
