class ChatService:
    def __init__(self):
        self.chat_client = ChatClient(settings.DIFY_KEY)
        self.chat_client.base_url = settings.DIFY_URL
        self.logger = logging.getLogger(__name__)

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