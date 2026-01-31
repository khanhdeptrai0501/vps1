"""
Verification Worker - Background tasks for:
1. Check GitHub status sau 5 phút
2. Retry nếu bị denied (max 3 lần)
3. Refund credits nếu fail

Chạy cùng với telegram_bot.py
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import aiohttp
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import (
    VerificationOrder, User, OrderStatus, GitHubStatus, 
    PaymentType, VerificationQueue, QueueStatus
)

logger = logging.getLogger(__name__)

# Constants
CHECK_INTERVAL_SECONDS = 60  # Check mỗi 60 giây
WAIT_BEFORE_CHECK_MINUTES = 5  # Đợi 5 phút sau khi submit mới check
MAX_RETRY_ATTEMPTS = 3

# Verification steps (b0-b7)
VERIFICATION_STEPS = [
    ("b0", "🔐 Kiểm tra cookie"),
    ("b1", "🎓 Tạo thông tin sinh viên"),
    ("b2", "🏫 Chọn trường học"),
    ("b3", "🖼️ Tạo thẻ sinh viên"),
    ("b4", "📋 Điền form đăng ký"),
    ("b5", "📤 Gửi yêu cầu"),
    ("b6", "📎 Upload bằng chứng"),
    ("b7", "✅ Hoàn tất"),
]


def mask_text(text: str) -> str:
    """Mask sensitive text: 'Harvard University' → '███████ University'"""
    if not text:
        return "████████"
    words = text.split()
    masked = []
    for word in words:
        if len(word) > 3:
            masked.append('█' * min(len(word), 10))
        else:
            masked.append(word)
    return ' '.join(masked)


def mask_email(email: str) -> str:
    """Mask email: 'john@harvard.edu' → '████@███████.edu'"""
    if not email or '@' not in email:
        return "████@████.edu"
    local, domain = email.split('@')
    domain_parts = domain.split('.')
    return f"{'█' * min(len(local), 8)}@{'█' * min(len(domain_parts[0]), 8)}.{domain_parts[-1]}"


def build_progress_message(step_index: int, school: str = None, email: str = None) -> str:
    """Build progress message for verification."""
    lines = ["🔄 **ĐANG XÁC MINH GITHUB STUDENT**\n"]
    
    for i, (code, name) in enumerate(VERIFICATION_STEPS):
        if i < step_index:
            indicator = "✅"
        elif i == step_index:
            indicator = "⏳"
        else:
            indicator = "⬜"
        lines.append(f"{indicator} {code}: {name}")
    
    # Progress bar
    percent = int((step_index + 1) / len(VERIFICATION_STEPS) * 100)
    bar_filled = int(percent / 5)
    bar = "━" * bar_filled + "─" * (20 - bar_filled)
    lines.append(f"\n{bar} {percent}%")
    
    # Masked info
    if school:
        lines.append(f"\n📍 Trường: {mask_text(school)}")
    if email:
        lines.append(f"📧 Email: {mask_email(email)}")
    
    return "\n".join(lines)


async def check_github_status(cookie: str) -> Tuple[str, Optional[str]]:
    """
    Check GitHub application status.
    
    Returns:
        Tuple of (status, denial_reasons)
        status: "approved", "denied", "pending"
        denial_reasons: JSON string of reasons if denied
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{settings.api_server_url}/check-status",
                json={"cookie": cookie},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Check status failed: {response.status}")
                    return "pending", None
                
                result = await response.json()
                status = result.get("status", "pending")
                reasons = result.get("reasons")
                
                return status, json.dumps(reasons) if reasons else None
                
    except Exception as e:
        logger.exception(f"Error checking GitHub status: {e}")
        return "pending", None


async def refund_order(session: AsyncSession, order: VerificationOrder, user: User):
    """Refund credits for failed order."""
    if order.refunded:
        return
    
    if order.payment_type == PaymentType.CREDIT:
        user.credits += 1  # Hoàn 1 credit
        order.refunded = True
        order.status = OrderStatus.REFUNDED
        
        logger.info(f"Refunded 1 credit to user {user.telegram_id} for order {order.id}")
    else:
        # QR Payment - cần admin xử lý
        order.status = OrderStatus.FAILED
        order.error_message = "Cần hoàn tiền thủ công"
        logger.info(f"Order {order.id} needs manual refund (QR payment)")


