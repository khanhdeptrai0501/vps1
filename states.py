"""FSM States for conversation flow."""

from aiogram.fsm.state import State, StatesGroup


class AdminAuth(StatesGroup):
    """Admin authentication states."""
    waiting_password = State()


class Verification(StatesGroup):
    """Verification flow states."""
    waiting_cookie = State()
    processing = State()


class RedeemCode(StatesGroup):
    """Redeem promo code states."""
    waiting_code = State()


class AdminBroadcast(StatesGroup):
    """Admin broadcast states."""
    waiting_message = State()
    confirm = State()


class AdminUserSearch(StatesGroup):
    """Admin user search states."""
    waiting_query = State()


class AdminEditCredits(StatesGroup):
    """Admin edit credits states."""
    waiting_amount = State()


class AdminCreateCode(StatesGroup):
    """Admin create promo code states."""
    waiting_code = State()
    waiting_credits = State()
    waiting_max_uses = State()
    waiting_expires = State()
