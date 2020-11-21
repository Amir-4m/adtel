from .functions import refresh_session
from .texts import CANT_START


def add_session(view_func=None, clear=False):
    def inner(function):
        def params(*args, **kwargs):
            user_session = refresh_session(*args, **kwargs, clear=clear)
            if user_session:
                return function(*args, **kwargs, session=user_session)

            elif user_session is False:
                bot = args[0]
                update = args[1]
                bot.send_message(update.effective_user.id, CANT_START)
                return

        return params

    if view_func:
        return inner(view_func)
    return inner

