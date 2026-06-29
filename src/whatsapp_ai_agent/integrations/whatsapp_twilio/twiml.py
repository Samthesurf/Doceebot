from twilio.twiml.messaging_response import MessagingResponse


def empty_messaging_response() -> str:
    return str(MessagingResponse())


def text_messaging_response(message: str) -> str:
    response = MessagingResponse()
    response.message(message)
    return str(response)
