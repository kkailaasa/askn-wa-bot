@app.task
def process_question(Body: str, From: str):
    logger.info("Processing question")
    try:
        # Remove 'whatsapp:' prefix from the phone number
        From = From.replace('whatsapp:', '')

        #Authorization Celery Task
        #if not is_user_authorized(From):
        #    logger.info(f"User not present with phone number {From}")
        #    messaging_service.send_message(From, "Signup to continue chatting with Ask Nithyananda, please visit +1 2518100108")
        #    return

        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            return

        conversation_id = chat_service.get_conversation_id(From)
        result = chat_service.create_chat_message(From, Body, conversation_id)

        logger.info(f"The response to be sent was {result}")
        messaging_service.send_message(From, result)

    except Exception as e:
        logger.error(f"Error processing message for {From}: {str(e)}")
        logger.error(traceback.format_exc())
        # Optionally, send an error message to the user
        messaging_service.send_message(From, "Sorry, an error occurred while processing your message. Please try again later.")