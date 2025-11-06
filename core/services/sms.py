from warnings import warn

import clicksend_client
from clicksend_client import SmsMessage
from clicksend_client.rest import ApiException

from ftt.settings import ENV


class SMSService:
	def __init__(self) -> None:
		"""Initialize ClickSend SMS API client."""
		self.configuration = clicksend_client.Configuration()
		self.configuration.username = ENV.CLICKSEND_USERNAME
		self.configuration.password = ENV.CLICKSEND_API_KEY

		self.api_instance = clicksend_client.SMSApi(clicksend_client.ApiClient(self.configuration))

	def send_sms(self, message: str, phone_number: str) -> bool:
		"""
		Send an SMS message.

		Args:
			message (str): The message body to send.
			phone_number (str): The recipient's phone number.

		Returns:
			bool: True if the message was sent successfully, False otherwise.
		"""
		sms_message = SmsMessage(
			source="Fantasy Trash Talk",
			body=message,
			to=phone_number,
		)

		sms_messages = clicksend_client.SmsMessageCollection(messages=[sms_message])

		try:
			self.api_instance.sms_send_post(sms_messages)

		except ApiException as e:
			warn(f"Exception when sending SMS: {e}", stacklevel=2, category=RuntimeWarning)
			return False

		else:
			return True
