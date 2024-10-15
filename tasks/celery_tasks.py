@app.task
def process_question(Body: str, From: str):
    logger.info(f"Processing question for user: {From}")
    try:
        # Remove 'whatsapp:' prefix from the phone number
        From = From.replace('whatsapp:', '')

        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            return

        logger.debug(f"Getting conversation ID for user: {From}")
        conversation_id = chat_service.get_conversation_id(From)
        logger.debug(f"Conversation ID for user {From}: {conversation_id}")

        logger.debug(f"Creating chat message for user {From} with body: {Body}")
        result = chat_service.create_chat_message(From, Body, conversation_id)
        logger.info(f"Response for user {From}: {result}")

        logger.debug(f"Sending message to user {From}")
        messaging_service.send_message(From, result)
        logger.info(f"Message sent successfully to user {From}")

    except Exception as e:
        logger.error(f"Error processing message for {From}: {str(e)}")
        logger.error(traceback.format_exc())
        # Optionally, send an error message to the user
        messaging_service.send_message(From, "Sorry, an error occurred while processing your message. Please try again later.")