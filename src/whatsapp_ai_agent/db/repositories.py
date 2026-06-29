from sqlalchemy.orm import Session

from whatsapp_ai_agent.db.models import RawInboundMessage


class RawInboundMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: RawInboundMessage) -> RawInboundMessage:
        self.session.add(message)
        self.session.flush()
        return message