async def process_submitted_orders(bot=None):
    """
    Process orders that have been submitted and need status check.
    Called every minute by the worker.
    """
    async with AsyncSessionLocal() as session:
        # Lấy các orders đã submit > 5 phút và chưa check gần đây
        cutoff_time = datetime.utcnow() - timedelta(minutes=WAIT_BEFORE_CHECK_MINUTES)
        check_cutoff = datetime.utcnow() - timedelta(minutes=WAIT_BEFORE_CHECK_MINUTES)
        
        result = await session.execute(
            select(VerificationOrder).where(
                and_(
                    VerificationOrder.status.in_([
                        OrderStatus.SUBMITTED,
                        OrderStatus.CHECKING,
                        OrderStatus.RETRYING
                    ]),
                    VerificationOrder.submitted_at < cutoff_time,
                    VerificationOrder.attempt_count < MAX_RETRY_ATTEMPTS,
                    # Chưa check hoặc check > 5 phút trước
                    (VerificationOrder.last_check_at == None) | 
                    (VerificationOrder.last_check_at < check_cutoff)
                )
            )
        )
        orders = result.scalars().all()
        
        for order in orders:
            try:
                await process_single_order(session, order, bot)
            except Exception as e:
                logger.exception(f"Error processing order {order.id}: {e}")
        
        await session.commit()


async def process_single_order(session: AsyncSession, order: VerificationOrder, bot=None):
    """Process a single order - check status and handle result."""
    logger.info(f"Checking status for order {order.id}, attempt {order.attempt_count}")
    
    order.last_check_at = datetime.utcnow()
    order.status = OrderStatus.CHECKING
    
    # Check GitHub status
    status, reasons = await check_github_status(order.github_cookie)
    
    # Get user for notifications
    user_result = await session.execute(
        select(User).where(User.id == order.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if status == "approved":
        order.status = OrderStatus.COMPLETED
        order.github_status = GitHubStatus.APPROVED
        order.completed_at = datetime.utcnow()
        
        if bot and user:
            try:
                await bot.send_message(
                    user.telegram_id,
                    "🎉 **XÁC MINH THÀNH CÔNG!**\n\n"
                    "✅ GitHub đã chấp nhận yêu cầu của bạn!\n"
                    "📧 Kiểm tra email để nhận thông tin về benefits.\n\n"
                    "Cảm ơn bạn đã sử dụng dịch vụ! 🙏",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user: {e}")
                
    elif status == "denied":
        order.github_status = GitHubStatus.DENIED
        order.denial_reasons = reasons
        order.attempt_count += 1
        
        if order.attempt_count < MAX_RETRY_ATTEMPTS:
            # Còn lượt retry
            order.status = OrderStatus.RETRYING
            
            if bot and user:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"⚠️ **Yêu cầu bị từ chối**\n\n"
                        f"🔄 Đang thử lại lần {order.attempt_count}/{MAX_RETRY_ATTEMPTS}...\n"
                        f"Vui lòng đợi 5 phút để kiểm tra kết quả.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            # Trigger retry (sẽ được xử lý bởi queue worker)
            await trigger_retry(session, order)
            
        else:
            # Hết lượt retry - refund
            if user:
                await refund_order(session, order, user)
                
                if bot:
                    try:
                        refund_msg = "💰 Đã hoàn lại 1 credit." if order.payment_type == PaymentType.CREDIT else "💰 Liên hệ admin để được hoàn tiền."
                        await bot.send_message(
                            user.telegram_id,
                            f"❌ **Xác minh thất bại sau {MAX_RETRY_ATTEMPTS} lần thử**\n\n"
                            f"{refund_msg}\n\n"
                            f"📋 Lý do từ chối:\n{format_denial_reasons(reasons)}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
    else:
        # Still pending - keep checking
        order.status = OrderStatus.SUBMITTED
        logger.info(f"Order {order.id} still pending")


async def trigger_retry(session: AsyncSession, order: VerificationOrder):
    """Trigger a retry for verification."""
    # TODO: Implement retry with data variation
    # For now, just re-submit with same data
    order.submitted_at = datetime.utcnow()
    order.status = OrderStatus.PROCESSING
    
    logger.info(f"Triggered retry for order {order.id}, attempt {order.attempt_count}")


def format_denial_reasons(reasons_json: Optional[str]) -> str:
    """Format denial reasons for display."""
    if not reasons_json:
        return "- Không rõ lý do"
    
    try:
        reasons = json.loads(reasons_json)
        if isinstance(reasons, list):
            return "\n".join(f"- {r}" for r in reasons)
        return str(reasons)
    except:
        return reasons_json


class VerificationWorker:
    """Background worker for verification status checking."""
    
    def __init__(self, bot=None):
        self.bot = bot
        self.running = False
    
    async def start(self):
        """Start the worker."""
        self.running = True
        logger.info("VerificationWorker started")
        
        while self.running:
            try:
                await process_submitted_orders(self.bot)
            except Exception as e:
                logger.exception(f"VerificationWorker error: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    
    def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("VerificationWorker stopped")


# Singleton instance
_worker_instance: Optional[VerificationWorker] = None


def get_worker(bot=None) -> VerificationWorker:
    """Get or create worker instance."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = VerificationWorker(bot)
    return _worker_instance
