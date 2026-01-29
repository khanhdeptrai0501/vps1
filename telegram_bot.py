#!/usr/bin/env python3
"""
🤖 GitHub Student Verification Telegram Bot
VPS1: Bot + API Server (Step 0-5)

Chạy: python telegram_bot.py
"""

import asyncio
import logging
import sys
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal, init_db
from models import User, PromoCode, PromoCodeUsage, VerificationOrder, BotSettings, OrderStatus, PaymentType
from keyboards import (
    gate_keyboard, main_menu_keyboard, verify_payment_keyboard,
    no_credit_keyboard, confirm_credit_keyboard, qr_payment_keyboard,
    cancel_keyboard, back_main_keyboard, admin_keyboard,
    admin_user_actions_keyboard, admin_codes_keyboard,
)
from states import AdminAuth, Verification, RedeemCode, AdminBroadcast, AdminUserSearch, AdminEditCredits

# Logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Bot setup
bot = Bot(token=settings.bot_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()


# ============== Helpers ==============

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str = None, first_name: str = None) -> User:
    """Get or create user."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            referral_code=User.generate_referral_code(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update info
        user.username = username
        user.first_name = first_name
        await session.commit()
    
    return user


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    """Get bot setting."""
    result = await session.execute(
        select(BotSettings).where(BotSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str):
    """Set bot setting."""
    result = await session.execute(
        select(BotSettings).where(BotSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting:
        setting.value = value
    else:
        setting = BotSettings(key=key, value=value)
        session.add(setting)
    
    await session.commit()


async def is_maintenance_mode(session: AsyncSession) -> bool:
    """Check if maintenance mode is on."""
    return await get_setting(session, "maintenance_mode", "false") == "true"


async def check_user_joined(bot: Bot, user_id: int, chat_id: int) -> bool:
    """Check if user has joined a chat."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


# ============== Gate Check ==============

async def show_gate(message: Message, user: User):
    """Show join gate."""
    channel_url = f"https://t.me/c/{str(settings.channel_id)[4:]}" if settings.channel_id else "#"
    group_url = f"https://t.me/c/{str(settings.group_id)[4:]}" if settings.group_id else "#"
    
    text = (
        "👋 **Chào mừng bạn đến với GitHub Student Bot!**\n\n"
        "Để sử dụng bot, vui lòng tham gia:\n"
        "📢 Channel thông báo\n"
        "👥 Group hỗ trợ\n\n"
        "Sau khi tham gia, bấm **✅ Kiểm tra**"
    )
    await message.answer(text, reply_markup=gate_keyboard(channel_url, group_url), parse_mode="Markdown")


async def show_main_menu(message_or_callback, user: User):
    """Show main menu."""
    text = (
        f"✅ **Menu chính**\n\n"
        f"👤 Xin chào, {user.first_name or user.username or 'bạn'}!\n"
        f"💰 Credits: **{user.credits}**\n\n"
        f"Chọn chức năng bên dưới:"
    )
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(
            text, reply_markup=main_menu_keyboard(user.credits), parse_mode="Markdown"
        )
    else:
        await message_or_callback.answer(
            text, reply_markup=main_menu_keyboard(user.credits), parse_mode="Markdown"
        )


