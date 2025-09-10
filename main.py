import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, Optional

from api_data_sender_manager import ApiDataSenderManager

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

from config_loader import ConfigLoader
from auth_manager import AuthManager
  
from admin_handler import AdminHandler
from user_command_handler import UserCommandHandler
from utils import AdminState, get_channel_id

# 创建logs目录（如果不存在）
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

def setup_logger() -> None:
    """配置日志系统"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 检查是否已经有处理器，避免重复添加
    if not logger.handlers:
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # 添加文件处理器
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, 'bot.log'),
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

setup_logger()
logger = logging.getLogger(__name__)

from telegram import Bot
from telegram.request import HTTPXRequest

class TelegramForwarderBot:
    _instance: Optional['TelegramForwarderBot'] = None
    _bot: Optional[Bot] = None
    
    def __new__(cls):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化机器人"""
        if hasattr(self, 'config_loader'):
            return
            
        self.config_loader = ConfigLoader()
        self.auth_manager = AuthManager(self.config_loader)
        self.bot_token = self.config_loader.get_bot_token()
        self.forward_delay = self.config_loader.get_forward_delay()
        self.admins = self.config_loader.get_admins()
        self.admin_state = AdminState()
        
        # 存储API token
        self.api_token = None

        # 初始化共享的 Bot 实例，配置连接池
        if not TelegramForwarderBot._bot:
            # 创建自定义请求对象，配置连接池
            request = HTTPXRequest(
                connection_pool_size=32,  # 增加连接池大小
                pool_timeout=10.0,        # 增加池超时时间
                connect_timeout=20.0,     # 连接超时
                read_timeout=20.0         # 读取超时
            )
            TelegramForwarderBot._bot = Bot(self.bot_token, request=request)
        
        # 初始化 API 数据发送管理器
        self.api_data_sender_manager = ApiDataSenderManager(TelegramForwarderBot._bot)
        
        # 初始化用户命令处理器
        self.user_command_handler = UserCommandHandler(self.config_loader)
        
        # 初始化管理员处理器，传递所有必要的组件
        self.admin_handler = AdminHandler(
            self.config_loader, 
            self.admin_state, 
            self.user_command_handler,
            self.api_data_sender_manager
        )
    
    async def get_api_token(self) -> Optional[str]:
        """获取API token，如果没有则重新登录"""
        try:
            if not self.api_token:
                logger.info("正在获取API token...")
                self.api_token = self.auth_manager.login_and_get_token()
                if self.api_token:
                    logger.info("API token获取成功")
                else:
                    logger.error("API token获取失败")
            return self.api_token
        except Exception as e:
            logger.error(f"获取API token时出错: {str(e)}")
            return None
    
    async def refresh_api_token(self) -> Optional[str]:
        """刷新API token"""
        try:
            logger.info("正在刷新API token...")
            self.auth_manager.clear_token_cache()
            self.api_token = None
            return await self.get_api_token()
        except Exception as e:
            logger.error(f"刷新API token时出错: {str(e)}")
            return None
    
    async def get_package_list(self) -> Optional[dict]:
        """获取包列表数据"""
        try:
            logger.info("正在获取包列表数据...")
            
            # 准备请求参数
            request_data = {
                "sortField": "id",
                "orderBy": "Desc",
                "pageNo": 1,
                "pageSize": 1000
            }
            
            # 使用认证管理器发送带认证和验签的请求
            response = AuthManager.send_authenticated_request(
                endpoint='/api/Package/GetPageList',
                data=request_data,
                method='POST',
                config_loader=self.config_loader
            )
            
            if 'error' not in response and response.get('status_code') == 200:
                logger.info("包列表获取成功")
                return response.get('response')
            else:
                logger.error(f"包列表获取失败: {response}")
                return None
                
        except Exception as e:
            logger.error(f"获取包列表时出错: {str(e)}")
            return None
    
    async def get_package_analysis(self, start_date: str, end_date: str) -> Optional[dict]:
        """获取包分析数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        try:
            logger.info(f"正在获取包分析数据: {start_date} 到 {end_date}")
            
            # 准备请求参数
            request_data = {
                "startTime": start_date,
                "endTime": end_date,
                "pageNo": 1,
                "pageSize": 1000,
                "orderBy": "Desc"
            }
            
            # 使用认证管理器发送带认证和验签的请求
            response = AuthManager.send_authenticated_request(
                endpoint='/api/RptDataAnalysis/GetPackageAnalysis',
                data=request_data,
                method='POST',
                config_loader=self.config_loader
            )
            
            if 'error' not in response and response.get('status_code') == 200:
                logger.info("包分析数据获取成功")
                return response.get('response')
            else:
                logger.error(f"包分析数据获取失败: {response}")
                return None
                
        except Exception as e:
            logger.error(f"获取包分析数据时出错: {str(e)}")
            return None
    
    def get_india_date(self, days_offset: int = 0) -> str:
        """获取印度时区的日期字符串
        
        Args:
            days_offset: 日期偏移量，0为今天，-1为昨天，1为明天
            
        Returns:
            印度时区的日期字符串，格式为 YYYY-MM-DD
        """
        import pytz
        from datetime import datetime, timedelta
        
        # 印度时区
        india_tz = pytz.timezone('Asia/Kolkata')
        india_now = datetime.now(india_tz)
        
        # 应用偏移量
        if days_offset != 0:
            india_now = india_now + timedelta(days=days_offset)
        
        return india_now.strftime('%Y-%m-%d')
    
    async def process_package_data(self, target_date: str = None) -> Optional[list]:
        """处理包数据，匹配配置中的渠道并生成表格数据
        
        Args:
            target_date: 目标日期，如果为None则使用印度时区的当天
            
        Returns:
            处理后的数据列表
        """
        try:
            if not target_date:
                target_date = self.get_india_date()
            
            logger.info(f"开始处理包数据，目标日期: {target_date}")
            
            # 1. 获取包列表，建立ID和包名的对应关系
            package_list_response = await self.get_package_list()
            if not package_list_response or 'data' not in package_list_response:
                logger.error("无法获取包列表数据")
                return None
            
            # 建立ID到包名的映射
            id_to_package_name = {}
            package_list = package_list_response['data'].get('list', [])
            for package in package_list:
                package_id = package.get('id')
                package_name = package.get('channelPackageName')
                if package_id is not None and package_name:
                    id_to_package_name[package_id] = package_name
            
            logger.info(f"建立了 {len(id_to_package_name)} 个包的ID映射关系")
            
            # 2. 获取包分析数据
            analysis_response = await self.get_package_analysis(target_date, target_date)
            if not analysis_response or 'data' not in analysis_response:
                logger.error("无法获取包分析数据")
                return None
            
            analysis_list = analysis_response['data'].get('list', [])
            logger.info(f"获取到 {len(analysis_list)} 条分析数据")
            
            # 3. 获取配置中的渠道列表
            groups_config = self.config_loader.get_groups_config()
            target_channels = set()
            for group_name, group_config in groups_config.items():
                channel_ids = group_config.get('channel_ids', [])
                for channel_config in channel_ids:
                    channel_id = channel_config.get('id', '')
                    if channel_id:
                        target_channels.add(channel_id)
            
            logger.info(f"配置中的目标渠道: {target_channels}")
            
            # 4. 匹配数据并生成表格
            matched_data = []
            for analysis_item in analysis_list:
                package_id = analysis_item.get('packageId')
                package_name = analysis_item.get('packageName', '')
                
                # 如果packageId存在于映射中，使用映射的名称，否则使用原始名称
                if package_id in id_to_package_name:
                    mapped_package_name = id_to_package_name[package_id]
                    logger.info(f"包ID {package_id} 映射: {package_name} -> {mapped_package_name}")
                    package_name = mapped_package_name
                
                # 检查是否匹配配置中的渠道
                if package_name in target_channels:
                    # 按照要求的字段映射生成数据
                    formatted_data = {
                        'date': target_date,
                        'channel': package_name,  # 渠道packageName
                        'register': analysis_item.get('newMemberCount', 0),  # 新增注册用户newMemberCount
                        'new_charge_user': analysis_item.get('newMemberRechargeCount', 0),  # 新增付费用户newMemberRechargeCount
                        'new_charge': analysis_item.get('newMemberLoginCount', 0),  # 新增付费金额newMemberLoginCount
                        'charge_total': analysis_item.get('rechargeAmount', 0),  # 总充值金额rechargeAmount
                        'withdraw_total': analysis_item.get('withdrawAmount', 0),  # 总提现金额withdrawAmount
                        'charge_withdraw_diff': analysis_item.get('chargeWithdrawDiff', 0)  # 充提差chargeWithdrawDiff
                    }
                    matched_data.append(formatted_data)
                    logger.info(f"匹配到渠道数据: {package_name}")
            
            logger.info(f"最终匹配到 {len(matched_data)} 条数据")
            return matched_data
            
        except Exception as e:
            logger.error(f"处理包数据时出错: {str(e)}")
            return None

    
    async def start(self) -> None:
        """启动机器人"""
        application = Application.builder().token(self.bot_token).build()
        
        # 注册处理器
        self._register_handlers(application)
        
        # 启动应用
        await self._start_application(application)
    
    def _register_handlers(self, application: Application) -> None:
        """注册所有消息处理器"""
        logger.info("开始注册所有消息处理器...")
        
        # 注册命令处理器
        logger.info("注册管理员命令处理器...")
        application.add_handler(CommandHandler("start", self.admin_handler.handle_start_command, filters=filters.ChatType.PRIVATE))
        application.add_handler(CommandHandler("getid", self.handle_get_id_command))
        application.add_handler(CommandHandler("reload", self.handle_reload_command))
        
        # 注册用户命令处理器
        logger.info("注册用户命令处理器...")
        application.add_handler(CommandHandler("today", self.user_command_handler.handle_today_command))
        application.add_handler(CommandHandler("yesterday", self.user_command_handler.handle_yesterday_command))
        logger.info("用户命令处理器注册完成: today, yesterday")
        
        # 注册回调查询处理器 - 确保它在其他处理器之前
        logger.info("注册回调查询处理器...")
        application.add_handler(CallbackQueryHandler(self.admin_handler.handle_callback_query))
        
        # 注册错误处理器
        logger.info("注册错误处理器...")
        application.add_error_handler(self._error_handler)
        
        # 注册私聊消息处理器
        logger.info("注册私聊消息处理器...")
        application.add_handler(MessageHandler(
            filters.FORWARDED & filters.ChatType.PRIVATE,
            self.handle_forwarded_message
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            self.handle_admin_message
        ))
        
        # 添加一个捕获所有命令的处理器（用于调试）
        logger.info("注册命令调试处理器...")
        application.add_handler(MessageHandler(
            filters.COMMAND,
            self._debug_command_handler
        ))
        
        logger.info("所有消息处理器注册完成!")
        
    
    async def _start_application(self, application: Application) -> None:
        """启动应用并处理异常"""
        try:
            await application.initialize()
            await application.start()
            logger.info("机器人已启动")
            
            # 启动全局速率限制器
            from utils import global_rate_limiter
            await global_rate_limiter.start_async()
            
            # 初始化完成，准备开始服务
            logger.info("系统初始化完成，准备开始服务")

                
            # 初始化数据发送管理器
            if hasattr(self, 'data_sender_manager'):
                success = await self.data_sender_manager.initialize()
                if success:
                    logger.info("数据发送管理器初始化成功")
                else:
                    logger.error("数据发送管理器初始化失败")
                    
            # 初始化 API 数据发送管理器
            if hasattr(self, 'api_data_sender_manager'):
                success = await self.api_data_sender_manager.initialize()
                if success:
                    logger.info("API 数据发送管理器初始化成功")
                else:
                    logger.error("API 数据发送管理器初始化失败")
            
            await application.updater.start_polling()
            stop_signal = asyncio.Event()
            await stop_signal.wait()
            
        except (KeyboardInterrupt, SystemExit):
            logger.info("机器人正在关闭...")
        except Exception as e:
            logger.error(f"启动机器人时出错: {str(e)}")
        finally:
            # 停止全局速率限制器
            from utils import global_rate_limiter
            await global_rate_limiter.stop_async()
            
            # 停止数据发送管理器
            if hasattr(self, 'data_sender_manager'):
                await self.data_sender_manager.stop()
                logger.info("数据发送管理器已停止")
                
            # 停止 API 数据发送管理器
            if hasattr(self, 'api_data_sender_manager'):
                await self.api_data_sender_manager.stop()
                logger.info("API 数据发送管理器已停止")
            
            await application.stop()

    async def _debug_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """调试处理器，捕获所有更新"""
        logger.info("=== 调试处理器 ===")
        logger.info(f"更新类型: {type(update)}")
        logger.info(f"是否有回调查询: {update.callback_query is not None}")
        if update.callback_query:
            logger.info(f"回调查询数据: {update.callback_query.data}")
        if update.message:
            logger.info(f"消息文本: {update.message.text}")
        logger.info("=== 调试处理器结束 ===")
    
    async def _debug_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """调试命令处理器，记录所有接收到的命令"""
        try:
            logger.info("=== 命令调试处理器触发 ===")
            
            if update.message and update.message.text:
                command_text = update.message.text
                logger.info(f"接收到命令: '{command_text}'")
                
                if update.effective_chat:
                    logger.info(f"命令来源聊天: ID={update.effective_chat.id}, Type={update.effective_chat.type}")
                
                if update.effective_user:
                    logger.info(f"命令发送用户: ID={update.effective_user.id}, Username={update.effective_user.username}")
                
                # 检查是否是 today 或 yesterday 命令
                if command_text.strip().lower() in ['/today', '/yesterday']:
                    logger.warning(f"检测到 {command_text} 命令，但没有被专用处理器处理！这可能表明处理器注册有问题。")
                    logger.info("列出当前所有注册的处理器...")
                    
                    # 尝试列出处理器信息
                    if context.application and hasattr(context.application, 'handlers'):
                        logger.info(f"当前注册的处理器数量: {len(context.application.handlers)}")
                        for i, handler_group in enumerate(context.application.handlers.values()):
                            logger.info(f"处理器组 {i}: {len(handler_group)} 个处理器")
                            for j, handler in enumerate(handler_group):
                                logger.info(f"  处理器 {i}-{j}: {type(handler)} - {handler}")
                
            logger.info("=== 命令调试处理器结束 ===")
            
        except Exception as e:
            logger.error(f"命令调试处理器出错: {str(e)}", exc_info=True)
    
    async def _handle_today_command_wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """包装 /today 命令处理器，添加详细日志"""
        try:
            logger.info("=== /today 命令接收 ===")
            logger.info(f"Update 对象: {update}")
            logger.info(f"Message: {update.message}")
            logger.info(f"Effective Chat: {update.effective_chat}")
            logger.info(f"Effective User: {update.effective_user}")
            
            if update.effective_chat:
                logger.info(f"Chat ID: {update.effective_chat.id}, Chat Type: {update.effective_chat.type}")
            
            if update.effective_user:
                logger.info(f"User ID: {update.effective_user.id}, Username: {update.effective_user.username}")
            
            if update.message:
                logger.info(f"Message Text: '{update.message.text}', Message ID: {update.message.message_id}")
            
            logger.info("准备调用 handle_today_command...")
            
            # 调用实际的处理器
            await self.user_command_handler.handle_today_command(update, context)
            
            logger.info("/today 命令处理完成")
            
        except Exception as e:
            logger.error(f"/today 命令包装器中发生异常: {str(e)}", exc_info=True)
            try:
                if update.message:
                    await update.message.reply_text("❌ 处理命令时发生内部错误，请稍后重试")
            except:
                logger.error("发送错误消息失败")
    
    async def _handle_yesterday_command_wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """包装 /yesterday 命令处理器，添加详细日志"""
        try:
            logger.info("=== /yesterday 命令接收 ===")
            logger.info(f"Update 对象: {update}")
            logger.info(f"Message: {update.message}")
            logger.info(f"Effective Chat: {update.effective_chat}")
            logger.info(f"Effective User: {update.effective_user}")
            
            if update.effective_chat:
                logger.info(f"Chat ID: {update.effective_chat.id}, Chat Type: {update.effective_chat.type}")
            
            if update.effective_user:
                logger.info(f"User ID: {update.effective_user.id}, Username: {update.effective_user.username}")
            
            if update.message:
                logger.info(f"Message Text: '{update.message.text}', Message ID: {update.message.message_id}")
            
            logger.info("准备调用 handle_yesterday_command...")
            
            # 调用实际的处理器
            await self.user_command_handler.handle_yesterday_command(update, context)
            
            logger.info("/yesterday 命令处理完成")
            
        except Exception as e:
            logger.error(f"/yesterday 命令包装器中发生异常: {str(e)}", exc_info=True)
            try:
                if update.message:
                    await update.message.reply_text("❌ 处理命令时发生内部错误，请稍后重试")
            except:
                logger.error("发送错误消息失败")
                
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理所有未捕获的异常"""
        logger.error(f"=== 全局错误处理器触发 ===")
        logger.error(f"未捕获的异常: {context.error}")
        logger.error(f"异常类型: {type(context.error)}")
        logger.error(f"更新对象: {update}")
        
        if update.message:
            logger.error(f"消息文本: {update.message.text}")
            logger.error(f"消息ID: {update.message.message_id}")
            
        if update.effective_chat:
            logger.error(f"聊天ID: {update.effective_chat.id}")
            logger.error(f"聊天类型: {update.effective_chat.type}")
            
        if update.effective_user:
            logger.error(f"用户ID: {update.effective_user.id}")
            
        if update.callback_query:
            logger.error(f"回调查询数据: {update.callback_query.data}")
            
        # 尝试记录完整的异常堆栈
        import traceback
        logger.error(f"完整异常堆栈: {traceback.format_exc()}")
    
    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理管理员消息"""
        if not update.effective_user:
            return
            
        user_id = update.effective_user.id
        if not self.admin_handler.is_admin(user_id):
            return
            
        # 将所有状态处理逻辑委托给 admin_handler
        await self.admin_handler.handle_admin_message(update, context)
    
    async def handle_forwarded_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理转发的消息以获取来源信息"""
        if not update.message:
            return
            
        # 检查是否为转发消息
        if not (hasattr(update.message, 'forward_origin') and update.message.forward_origin):
            return
            
        try:
            info = []
            info.append("📝 消息来源信息:")
            
            # 获取转发来源信息
            origin = update.message.forward_origin
            origin_type = origin.type
            
            if origin_type == 'channel':
                info.append(f"\n📢 来源:")
                info.append(f"类型: 频道")
                info.append(f"ID: {origin.chat.id}")
                info.append(f"名称: {origin.chat.title or '未知'}")
                if hasattr(origin, 'message_id'):
                    info.append(f"消息ID: {origin.message_id}")
                
            elif origin_type == 'user':
                info.append(f"\n👤 发送者:")
                info.append(f"ID: {origin.sender_user.id}")
                if origin.sender_user.username:
                    info.append(f"用户名: @{origin.sender_user.username}")
                info.append(f"名称: {origin.sender_user.first_name}")
                
            elif origin_type == 'hidden_user':
                info.append(f"\n👤 发送者: {origin.sender_user_name}")  # 修改这里，使用 sender_user_name 而不是 sender_name
                info.append("(用户已启用隐私设置)")
                
            elif origin_type == 'chat':
                info.append(f"\n👥 来源:")
                info.append(f"类型: 群组")
                info.append(f"ID: {origin.chat.id}")
                info.append(f"名称: {origin.chat.title}")
            
            # 获取转发时间（从 origin 对象获取）
            if hasattr(origin, 'date'):
                info.append(f"\n⏰ 转发时间: {origin.date}")
            
            # 发送信息
            if info:
                await update.message.reply_text("\n".join(info))
            else:
                await update.message.reply_text("❌ 无法获取消息来源信息")
            
        except Exception as e:
            logger.error(f"处理转发消息时出错: {str(e)}")
            await update.message.reply_text("❌ 处理消息时出现错误")
        
        if not update.effective_user or not self.admin_handler.is_admin(update.effective_user.id):
            return
        
        channel_id = await get_channel_id(update)
        if channel_id:
            await update.message.reply_text(f"频道ID: {channel_id}")
        else:
            await update.message.reply_text("无法获取频道ID，请确保转发的消息来自频道。")

    async def handle_get_id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /getid 命令"""
        if not update.message:
            return
            
        info = []
        info.append("🆔 ID信息:")
        
        # 获取用户信息
        if update.effective_user:
            info.append(f"\n👤 您的用户信息:")
            info.append(f"用户ID: {update.effective_user.id}")
            if update.effective_user.username:
                info.append(f"用户名: @{update.effective_user.username}")
            info.append(f"名称: {update.effective_user.first_name}")
        
        # 获取聊天信息
        if update.effective_chat:
            chat = update.effective_chat
            info.append(f"\n💭 当前聊天信息:")
            info.append(f"类型: {chat.type}")
            info.append(f"ID: {chat.id}")
            if chat.title:
                info.append(f"名称: {chat.title}")
        
        # 如果是回复消息，获取被回复消息的信息
        if update.message.reply_to_message:
            reply_msg = update.message.reply_to_message
            info.append(f"\n↩️ 回复消息信息:")
            info.append(f"消息ID: {reply_msg.message_id}")
            if reply_msg.forward_origin:
                origin = reply_msg.forward_origin
                info.append("转发来源:")
                if origin.type == 'channel':
                    info.append(f"频道ID: {origin.chat.id}")
                    info.append(f"频道名称: {origin.chat.title}")
                elif origin.type == 'user':
                    info.append(f"用户ID: {origin.sender_user.id}")
                elif origin.type == 'chat':
                    info.append(f"群组ID: {origin.chat.id}")
        
        await update.message.reply_text("\n".join(info))


    async def handle_reload_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /reload 命令，重新加载配置"""
        if not update.effective_user:
            return
            
        if not self.admin_handler.is_admin(update.effective_user.id):
            await update.message.reply_text("⚠️ 您没有权限执行此操作")
            return
            
        try:
            # 获取应用实例
            application = context.application
            
            # 移除所有现有的处理器
            logger.info("清除所有现有的处理器...")
            application.handlers.clear()
            logger.info(f"处理器清除完成，当前处理器数量: {len(application.handlers)}")
            
            # 重新加载配置
            logger.info("重新加载配置文件...")
            self.config_loader.reload_config()
            
            # 更新机器人配置
            logger.info("更新机器人配置...")
            self.forward_delay = self.config_loader.get_forward_delay()
            self.admins = self.config_loader.get_admins()
            
            # 更新管理员处理器的配置
            logger.info("更新管理员处理器配置...")
            self.admin_handler.update_config(self.config_loader)
            
            # 更新用户命令处理器的配置
            logger.info("更新用户命令处理器配置...")
            self.user_command_handler.update_config(self.config_loader)
            
            # 重新注册所有处理器
            logger.info("重新注册所有处理器...")
            self._register_handlers(application)
            logger.info(f"处理器重新注册完成，当前处理器数量: {len(application.handlers)}")
            

            
            # 重新初始化 API 数据发送管理器
            if hasattr(self, 'api_data_sender_manager'):
                await self.api_data_sender_manager.stop()
                self.api_data_sender_manager = ApiDataSenderManager(TelegramForwarderBot._bot)
                success = await self.api_data_sender_manager.initialize()
                if success:
                    logger.info("API 数据发送管理器重新初始化成功")
                else:
                    logger.error("API 数据发送管理器重新初始化失败")
            
            await update.message.reply_text("✅ 配置已成功重新加载")
            logger.info(f"配置已被管理员 {update.effective_user.id} 重新加载")
            
        except Exception as e:
            error_message = f"❌ 重新加载配置时出错: {str(e)}"
            logger.error(error_message)
            await update.message.reply_text(error_message)

if __name__ == "__main__":
    bot = TelegramForwarderBot()
    asyncio.run(bot.start())
