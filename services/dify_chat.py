from dify_client import ChatClient
from core.config import settings

class ChatService:
    def __init__(self):
        self.chat_client = ChatClient(settings.DIFY_KEY)
        self.chat_client.base_url = settings.DIFY_URL

    def get_conversation_id(self, user: str):
        conversations = self.chat_client.get_conversations(user=user)
        conversations.raise_for_status()
        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if len(conversation_list) > 0:
                return conversation_list[0].get("id")
        return None

    def create_chat_message(self, user: str, query: str, conversation_id: str = None):
        response = self.chat_client.create_chat_message(
            inputs={},
            query=query,
            user=user,
            conversation_id=conversation_id,
            response_mode="blocking"
        )
        response.raise_for_status()
        return response.json().get("answer")