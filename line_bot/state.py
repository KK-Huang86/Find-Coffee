from line_bot.constants import UserState

user_states = {}


def get_state(user_id):
    return user_states.get(user_id, UserState.NORMAL)


def set_state(user_id, state):
    user_states[user_id] = state


def reset_state(user_id):
    user_states[user_id] = UserState.NORMAL
