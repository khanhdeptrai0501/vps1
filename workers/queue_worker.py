"""
Queue Worker - Quản lý hàng đợi xác minh.

Features:
- Max 5 concurrent verifications
- Tự động xử lý queue khi có slot
- Thông báo user khi đến lượt
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import (
    VerificationOrder, VerificationQueue, User,
    OrderStatus, QueueStatus
)

logger = logging.getLogger(__name__)

# Constants
MAX_CONCURRENT_VERIFICATIONS = 5
QUEUE_CHECK_INTERVAL_SECONDS = 30


async def get_processing_count(session: AsyncSession) -> int:
    """Count orders currently being processed."""
    result = await session.execute(
        select(func.count()).select_from(VerificationOrder).where(
            VerificationOrder.status.in_([
                OrderStatus.PROCESSING,
                OrderStatus.SUBMITTING,
            ])
        )
    )
    return result.scalar() or 0


async def get_waiting_queue_items(session: AsyncSession, limit: int = 5):
    """Get waiting queue items ordered by position."""
    result = await session.execute(
        select(VerificationQueue).where(
            VerificationQueue.status == QueueStatus.WAITING
        ).order_by(VerificationQueue.position).limit(limit)
    )
    return result.scalars().all()


async def get_next_queue_position(session: AsyncSession) -> int:
    """Get next position in queue."""
    result = await session.execute(
        select(func.max(VerificationQueue.position)).where(
            VerificationQueue.status == QueueStatus.WAITING
        )
    )
    max_pos = result.scalar() or 0
    return max_pos + 1


async def add_to_queue(
    session: AsyncSession, 
    order: VerificationOrder, 
    user: User
) -> dict:
    """
    Add order to queue or start immediately if slots available.
    
    Returns:
        dict with keys: queued (bool), position (int), started (bool)
    """
    processing_count = await get_processing_count(session)
    
    if processing_count < MAX_CONCURRENT_VERIFICATIONS:
        # Có slot - bắt đầu ngay
        order.status = OrderStatus.PROCESSING
        return {"queued": False, "started": True, "position": 0}
    
    # Hết slot - thêm vào queue
    position = await get_next_queue_position(session)
    
    queue_item = VerificationQueue(
        user_id=user.id,
        order_id=order.id,
        position=position,
        status=QueueStatus.WAITING
    )
    session.add(queue_item)
    
    order.status = OrderStatus.QUEUED
    
    return {
        "queued": True, 
        "started": False, 
        "position": position,
        "total_processing": processing_count
    }


async def update_queue_positions(session: AsyncSession):
    """Reorder queue positions after changes."""
    waiting_items = await get_waiting_queue_items(session, limit=100)
    
    for i, item in enumerate(waiting_items, 1):
        if item.position != i:
            item.position = i


async def process_queue(bot=None):
    """
    Process queue - start verification for next waiting items.
    Called every 30 seconds.
    """
    async with AsyncSessionLocal() as session:
        processing_count = await get_processing_count(session)
        available_slots = MAX_CONCURRENT_VERIFICATIONS - processing_count
        
        logger.debug(f"Queue check: {processing_count}/{MAX_CONCURRENT_VERIFICATIONS} processing, {available_slots} slots available")
        
        if available_slots <= 0:
            return
        
        # Get next waiting items
        waiting_items = await get_waiting_queue_items(session, limit=available_slots)
        
        for item in waiting_items:
            # Get order and user
            order_result = await session.execute(
                select(VerificationOrder).where(VerificationOrder.id == item.order_id)
            )
            order = order_result.scalar_one_or_none()
            
            user_result = await session.execute(
                select(User).where(User.id == item.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not order or not user:
                item.status = QueueStatus.CANCELLED
                continue
            
            # Update queue item
            item.status = QueueStatus.PROCESSING
            item.started_at = datetime.utcnow()
            
            # Update order
            order.status = OrderStatus.PROCESSING
            
            logger.info(f"Starting verification for order {order.id} from queue position {item.position}")
            
            # Notify user
            if bot:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "🚀 **Đến lượt bạn!**\n\n"
                        "Hệ thống đang bắt đầu xác minh GitHub Student...\n"
                        "Vui lòng chờ trong giây lát.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify user {user.telegram_id}: {e}")
            
            # TODO: Actually start verification process
            # This should call the API server to begin verification
        
        # Update positions for remaining items
        await update_queue_positions(session)
        
        await session.commit()


async def notify_queue_position_change(
    session: AsyncSession, 
    user: User, 
    old_position: int, 
    new_position: int,
    bot=None
):
    """Notify user when their queue position changes significantly."""
    if old_position - new_position >= 2:  # Position improved by 2+
        if bot:
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"📢 Vị trí hàng đợi: #{old_position} → **#{new_position}**",
                    parse_mode="Markdown"
                )
            except:
                pass


def build_queue_status_message(position: int, total_processing: int) -> str:
    """Build queue status message for user."""
    return (
        f"⏳ **Đang trong hàng chờ**\n\n"
        f"📋 Vị trí của bạn: **#{position:02d}**\n"
        f"👥 Đang xử lý: {total_processing}/{MAX_CONCURRENT_VERIFICATIONS}\n\n"
        f"Hệ thống sẽ tự động xác minh khi đến lượt bạn.\n"
        f"Bạn sẽ nhận được thông báo!"
    )


class QueueWorker:
    """Background worker for queue processing."""
    
    def __init__(self, bot=None):
        self.bot = bot
        self.running = False
    
    async def start(self):
        """Start the worker."""
        self.running = True
        logger.info("QueueWorker started")
        
        while self.running:
            try:
                await process_queue(self.bot)
            except Exception as e:
                logger.exception(f"QueueWorker error: {e}")
            
            await asyncio.sleep(QUEUE_CHECK_INTERVAL_SECONDS)
    
    def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("QueueWorker stopped")


# Singleton instance
_worker_instance: Optional[QueueWorker] = None


def get_queue_worker(bot=None) -> QueueWorker:
    """Get or create queue worker instance."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = QueueWorker(bot)
    return _worker_instance
