import openai
from dify_client import ChatClient
from fastapi import FastAPI, Form
from decouple import config
from utils import send_message, logger, is_rate_limited
from keycloak_utils import get_user_by_phone
app = FastAPI()

dify_key = config("DIFY_KEY")
chat_client = ChatClient(dify_key)

def is_user_authorized(phone_number):
    if "whatsapp" in phone_number:
        phone_number = phone_number.split(':')[1].strip()
        print(phone_number)
    users = get_user_by_phone(phone_number)
    if len(users) == 1:
        return True
    return False

@app.post("/message")
def reply(Body: str = Form(), From: str = Form()):
    try:
        if not is_user_authorized(From):
            logger.info(f"user not present with phone number ${From}")
            send_message(From, "Signup to continue chating with Ask Nithyananda, please visit +1 2518100108")
            return
        if is_rate_limited(From):
            logger.info(f"rate limit exceed for ${From}")
            return

        chat_client.base_url = "http://brightpath.koogle.sk/v1"

        # Check if there is an existing conversation ID for the user
        conversation_id = None
        conversations = chat_client.get_conversations(user=From)
        conversations.raise_for_status()
        # logger.info(f"conversations json was {conversations.json()}")

        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if len(conversation_list) > 0:
                conversation_id = conversation_list[0].get("id")

        logger.info(f"conversation id was {conversation_id}")

        if not conversation_id:
            # If no conversation exists, create a new one
            response = chat_client.create_chat_message(inputs={}, query=Body, user=From, response_mode="blocking")
            response.raise_for_status()
            result = response.json().get("answer")
            logger.info(f"The response to be sent was {result}")
            # Send message back to the sender's number
            send_message(From, result)
            return {"status": "Message sent successfully"}
        else:
            # Continue the conversation by including the conversation_id and first_id
            response = chat_client.create_chat_message(
                inputs={},
                query=Body,
                user=From,
                conversation_id=conversation_id,
                response_mode="blocking"
            )
            response.raise_for_status()
            result = response.json().get("answer")
            logger.info(f"The response to be sent was {result}")

            # Send message back to the sender's number
            send_message(From, result)
            return {"status": "Message sent successfully"}

    except Exception as e:
        logger.error(f"Error sending message to {From}: {str(e)}")
        return {"status": "Failed to send message", "error": str(e)}
