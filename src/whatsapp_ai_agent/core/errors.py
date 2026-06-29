class WhatsAppAIAgentError(Exception):
    """Base application error."""


class WebhookValidationError(WhatsAppAIAgentError):
    """Raised when a webhook signature or secret header is invalid."""
