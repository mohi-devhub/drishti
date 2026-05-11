import logfire

from drishti.config import Settings


def configure_observability(settings: Settings) -> None:
    if not settings.logfire_token:
        logfire.configure(send_to_logfire=False, service_name=settings.logfire_service_name)
        return

    logfire.configure(token=settings.logfire_token, service_name=settings.logfire_service_name)