# ============== Command Handlers ==============

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        
        # Check banned
        if user.is_banned:
            await message.answer(f"🚫 Bạn đã bị cấm sử dụng bot.\nLý do: {user.ban_reason or 'Không rõ'}")
            return
        
        # Check maintenance
        if await is_maintenance_mode(session):
            await message.answer("🔧 Bot đang bảo trì. Vui lòng quay lại sau!")
            return
        
        # Check join gate
        if settings.channel_id and settings.group_id:
            joined_channel = await check_user_joined(bot, user.telegram_id, settings.channel_id)
            joined_group = await check_user_joined(bot, user.telegram_id, settings.group_id)
            
            user.joined_channel = joined_channel
            user.joined_group = joined_group
            await session.commit()
            
            if not user.has_joined_all():
                await show_gate(message, user)
                return
        
        await show_main_menu(message, user)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Handle /admin command."""
    await state.set_state(AdminAuth.waiting_password)
    await message.answer("🔐 Nhập mật khẩu admin:")


@router.message(AdminAuth.waiting_password)
async def admin_password(message: Message, state: FSMContext):
    """Check admin password."""
    if message.text == settings.admin_password:
        await state.clear()
        await message.answer("✅ Đăng nhập thành công!", reply_markup=admin_keyboard())
    else:
        await state.clear()
        await message.answer("❌ Sai mật khẩu!")


# ============== Callback Handlers ==============

@router.callback_query(F.data == "check_join")
async def callback_check_join(callback: CallbackQuery):
    """Check if user has joined channel and group."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        joined_channel = await check_user_joined(bot, user.telegram_id, settings.channel_id) if settings.channel_id else True
        joined_group = await check_user_joined(bot, user.telegram_id, settings.group_id) if settings.group_id else True
        
        user.joined_channel = joined_channel
        user.joined_group = joined_group
        await session.commit()
        
        if user.has_joined_all():
            await callback.answer("✅ Đã xác nhận!")
            await show_main_menu(callback, user)
        else:
            missing = []
            if not joined_channel:
                missing.append("Channel")
            if not joined_group:
                missing.append("Group")
            await callback.answer(f"❌ Bạn chưa tham gia: {', '.join(missing)}", show_alert=True)


@router.callback_query(F.data == "back_main")
async def callback_back_main(callback: CallbackQuery, state: FSMContext):
    """Back to main menu."""
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        await show_main_menu(callback, user)


@router.callback_query(F.data == "verify_start")
async def callback_verify_start(callback: CallbackQuery):
    """Start verification - choose payment method."""
    text = (
        "🔎 **Xác minh GitHub Student**\n\n"
        "Chọn cách thanh toán:"
    )
    await callback.message.edit_text(text, reply_markup=verify_payment_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "pay_credit")
async def callback_pay_credit(callback: CallbackQuery):
    """Pay with credit."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        if user.credits < 1:
            text = (
                "❌ **Không đủ credit!**\n\n"
                f"Bạn có: **{user.credits}** credits\n"
                f"Cần: **1** credit\n\n"
                "Chọn cách khác:"
            )
            await callback.message.edit_text(text, reply_markup=no_credit_keyboard(), parse_mode="Markdown")
        else:
            text = (
                "⚠️ **Xác nhận sử dụng credit**\n\n"
                f"Bạn có: **{user.credits}** credits\n"
                f"Sẽ trừ: **1** credit\n\n"
                "Tiếp tục?"
            )
            await callback.message.edit_text(text, reply_markup=confirm_credit_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "confirm_credit")
async def callback_confirm_credit(callback: CallbackQuery, state: FSMContext):
    """Confirm credit usage and ask for cookie."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        if user.credits < 1:
            await callback.answer("❌ Không đủ credit!", show_alert=True)
            return
        
        # Deduct credit
        user.credits -= 1
        
        # Create order
        order = VerificationOrder(
            user_id=user.id,
            payment_type=PaymentType.CREDIT,
            status=OrderStatus.PAID,
            paid_at=datetime.utcnow(),
        )
        session.add(order)
        await session.commit()
        
        # Store order_id in state
        await state.update_data(order_id=order.id)
        await state.set_state(Verification.waiting_cookie)
        
        text = (
            "✅ **Đã trừ 1 credit!**\n\n"
            "📝 Gửi cookie GitHub của bạn:\n"
            "*(Lấy từ trình duyệt: F12 → Application → Cookies → github.com)*\n\n"
            "⚠️ Cookie sẽ được dùng để xác minh và xóa ngay sau đó."
        )
        await callback.message.edit_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "pay_qr")
