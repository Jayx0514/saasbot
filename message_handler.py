import asyncio
import logging
from typing import List, Dict, Any, Optional
from telegram import Bot, Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from utils import global_rate_limiter

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, bot: Bot, target_channels: List[Dict[str, Any]], forward_delay: int):
        self.bot = bot
        self.target_channels = target_channels
        self.forward_delay_ms = forward_delay
        # 移除这里的 start 调用
        # global_rate_limiter.start()

    async def initialize(self):
        """异步初始化方法"""
        await global_rate_limiter.start_async()

    async def forward_message(self, message: Message, keep_forward_origin: bool = False) -> None:
        try:
            logger.info(f"开始转发消息到 {len(self.target_channels)} 个目标频道")
            
            # 检查是否包含会员表情
            has_premium_emoji = False
            if message.entities:
                for entity in message.entities:
                    if hasattr(entity, 'custom_emoji_id') and entity.custom_emoji_id:
                        has_premium_emoji = True
                        break
            if not has_premium_emoji and message.caption_entities:
                for entity in message.caption_entities:
                    if hasattr(entity, 'custom_emoji_id') and entity.custom_emoji_id:
                        has_premium_emoji = True
                        break
            
            # 创建所有转发任务
            tasks = []
            for channel in self.target_channels:
                tasks.append(self._forward_to_channel(message, channel, has_premium_emoji))
            
            # 批量执行任务，每批最多25个
            batch_size = 25
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                await asyncio.gather(*batch)
                # 只在批次之间添加延迟，而不是每个消息之间
                if i + batch_size < len(tasks) and self.forward_delay_ms > 0:
                    await asyncio.sleep(self.forward_delay_ms / 1000)
            
            logger.info("消息转发完成")
        except Exception as e:
            logger.error(f"转发消息失败: {str(e)}")
            
    async def _forward_to_channel(self, message: Message, channel: Dict[str, Any], has_premium_emoji: bool) -> None:
        """转发单个消息到指定频道"""
        try:
            should_proceed, need_delay = await global_rate_limiter.acquire()
            
            if has_premium_emoji:
                # 如果包含会员表情，使用 forward 方法
                await message.forward(
                    chat_id=channel['id'],
                    protect_content=False
                )
            else:
                # 如果不包含会员表情，使用普通发送方法
                if message.text:
                    # 文本消息
                    await self.bot.send_message(
                        chat_id=channel['id'],
                        text=message.text,
                        entities=message.entities
                    )
                elif message.photo:
                    # 图片消息
                    await self.bot.send_photo(
                        chat_id=channel['id'],
                        photo=message.photo[-1].file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities
                    )
                elif message.video:
                    # 视频消息
                    await self.bot.send_video(
                        chat_id=channel['id'],
                        video=message.video.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities
                    )
                elif message.document:
                    # 文档消息
                    await self.bot.send_document(
                        chat_id=channel['id'],
                        document=message.document.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities
                    )
                elif message.audio:
                    # 音频消息
                    await self.bot.send_audio(
                        chat_id=channel['id'],
                        audio=message.audio.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities
                    )
                elif message.voice:
                    # 语音消息
                    await self.bot.send_voice(
                        chat_id=channel['id'],
                        voice=message.voice.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities
                    )
                elif message.sticker:
                    # 贴纸消息
                    await self.bot.send_sticker(
                        chat_id=channel['id'],
                        sticker=message.sticker.file_id
                    )
                
        except Exception as e:
            logger.error(f"转发消息到频道 {channel['id']} 时出错: {str(e)}")

    def update_config(self, target_channels=None, forward_delay=None):
        """更新处理器配置"""
        if target_channels is not None:
            self.target_channels = target_channels
        if forward_delay is not None:
            self.forward_delay_ms = forward_delay

    async def send_media_group(self, messages: List[Message], group_id: str) -> None:
        """批量发送媒体组消息"""
        try:
            if not messages:
                return
                
            logger.info(f"开始批量转发媒体组({len(messages)}条消息)到 {len(self.target_channels)} 个目标频道")
            
            # 为每个目标频道创建转发任务
            tasks = []
            for channel in self.target_channels:
                tasks.append(self._forward_media_group_to_channel(messages, channel))
            
            # 批量执行任务，每批最多25个
            batch_size = max(1, int(29 / len(messages)))
            logger.info(f"根据消息数量({len(messages)}条)计算的批处理大小为: {batch_size}")
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                await asyncio.gather(*batch)
                # 只在批次之间添加延迟，而不是每个消息之间
                if i + batch_size < len(tasks) and self.forward_delay_ms > 0:
                    await asyncio.sleep(self.forward_delay_ms / 1000)
            
            logger.info("媒体组转发完成")
            
        except Exception as e:
            logger.error(f"批量转发媒体组消息时出错: {str(e)}")

    async def _forward_media_group_to_channel(self, messages: List[Message], channel: Dict[str, Any]) -> None:
        """将媒体组作为一个整体转发到指定频道"""
        try:
            # 获取速率限制许可
            should_proceed, need_delay = await global_rate_limiter.acquire()
            
            logger.info(f"正在转发媒体组到频道 {channel['id']}")
            
            # 创建媒体数组
            media_array = []
            for msg in messages:
                if msg.photo:
                    media_array.append(InputMediaPhoto(
                        media=msg.photo[-1].file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    ))
                elif msg.video:
                    media_array.append(InputMediaVideo(
                        media=msg.video.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    ))
                elif msg.document:
                    media_array.append(InputMediaDocument(
                        media=msg.document.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    ))
                elif msg.audio:
                    media_array.append(InputMediaAudio(
                        media=msg.audio.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    ))
            
            # 发送媒体组
            if media_array:
                await self.bot.send_media_group(
                    chat_id=channel['id'],
                    media=media_array
                )
            
        except Exception as e:
            logger.error(f"转发媒体组到频道 {channel['id']} 时出错: {str(e)}")