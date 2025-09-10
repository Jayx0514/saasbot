import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Optional
import pytz

from telegram import Bot
from api_data_reader import ApiDataReader, ApiDataSender
from scheduler import Scheduler
from config_loader import ConfigLoader
from google_sheets_writer import GoogleSheetsWriter

logger = logging.getLogger(__name__)

class ApiDataSenderManager:
    def __init__(self, bot: Bot):
        """初始化 API 数据发送管理器
        
        Args:
            bot: Telegram Bot 实例
        """
        self.bot = bot
        self.config_loader = ConfigLoader()
        self.scheduler = Scheduler()
        
        # 初始化 API 数据读取器
        self.api_reader = ApiDataReader(
            api_url='',  # 不再使用配置文件中的url
            api_token='',  # 不再使用配置文件中的token
            config_loader=self.config_loader
        )
        
        # 初始化数据发送器
        self.data_sender = ApiDataSender(bot, self.config_loader)
        
        # 初始化Google表格写入器
        self.sheets_writer = GoogleSheetsWriter(self.config_loader)
    
    async def initialize(self):
        """初始化管理器"""
        # 启动调度器
        await self.scheduler.start()
        
        # 设置定时任务
        self._setup_tasks()
        
        logger.info("API 数据发送管理器初始化完成")
        return True
    
    async def stop(self):
        """停止管理器"""
        await self.scheduler.stop()
        logger.info("API 数据发送管理器已停止")
    
    def update_config(self, config_loader):
        """更新配置加载器
        
        Args:
            config_loader: 新的配置加载器实例
        """
        self.config_loader = config_loader
        # 更新现有 API 数据读取器的配置，而不是重新创建实例
        self.api_reader.config_loader = self.config_loader
        # 重新初始化数据发送器
        self.data_sender = ApiDataSender(self.bot, self.config_loader)
        
        # 重新初始化Google表格写入器
        self.sheets_writer = GoogleSheetsWriter(self.config_loader)
        logger.info("ApiDataSenderManager 配置已更新")
    
    def _setup_tasks(self):
        """设置定时任务"""
        data_sending_config = self.config_loader.get_api_data_sending_config()
        
        # 设置时报任务
        hourly_config = data_sending_config.get('hourly_report', {})
        if hourly_config.get('enabled', False):
            interval_minutes = hourly_config.get('interval_minutes', 30)
            report_type = hourly_config.get('report_type', 0)
            
            self.scheduler.add_interval_task(
                'api_hourly_report',
                interval_minutes,
                self._send_hourly_report,
                report_type
            )
            logger.info(f"已设置 API 时报任务，间隔 {interval_minutes} 分钟，报表类型: {report_type}")
        
        # 设置日报任务
        daily_config = data_sending_config.get('daily_report', {})
        if daily_config.get('enabled', False):
            send_time = daily_config.get('send_time', '18:00')
            report_type = daily_config.get('report_type', 0)
            
            # 解析发送时间（印度时区）
            try:
                # 处理不同的时间格式
                if isinstance(send_time, str):
                    # 字符串格式，如 "05:45"
                    hour, minute = map(int, send_time.split(':'))
                elif isinstance(send_time, (int, float)):
                    # 数字格式，如 5.75 表示 5:45
                    total_minutes = int(send_time * 60)
                    hour = total_minutes // 60
                    minute = total_minutes % 60
                else:
                    logger.error(f"不支持的时间格式: {send_time}")
                    return
                
                # 将印度时区时间转换为UTC时间
                india_tz = pytz.timezone('Asia/Kolkata')
                utc_tz = pytz.UTC
                
                # 创建印度时区的datetime对象
                india_time = india_tz.localize(datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0))
                # 转换为UTC时间
                utc_time = india_time.astimezone(utc_tz)
                
                logger.info(f"配置的印度时区时间: {hour:02d}:{minute:02d}")
                logger.info(f"转换后的UTC时间: {utc_time.hour:02d}:{utc_time.minute:02d}")
                logger.info(f"当前UTC时间: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')}")
                
                self.scheduler.add_daily_task(
                    'api_daily_report',
                    utc_time.hour,
                    utc_time.minute,
                    self._send_daily_report,
                    report_type
                )
                logger.info(f"已设置 API 日报任务，印度时区时间 {hour:02d}:{minute:02d} (UTC时间 {utc_time.hour:02d}:{utc_time.minute:02d})，报表类型: {report_type}")
            except Exception as e:
                logger.error(f"设置 API 日报任务失败: {str(e)}")
                logger.error(f"错误详情: {str(e)}", exc_info=True)
    
    async def _send_hourly_report(self, report_type: int):
        """处理时报数据（写入Google表格）
        
        Args:
            report_type: 报表类型
        """
        try:
            logger.info(f"开始处理 API 时报数据，报表类型: {report_type}")
            
            # 获取印度时区的当前日期
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            today = india_now.strftime('%Y-%m-%d')
            logger.info(f"印度时区当前日期: {today}")
            
            # 获取所有渠道数据
            logger.info("查询所有渠道数据")
            data_list = await self.api_reader.read_data(today, report_type)
                
            if not data_list:
                logger.warning("API 数据为空")
                return
            
            logger.info(f"获取到 {len(data_list)} 条数据，开始写入Google表格")
            
            # 只写入Google表格，不发送群内消息
            await self._write_hourly_data_to_sheets(data_list)
        
        except Exception as e:
            logger.error(f"处理 API 时报时出错: {str(e)}")
    
    async def _send_daily_report(self, report_type: int):
        """处理日报数据（写入Google表格）
        
        Args:
            report_type: 报表类型
        """
        try:
            logger.info(f"开始处理 API 日报数据，报表类型: {report_type}")
            
            # 获取印度时区的昨天日期（日报发送昨天的数据）
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            india_yesterday = india_now - timedelta(days=1)
            yesterday = india_yesterday.strftime('%Y-%m-%d')
            logger.info(f"印度时区昨天日期: {yesterday}")
            
            # 获取所有渠道数据
            logger.info("查询所有渠道数据")
            data_list = await self.api_reader.read_data(yesterday, report_type)
                
            if not data_list:
                logger.warning("API 数据为空")
                return
            
            logger.info(f"获取到 {len(data_list)} 条数据，开始写入Google表格")
            
            # 只写入Google表格，不发送群内消息
            await self._write_daily_data_to_sheets(data_list)
        
        except Exception as e:
            logger.error(f"处理 API 日报时出错: {str(e)}")
    
    async def _write_daily_data_to_sheets(self, data_list: List[Dict[str, Any]]):
        """将日报数据写入Google表格
        
        Args:
            data_list: 数据列表
        """
        try:
            if not data_list:
                logger.warning("日报数据为空，跳过Google表格写入")
                return
            
            # 获取群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置，跳过Google表格写入")
                return
            
            # 按群组分组数据
            group_data_map = {}
            for data in data_list:
                channel_source = data.get('channel', '')
                if not channel_source:
                    continue
                
                # 查找包含该渠道的群组
                for group_name, group_config in groups_config.items():
                    channel_ids = group_config.get('channel_ids', [])
                    for channel_config in channel_ids:
                        channel_id = channel_config.get('id', '')
                        if channel_id == channel_source:
                            # 检查是否有Google表格配置
                            spreadsheet_id = self.config_loader.get_group_spreadsheet_id(group_name)
                            if spreadsheet_id:
                                if group_name not in group_data_map:
                                    group_data_map[group_name] = {
                                        'config': group_config,
                                        'data_list': []
                                    }
                                group_data_map[group_name]['data_list'].append(data)
                            break
            
            # 写入每个群组的数据
            for group_name, group_info in group_data_map.items():
                group_config = group_info['config']
                group_data_list = group_info['data_list']
                
                spreadsheet_id = self.config_loader.get_group_spreadsheet_id(group_name)
                daily_sheet_name = self.config_loader.get_daily_sheet_name()
                
                # 确保工作表存在
                await self.sheets_writer.create_sheet_if_not_exists(spreadsheet_id, daily_sheet_name)
                
                # 确保表头存在
                await self.sheets_writer.ensure_sheet_headers(spreadsheet_id, daily_sheet_name)
                
                # 写入数据
                success = await self.sheets_writer.write_daily_data(
                    spreadsheet_id, 
                    daily_sheet_name, 
                    group_data_list, 
                    group_config.get('name', group_name)
                )
                
                if success:
                    logger.info(f"群组 {group_name} 的日报数据已成功写入Google表格")
                else:
                    logger.error(f"群组 {group_name} 的日报数据写入Google表格失败")
        
        except Exception as e:
            logger.error(f"写入日报数据到Google表格时出错: {str(e)}")
    
    async def _write_hourly_data_to_sheets(self, data_list: List[Dict[str, Any]]):
        """将时报数据写入Google表格
        
        Args:
            data_list: 数据列表
        """
        try:
            if not data_list:
                logger.warning("时报数据为空，跳过Google表格写入")
                return
            
            # 获取群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置，跳过Google表格写入")
                return
            
            # 按群组分组数据
            group_data_map = {}
            for data in data_list:
                channel_source = data.get('channel', '')
                if not channel_source:
                    continue
                
                # 查找包含该渠道的群组
                for group_name, group_config in groups_config.items():
                    channel_ids = group_config.get('channel_ids', [])
                    for channel_config in channel_ids:
                        channel_id = channel_config.get('id', '')
                        if channel_id == channel_source:
                            # 检查是否有Google表格配置
                            spreadsheet_id = self.config_loader.get_group_spreadsheet_id(group_name)
                            if spreadsheet_id:
                                if group_name not in group_data_map:
                                    group_data_map[group_name] = {
                                        'config': group_config,
                                        'data_list': []
                                    }
                                group_data_map[group_name]['data_list'].append(data)
                            break
            
            # 写入每个群组的数据
            for group_name, group_info in group_data_map.items():
                group_config = group_info['config']
                group_data_list = group_info['data_list']
                
                spreadsheet_id = self.config_loader.get_group_spreadsheet_id(group_name)
                hourly_sheet_name = self.config_loader.get_hourly_sheet_name()
                
                # 确保工作表存在
                await self.sheets_writer.create_sheet_if_not_exists(spreadsheet_id, hourly_sheet_name)
                
                # 确保表头存在
                await self.sheets_writer.ensure_sheet_headers(spreadsheet_id, hourly_sheet_name)
                
                # 写入数据
                success = await self.sheets_writer.write_hourly_data(
                    spreadsheet_id, 
                    hourly_sheet_name, 
                    group_data_list, 
                    group_config.get('name', group_name)
                )
                
                if success:
                    logger.info(f"群组 {group_name} 的时报数据已成功写入Google表格")
                else:
                    logger.error(f"群组 {group_name} 的时报数据写入Google表格失败")
        
        except Exception as e:
            logger.error(f"写入时报数据到Google表格时出错: {str(e)}")
    
    async def _send_hourly_notification(self) -> bool:
        """发送时报通知
        
        Returns:
            是否发送成功
        """
        try:
            # 获取所有群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置")
                return False
            
            # 获取印度时区的当前时间
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            
            # 发送通知到所有群组
            total_sent = 0
            for group_name, group_config in groups_config.items():
                tg_group = group_config.get('tg_group', '')
                if tg_group:
                    try:
                        chat_id = int(tg_group)
                        message = f"📊 时报已更新表格\n⏰ 更新时间：{current_time}\n📋 数据已写入Google表格"
                        
                        await self.bot.send_message(chat_id=chat_id, text=message)
                        total_sent += 1
                        logger.info(f"已发送时报通知到群组 {group_name} ({chat_id})")
                        
                        # 添加发送间隔
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"发送时报通知到群组 {group_name} 失败: {str(e)}")
            
            logger.info(f"时报通知发送完成，共发送到 {total_sent} 个群组")
            return total_sent > 0
            
        except Exception as e:
            logger.error(f"发送时报通知时出错: {str(e)}")
            return False
    
    async def _send_daily_notification(self) -> bool:
        """发送日报通知
        
        Returns:
            是否发送成功
        """
        try:
            # 获取所有群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置")
                return False
            
            # 获取印度时区的当前时间
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            
            # 发送通知到所有群组
            total_sent = 0
            for group_name, group_config in groups_config.items():
                tg_group = group_config.get('tg_group', '')
                if tg_group:
                    try:
                        chat_id = int(tg_group)
                        message = f"📊 日报已更新表格\n⏰ 更新时间：{current_time}\n📋 数据已写入Google表格"
                        
                        await self.bot.send_message(chat_id=chat_id, text=message)
                        total_sent += 1
                        logger.info(f"已发送日报通知到群组 {group_name} ({chat_id})")
                        
                        # 添加发送间隔
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"发送日报通知到群组 {group_name} 失败: {str(e)}")
            
            logger.info(f"日报通知发送完成，共发送到 {total_sent} 个群组")
            return total_sent > 0
            
        except Exception as e:
            logger.error(f"发送日报通知时出错: {str(e)}")
            return False