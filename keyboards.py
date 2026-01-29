"""Inline keyboards for Telegram Bot."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============== Gate Check ==============

def gate_keyboard(channel_url: str, group_url: str) -> InlineKeyboardMarkup:
    """Keyboard for join gate."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Join Channel", url=channel_url),
        InlineKeyboardButton(text="👥 Join Group", url=group_url),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Kiểm tra", callback_data="check_join")
    )
    return builder.as_markup()


# ============== Main Menu ==============

def main_menu_keyboard(credits: int = 0) -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔎 Xác minh GitHub Student",
            callback_data="verify_start"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🧾 Tài khoản ({credits} credits)",
            callback_data="account"
        )
    )
    builder.row(
        InlineKeyboardButton(text="👫 Giới thiệu bạn bè", callback_data="referral"),
        InlineKeyboardButton(text="🎁 Nhập code", callback_data="redeem_code"),
    )
    return builder.as_markup()


# ============== Verification ==============

def verify_payment_keyboard() -> InlineKeyboardMarkup:
    """Choose payment method keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Dùng 1 Credit", callback_data="pay_credit")
    )
    builder.row(
        InlineKeyboardButton(text="💳 Thanh toán QR 30K", callback_data="pay_qr")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Quay lại", callback_data="back_main")
    )
    return builder.as_markup()


def no_credit_keyboard() -> InlineKeyboardMarkup:
    """Suggested actions when no credits."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Thanh toán QR 30K", callback_data="pay_qr")
    )
    builder.row(
        InlineKeyboardButton(text="👫 Kiếm credits qua referral", callback_data="referral")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Nhập code", callback_data="redeem_code")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Quay lại", callback_data="back_main")
    )
    return builder.as_markup()


def confirm_credit_keyboard() -> InlineKeyboardMarkup:
    """Confirm credit usage keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Xác nhận", callback_data="confirm_credit"),
        InlineKeyboardButton(text="❌ Hủy", callback_data="verify_start"),
    )
    return builder.as_markup()


def qr_payment_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """QR payment waiting keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Kiểm tra thanh toán",
            callback_data=f"check_payment:{order_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="❌ Hủy", callback_data=f"cancel_order:{order_id}")
    )
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Cancel current action."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Hủy", callback_data="back_main")
    )
    return builder.as_markup()


def back_main_keyboard() -> InlineKeyboardMarkup:
    """Back to main menu."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Menu chính", callback_data="back_main")
    )
    return builder.as_markup()


# ============== Admin ==============

def admin_keyboard() -> InlineKeyboardMarkup:
    """Admin panel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Quản lý User", callback_data="admin_users")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Thông báo", callback_data="admin_broadcast")
    )
    builder.row(
        InlineKeyboardButton(text="⏸️ Tạm dừng dịch vụ", callback_data="admin_maintenance")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Quản lý Code", callback_data="admin_codes")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Thống kê", callback_data="admin_stats")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Thoát Admin", callback_data="back_main")
    )
    return builder.as_markup()


def admin_user_actions_keyboard(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """Admin actions for a specific user."""
    builder = InlineKeyboardBuilder()
    
    if is_banned:
        builder.row(
            InlineKeyboardButton(
                text="✅ Bỏ cấm",
                callback_data=f"admin_unban:{user_id}"
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🚫 Cấm",
                callback_data=f"admin_ban:{user_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="💰 Sửa credits",
            callback_data=f"admin_edit_credits:{user_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Quay lại", callback_data="admin_users")
    )
    return builder.as_markup()


def admin_codes_keyboard() -> InlineKeyboardMarkup:
    """Admin code management keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Tạo code mới", callback_data="admin_create_code")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Danh sách codes", callback_data="admin_list_codes")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Quay lại", callback_data="admin_panel")
    )
    return builder.as_markup()
