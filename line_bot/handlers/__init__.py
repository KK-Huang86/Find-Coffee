from line_bot.handlers.postback_actions import ACTION_HANDLERS

__all__ = ['ACTION_HANDLERS']


def get_handler():
    """延遲導入以避免循環引用"""
    from line_bot.event_handlers import handler
    return handler