async def callback_pay_qr(callback: CallbackQuery):
    """Pay with QR."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        # Create order
        import uuid
        payment_ref = f"ODR_{uuid.uuid4().hex[:8].upper()}"
        
        order = VerificationOrder(
            user_id=user.id,
            payment_type=PaymentType.QR_PAYMENT,
            payment_ref=payment_ref,
            amount=settings.verification_price,
            status=OrderStatus.PENDING_PAYMENT,
        )
        session.add(order)
        await session.commit()
        
        # Generate QR URL
        from urllib.parse import quote
        memo = quote(f"Thanh toan {payment_ref}")
        qr_url = (
            f"https://img.vietqr.io/image/{settings.sepay_bank_code}"
            f"-{settings.sepay_account_number}-compact.png"
            f"?amount={settings.verification_price}&addInfo={memo}"
        )
        
        text = (
            "💳 **Thanh toán QR**\n\n"
            f"Số tiền: **{settings.verification_price:,}đ**\n"
            f"Mã đơn: `{payment_ref}`\n\n"
            "Quét mã QR bên dưới để thanh toán:\n"
            f"[Nhấn để xem QR]({qr_url})\n\n"
            "⏳ Sau khi thanh toán, bấm **Kiểm tra thanh toán**"
        )
        await callback.message.edit_text(
            text,
            reply_markup=qr_payment_keyboard(order.id),
            parse_mode="Markdown"
        )


@router.callback_query(F.data.startswith("check_payment:"))
async def callback_check_payment(callback: CallbackQuery, state: FSMContext):
    """Check payment status."""
    order_id = callback.data.split(":")[1]
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VerificationOrder).where(VerificationOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            await callback.answer("❌ Không tìm thấy đơn hàng!", show_alert=True)
            return
        
        if order.status == OrderStatus.PAID:
            await state.update_data(order_id=order_id)
            await state.set_state(Verification.waiting_cookie)
            
            text = (
                "✅ **Đã thanh toán thành công!**\n\n"
                "📝 Gửi cookie GitHub của bạn:\n"
                "*(Lấy từ trình duyệt: F12 → Application → Cookies → github.com)*"
            )
            await callback.message.edit_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
        else:
            await callback.answer("⏳ Chưa nhận được thanh toán. Vui lòng thử lại sau 30 giây.", show_alert=True)


@router.message(Verification.waiting_cookie)
async def handle_cookie_input(message: Message, state: FSMContext):
    """Handle cookie input and start verification."""
    cookie = message.text.strip()
    
    if len(cookie) < 50 or "user_session" not in cookie.lower():
        await message.answer(
            "❌ Cookie không hợp lệ!\n\n"
            "Cookie cần chứa `user_session`. Vui lòng thử lại.",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    order_id = data.get("order_id")
    
    await state.set_state(Verification.processing)
    
    processing_msg = await message.answer("⏳ Đang xử lý... Vui lòng đợi...")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VerificationOrder).where(VerificationOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            await processing_msg.edit_text("❌ Lỗi: Không tìm thấy đơn hàng!")
            await state.clear()
            return
        
        order.github_cookie = cookie
        order.status = OrderStatus.PROCESSING
        await session.commit()
        
        # Call API Server /prepare
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{settings.api_server_url}/prepare",
                    json={"cookie": cookie, "order_id": order_id},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    result_data = await resp.json()
                    
                    if not result_data.get("success"):
                        order.status = OrderStatus.FAILED
                        order.error_message = result_data.get("error", "Unknown error")
                        await session.commit()
                        
                        await processing_msg.edit_text(
                            f"❌ **Lỗi Step 0-5:**\n\n{order.error_message}",
                            reply_markup=back_main_keyboard(),
                            parse_mode="Markdown"
                        )
                        await state.clear()
                        return
                    
                    # Save data
                    order.github_username = result_data.get("username")
                    order.student_data = result_data.get("student_data")
                    order.card_base64 = result_data.get("card_base64")
                    order.geo_lat = result_data.get("geo", {}).get("lat")
                    order.geo_lng = result_data.get("geo", {}).get("lng")
                    order.status = OrderStatus.SUBMITTING
                    await session.commit()
                    
                    await processing_msg.edit_text("⏳ Đang submit đơn lên GitHub... (Step 6-7)")
                    
                    # Call VPS2 /submit
                    async with http.post(
                        f"{settings.vps2_url}/submit",
                        json={
                            "order_id": order_id,
                            "cookie": cookie,
                            "student_data": order.student_data,
                            "card_base64": order.card_base64,
                            "geo": {"lat": order.geo_lat, "lng": order.geo_lng},
                            "callback_url": f"{settings.api_server_url}/callback/submit"
                        },
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as resp2:
                        submit_result = await resp2.json()
                        
                        if submit_result.get("success"):
                            order.status = OrderStatus.COMPLETED
                            order.submit_result = "Submitted successfully"
                            order.completed_at = datetime.utcnow()
                            await session.commit()
                            
                            student = order.student_data or {}
                            text = (
                                "✅ **ĐÃ SUBMIT THÀNH CÔNG!**\n\n"
                                f"👤 GitHub: `{order.github_username}`\n"
                                f"🎓 Tên: {student.get('full_name', 'N/A')}\n"
                                f"🏫 Trường: {student.get('school_name', 'N/A')}\n"
                                f"📧 MSSV: {student.get('mssv', 'N/A')}\n\n"
                                "📬 Kiểm tra email GitHub để xác nhận từ GitHub!"
                            )
                            await processing_msg.edit_text(text, reply_markup=back_main_keyboard(), parse_mode="Markdown")
                        else:
                            order.status = OrderStatus.FAILED
                            order.error_message = submit_result.get("error", "Submit failed")
                            await session.commit()
                            
                            await processing_msg.edit_text(
                                f"❌ **Lỗi khi submit:**\n\n{order.error_message}",
                                reply_markup=back_main_keyboard(),
                                parse_mode="Markdown"
                            )
                        
        except asyncio.TimeoutError:
            order.status = OrderStatus.FAILED
            order.error_message = "Timeout"
            await session.commit()
            await processing_msg.edit_text("❌ Timeout! Vui lòng thử lại.", reply_markup=back_main_keyboard())
        except Exception as e:
            order.status = OrderStatus.FAILED
            order.error_message = str(e)
            await session.commit()
            await processing_msg.edit_text(f"❌ Lỗi: {e}", reply_markup=back_main_keyboard())
        
        await state.clear()


@router.callback_query(F.data == "account")
async def callback_account(callback: CallbackQuery):
    """Show account info."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        # Count orders
        result = await session.execute(
            select(func.count()).select_from(VerificationOrder).where(
                VerificationOrder.user_id == user.id,
                VerificationOrder.status == OrderStatus.COMPLETED
            )
        )
        completed_orders = result.scalar() or 0
        
        text = (
            f"🧾 **Tài khoản của bạn**\n\n"
            f"👤 Username: @{user.username or 'N/A'}\n"
            f"🆔 Telegram ID: `{user.telegram_id}`\n"
            f"💰 Credits: **{user.credits}**\n"
            f"✅ Đã xác minh: **{completed_orders}** lần\n"
            f"🔗 Mã giới thiệu: `{user.referral_code}`\n"
            f"👫 Đã giới thiệu: **{user.referral_count}** người\n"
        )
        await callback.message.edit_text(text, reply_markup=back_main_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery):
    """Show referral info."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        
        bot_info = await bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start=ref_{user.referral_code}"
        
        text = (
            f"👫 **Giới thiệu bạn bè**\n\n"
            f"Mỗi khi bạn bè của bạn xác minh thành công,\n"
            f"bạn nhận được **{settings.referral_bonus_credits}** credit!\n\n"
            f"🔗 Link giới thiệu của bạn:\n"
            f"`{referral_link}`\n\n"
            f"📊 Đã giới thiệu: **{user.referral_count}** người"
        )
        await callback.message.edit_text(text, reply_markup=back_main_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "redeem_code")
async def callback_redeem_code(callback: CallbackQuery, state: FSMContext):
    """Redeem promo code."""
    await state.set_state(RedeemCode.waiting_code)
    text = "🎁 **Nhập mã khuyến mãi:**"
    await callback.message.edit_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")


@router.message(RedeemCode.waiting_code)
async def handle_redeem_code(message: Message, state: FSMContext):
    """Handle promo code input."""
    code = message.text.strip().upper()
    
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        
        # Find code
        result = await session.execute(
            select(PromoCode).where(PromoCode.code == code)
        )
        promo = result.scalar_one_or_none()
        
        if not promo or not promo.is_valid():
            await message.answer("❌ Mã không hợp lệ hoặc đã hết hạn!", reply_markup=back_main_keyboard())
            await state.clear()
            return
        
        # Check if already used
        usage_result = await session.execute(
            select(PromoCodeUsage).where(
                PromoCodeUsage.user_id == user.id,
                PromoCodeUsage.promo_code_id == promo.id
            )
        )
        if usage_result.scalar_one_or_none():
            await message.answer("❌ Bạn đã sử dụng mã này rồi!", reply_markup=back_main_keyboard())
            await state.clear()
            return
        
        # Apply code
        user.credits += promo.credits_amount
        promo.current_uses += 1
        
        usage = PromoCodeUsage(user_id=user.id, promo_code_id=promo.id)
        session.add(usage)
        await session.commit()
        
        await message.answer(
            f"✅ **Thành công!**\n\n"
            f"➕ Nhận được: **{promo.credits_amount}** credits\n"
            f"💰 Tổng credits: **{user.credits}**",
            reply_markup=back_main_keyboard(),
            parse_mode="Markdown"
        )
        await state.clear()


# ============== Admin Handlers ==============

@router.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: CallbackQuery):
    """Show admin panel."""
    await callback.message.edit_text("🔐 **Admin Panel**", reply_markup=admin_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: CallbackQuery):
    """Show admin stats."""
    async with AsyncSessionLocal() as session:
        # Count users
        users_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        
        # Count orders
        total_orders = (await session.execute(select(func.count()).select_from(VerificationOrder))).scalar() or 0
        completed_orders = (await session.execute(
            select(func.count()).select_from(VerificationOrder).where(VerificationOrder.status == OrderStatus.COMPLETED)
        )).scalar() or 0
        
        # Total revenue
        revenue = (await session.execute(
            select(func.sum(VerificationOrder.amount)).where(
                VerificationOrder.payment_type == PaymentType.QR_PAYMENT,
                VerificationOrder.status == OrderStatus.COMPLETED
            )
        )).scalar() or 0
        
        text = (
            "📊 **Thống kê**\n\n"
            f"👥 Tổng users: **{users_count}**\n"
            f"📝 Tổng đơn: **{total_orders}**\n"
            f"✅ Thành công: **{completed_orders}**\n"
            f"💰 Doanh thu: **{revenue:,}đ**"
        )
        await callback.message.edit_text(text, reply_markup=admin_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "admin_maintenance")
async def callback_admin_maintenance(callback: CallbackQuery):
    """Toggle maintenance mode."""
    async with AsyncSessionLocal() as session:
        current = await get_setting(session, "maintenance_mode", "false")
        new_value = "false" if current == "true" else "true"
        await set_setting(session, "maintenance_mode", new_value)
        
        status = "🔴 BẬT" if new_value == "true" else "🟢 TẮT"
        await callback.answer(f"Chế độ bảo trì: {status}")
        await callback.message.edit_text(
            f"⏸️ **Chế độ bảo trì: {status}**",
            reply_markup=admin_keyboard(),
            parse_mode="Markdown"
        )


# ============== Main ==============

async def main():
    """Main function."""
    logger.info("Initializing database...")
    await init_db()
    
    logger.info("Starting bot...")
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║  🤖 GitHub Student Verification Bot                       ║
║  VPS1: Bot + API Server                                   ║
╚═══════════════════════════════════════════════════════════╝
""")
    asyncio.run(main())
