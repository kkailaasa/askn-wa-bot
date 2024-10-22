# services/dify_chat.py
from typing import Optional
from dify_client import ChatClient
from core.config import settings
import logging
from urllib.parse import urlparse
from utils.http_client import http_pool

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.chat_client = ChatClient(settings.DIFY_KEY)
        self.chat_client.base_url = settings.DIFY_URL
        self.logger = logging.getLogger(__name__)

        # Setup connection pool for Dify
        dify_url = urlparse(settings.DIFY_URL)
        self.dify_pool = http_pool.get_pool(
            host=dify_url.netloc,
            maxsize=settings.DIFY_MAX_CONNECTIONS
        )

    def _make_request(self, method, endpoint, **kwargs):
        url = f"{self.chat_client.base_url}{endpoint}"
        response = self.dify_pool.request(
            method,
            url,
            headers=self.chat_client.headers,
            **kwargs
        )
        return response

    def get_conversation_id(self, user: str) -> Optional[str]:
        try:
            self.logger.debug(f"Getting conversations for user: {user}")
            conversations = self.chat_client.get_conversations(user=user)
            conversations.raise_for_status()

            response_data = conversations.json()
            self.logger.debug(f"Got conversations response: {response_data}")

            if "data" in response_data:
                conversation_list = response_data.get("data")
                if conversation_list and len(conversation_list) > 0:
                    return conversation_list[0].get("id")
            return None
        except Exception as e:
            self.logger.error(f"Error getting conversation ID: {str(e)}", exc_info=True)
            return None

    def create_chat_message(self, user: str, query: str, conversation_id: Optional[str] = None) -> str:
        try:
            self.logger.debug(f"Creating chat message - User: {user}, Query: {query}, Conversation ID: {conversation_id}")

            response = self.chat_client.create_chat_message(
                inputs={},
                query=query,
                user=user,
                conversation_id=conversation_id,
                response_mode="blocking"
            )
            response.raise_for_status()

            response_data = response.json()
            self.logger.debug(f"Got response: {response_data}")

            return response_data.get("answer", "I'm sorry, I couldn't process your message.")
        except Exception as e:
            self.logger.error(f"Error creating chat message: {str(e)}", exc_info=True)
            raise