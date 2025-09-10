#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户命令处理器

处理目标群组中用户的命令：
- /today: 发送当天的时报数据
- /yesterday: 发送昨天的日报数据
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import pytz

from telegram import Update
from telegram.ext import ContextTypes

from config_loader import ConfigLoader
from api_data_reader import ApiDataReader, ApiDataSender
from google_sheets_writer import GoogleSheetsWriter

logger = logging.getLogger(__name__)

class UserCommandHandler:
    def __init__(self, config_loader: ConfigLoader):
        """初始化用户命令处理器
        
        Args:
            config_loader: 配置加载器实例
        """
        self.config_loader = config_loader
        
        # 初始化 API 数据读取器
        self.api_reader = ApiDataReader(
            api_url='',  # 不再使用配置文件中的url
            api_token='',  # 不再使用配置文件中的token
            config_loader=self.config_loader
        )
        
        # 初始化Google表格写入器
        self.sheets_writer = GoogleSheetsWriter(self.config_loader)
    
    def update_config(self, config_loader: ConfigLoader):
        """更新配置加载器
        
        Args:
            config_loader: 新的配置加载器实例
        """
        self.config_loader = config_loader
        
        # 重新创建 API 数据读取器实例，避免状态污染
        logger.info("重新创建ApiDataReader实例以避免状态污染")
        self.api_reader = ApiDataReader(
            api_url='',  # 不再使用配置文件中的url
            api_token='',  # 不再使用配置文件中的token
            config_loader=self.config_loader
        )
        
        # 重新创建Google表格写入器
        self.sheets_writer = GoogleSheetsWriter(self.config_loader)
        logger.info("UserCommandHandler 配置已更新")
    
    async def handle_today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /today 命令 - 发送当天的时报数据"""
        logger.info("=== 进入 handle_today_command 函数 ===")
        logger.info(f"接收到的参数 - update: {update}, context: {context}")
        
        if not update:
            logger.error("Update 对象为空!")
            return
            
        if not update.message:
            logger.warning("update.message 为空!")
            return
            
        if not update.effective_chat:
            logger.warning("update.effective_chat 为空!")
            return
            
        logger.info("所有必要的对象验证通过，继续处理...")
        
        chat_id = update.effective_chat.id
        logger.info(f"收到 /today 命令，群组ID: {chat_id}，类型: {type(chat_id)}")
        
        try:
            # 根据群组ID获取对应的渠道ID列表
            channel_ids = self.config_loader.get_channel_ids_by_group_id(chat_id)
            
            if not channel_ids:
                await update.message.reply_text("❌ 当前群组未配置渠道信息")
                return
            
            logger.info(f"群组 {chat_id} 对应的渠道ID列表: {channel_ids}")
            
            # 获取印度时区的当前时间
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            india_current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            india_current_date = india_now.strftime('%Y-%m-%d')
            
            logger.info(f"印度时区当前时间: {india_current_time}")
            logger.info(f"印度时区当前日期: {india_current_date}")
            
            # 查询所有数据
            logger.info("查询所有渠道数据")
            data_list = await self.api_reader.read_data(
                report_date=india_current_date,
                report_type=0
            )
            
            if not data_list:
                await update.message.reply_text("📊 今日暂无数据")
                return
            
            # 过滤匹配的数据
            matched_data = []
            for data in data_list:
                data_channel = data.get('channel', '')
                # logger.info(f"检查数据渠道: '{data_channel}' vs 期望渠道列表: {channel_ids}")
                
                # 只包含渠道ID在配置列表中的数据
                if data_channel in channel_ids:
                    matched_data.append(data)
                else:
                    continue
                    # logger.info(f"跳过不匹配的数据：数据渠道 '{data_channel}' 不在期望渠道列表 {channel_ids} 中")
            
            if not matched_data:
                await update.message.reply_text(f"📊 今日暂无匹配数据")
                return
            
            # 使用汇总发送功能
            logger.info(f"准备发送 {len(matched_data)} 条匹配的今日数据")
            
            # 创建临时的数据发送器
            data_sender = ApiDataSender(context.bot, self.config_loader)
            
            # 发送简单通知
            success = await self._send_today_notification(chat_id, context.bot)
            
            if success:
                logger.info(f"成功发送今日通知到群组 {chat_id}")
                
                # 写入Google表格
                await self._write_today_data_to_sheets(matched_data, chat_id)
            else:
                logger.error(f"发送今日通知到群组 {chat_id} 失败")
                await update.message.reply_text("❌ 发送通知时出现错误，请稍后重试")
            
        except Exception as e:
            logger.error(f"处理 /today 命令时出错: {str(e)}")
            await update.message.reply_text("❌ 获取数据时出现错误，请稍后重试")
    
    async def handle_yesterday_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /yesterday 命令 - 发送昨天的日报数据"""
        logger.info("=== 进入 handle_yesterday_command 函数 ===")
        logger.info(f"接收到的参数 - update: {update}, context: {context}")
        
        if not update:
            logger.error("Update 对象为空!")
            return
            
        if not update.message:
            logger.warning("update.message 为空!")
            return
            
        if not update.effective_chat:
            logger.warning("update.effective_chat 为空!")
            return
            
        logger.info("所有必要的对象验证通过，继续处理...")
        
        chat_id = update.effective_chat.id
        logger.info(f"收到 /yesterday 命令，群组ID: {chat_id}，类型: {type(chat_id)}")
        
        try:
            # 根据群组ID获取对应的渠道ID列表
            channel_ids = self.config_loader.get_channel_ids_by_group_id(chat_id)
            
            if not channel_ids:
                await update.message.reply_text("❌ 当前群组未配置渠道信息")
                return
            
            logger.info(f"群组 {chat_id} 对应的渠道ID列表: {channel_ids}")
            
            # 获取印度时区的当前时间，然后计算昨天
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            india_yesterday = india_now - timedelta(days=1)
            india_yesterday_date = india_yesterday.strftime('%Y-%m-%d')
            india_current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"印度时区当前时间: {india_current_time}")
            logger.info(f"印度时区昨天日期: {india_yesterday_date}")
            
            # 查询所有数据
            logger.info("查询所有渠道数据")
            data_list = await self.api_reader.read_data(
                report_date=india_yesterday_date,
                report_type=0
            )
            
            if not data_list:
                await update.message.reply_text("📊 昨日暂无数据")
                return
            
            # 过滤匹配的数据
            matched_data = []
            for data in data_list:
                data_channel = data.get('channel', '')
                # logger.info(f"检查数据渠道: '{data_channel}' vs 期望渠道列表: {channel_ids}")
                
                # 只包含渠道ID在配置列表中的数据
                if data_channel in channel_ids:
                    matched_data.append(data)
                else:
                    continue
                    # logger.info(f"跳过不匹配的数据：数据渠道 '{data_channel}' 不在期望渠道列表 {channel_ids} 中")
            
            if not matched_data:
                await update.message.reply_text(f"📊 昨日暂无匹配数据")
                return
            
            # 使用汇总发送功能
            logger.info(f"准备发送 {len(matched_data)} 条匹配的昨日数据")
            
            # 创建临时的数据发送器
            data_sender = ApiDataSender(context.bot, self.config_loader)
            
            # 发送简单通知
            success = await self._send_yesterday_notification(chat_id, context.bot)
            
            if success:
                logger.info(f"成功发送昨日通知到群组 {chat_id}")
                
                # 写入Google表格
                await self._write_yesterday_data_to_sheets(matched_data, chat_id)
            else:
                logger.error(f"发送昨日通知到群组 {chat_id} 失败")
                await update.message.reply_text("❌ 发送通知时出现错误，请稍后重试")
            
        except Exception as e:
            logger.error(f"处理 /yesterday 命令时出错: {str(e)}")
            await update.message.reply_text("❌ 获取数据时出现错误，请稍后重试")
    
    async def _send_grouped_data_to_single_group(self, data_sender, data_list, chat_id, report_type):
        """向单个群组发送汇总数据
        
        Args:
            data_sender: 数据发送器实例
            data_list: 数据列表
            chat_id: 目标群组ID
            report_type: 报表类型
            
        Returns:
            是否发送成功
        """
        try:
            if not data_list:
                logger.warning("数据列表为空")
                return False
            
            # 获取群组名称
            groups_config = self.config_loader.get_groups_config()
            group_name = "未知群组"
            
            for group_config in groups_config.values():
                if group_config.get('tg_group') == str(chat_id):
                    group_name = group_config.get('name', '未知群组')
                    break
            
            logger.info(f"向群组 {group_name} ({chat_id}) 发送汇总数据")
            
            # 生成汇总消息（文本表格格式）
            messages = await data_sender._generate_grouped_messages(data_list, group_name)
            
            if not messages:
                logger.warning("生成的汇总消息为空")
                return False
            
            # 发送消息
            for i, message in enumerate(messages):
                await data_sender.bot.send_message(chat_id=chat_id, text=message)
                logger.info(f"已发送第 {i + 1}/{len(messages)} 条汇总消息到群组 {group_name}")
            
            logger.info(f"群组 {group_name} 汇总发送完成，共 {len(messages)} 条消息")
            return True
            
        except Exception as e:
            logger.error(f"向单个群组发送汇总数据时出错: {str(e)}")
            return False
    
    async def _send_today_notification(self, chat_id: int, bot=None) -> bool:
        """发送今日通知
        
        Args:
            chat_id: 目标群组ID
            bot: Telegram bot实例
            
        Returns:
            是否发送成功
        """
        try:
            if not bot:
                logger.error("Bot实例为空，无法发送通知")
                return False
                
            # 获取印度时区的当前时间
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            
            message = f"📊 今日时报已更新表格\n⏰ 更新时间：{current_time}\n📋 数据已写入Google表格"
            
            await bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"已发送今日通知到群组 {chat_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"发送今日通知时出错: {str(e)}")
            return False
    
    async def _send_yesterday_notification(self, chat_id: int, bot=None) -> bool:
        """发送昨日通知
        
        Args:
            chat_id: 目标群组ID
            bot: Telegram bot实例
            
        Returns:
            是否发送成功
        """
        try:
            if not bot:
                logger.error("Bot实例为空，无法发送通知")
                return False
                
            # 获取印度时区的当前时间
            india_tz = pytz.timezone('Asia/Kolkata')
            india_now = datetime.now(india_tz)
            current_time = india_now.strftime('%Y-%m-%d %H:%M:%S')
            
            message = f"📊 昨日日报已更新表格\n⏰ 更新时间：{current_time}\n📋 数据已写入Google表格"
            
            await bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"已发送昨日通知到群组 {chat_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"发送昨日通知时出错: {str(e)}")
            return False
    
    async def _write_today_data_to_sheets(self, data_list, chat_id):
        """将今日数据写入Google表格
        
        Args:
            data_list: 数据列表
            chat_id: 群组ID
        """
        try:
            if not data_list:
                logger.warning("今日数据为空，跳过Google表格写入")
                return
            
            # 获取群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置，跳过Google表格写入")
                return
            
            # 查找对应的群组配置
            target_group = None
            for group_name, group_config in groups_config.items():
                if group_config.get('tg_group') == str(chat_id):
                    target_group = {
                        'name': group_name,
                        'config': group_config
                    }
                    break
            
            if not target_group:
                logger.warning(f"未找到群组ID {chat_id} 对应的配置，跳过Google表格写入")
                return
            
            # 检查是否有Google表格配置
            spreadsheet_id = self.config_loader.get_group_spreadsheet_id(target_group['name'])
            if not spreadsheet_id:
                logger.info(f"群组 {target_group['name']} 未配置Google表格，跳过写入")
                return
            
            hourly_sheet_name = self.config_loader.get_hourly_sheet_name()
            
            # 确保工作表存在
            await self.sheets_writer.create_sheet_if_not_exists(spreadsheet_id, hourly_sheet_name)
            
            # 确保表头存在
            await self.sheets_writer.ensure_sheet_headers(spreadsheet_id, hourly_sheet_name)
            
            # 写入数据
            success = await self.sheets_writer.write_hourly_data(
                spreadsheet_id, 
                hourly_sheet_name, 
                data_list, 
                target_group['config'].get('name', target_group['name'])
            )
            
            if success:
                logger.info(f"群组 {target_group['name']} 的今日数据已成功写入Google表格")
            else:
                logger.error(f"群组 {target_group['name']} 的今日数据写入Google表格失败")
        
        except Exception as e:
            logger.error(f"写入今日数据到Google表格时出错: {str(e)}")
    
    async def _write_yesterday_data_to_sheets(self, data_list, chat_id):
        """将昨日数据写入Google表格
        
        Args:
            data_list: 数据列表
            chat_id: 群组ID
        """
        try:
            if not data_list:
                logger.warning("昨日数据为空，跳过Google表格写入")
                return
            
            # 获取群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置，跳过Google表格写入")
                return
            
            # 查找对应的群组配置
            target_group = None
            for group_name, group_config in groups_config.items():
                if group_config.get('tg_group') == str(chat_id):
                    target_group = {
                        'name': group_name,
                        'config': group_config
                    }
                    break
            
            if not target_group:
                logger.warning(f"未找到群组ID {chat_id} 对应的配置，跳过Google表格写入")
                return
            
            # 检查是否有Google表格配置
            spreadsheet_id = self.config_loader.get_group_spreadsheet_id(target_group['name'])
            if not spreadsheet_id:
                logger.info(f"群组 {target_group['name']} 未配置Google表格，跳过写入")
                return
            
            daily_sheet_name = self.config_loader.get_daily_sheet_name()
            
            # 确保工作表存在
            await self.sheets_writer.create_sheet_if_not_exists(spreadsheet_id, daily_sheet_name)
            
            # 确保表头存在
            await self.sheets_writer.ensure_sheet_headers(spreadsheet_id, daily_sheet_name)
            
            # 写入数据
            success = await self.sheets_writer.write_daily_data(
                spreadsheet_id, 
                daily_sheet_name, 
                data_list, 
                target_group['config'].get('name', target_group['name'])
            )
            
            if success:
                logger.info(f"群组 {target_group['name']} 的昨日数据已成功写入Google表格")
            else:
                logger.error(f"群组 {target_group['name']} 的昨日数据写入Google表格失败")
        
        except Exception as e:
            logger.error(f"写入昨日数据到Google表格时出错: {str(e)}")
    
    async def _format_api_message(self, data: dict, report_type: str) -> str:
        """格式化API数据消息
        
        Args:
            data: API返回的数据项
            report_type: 报表类型（如"今日时报"、"昨日日报"）
            
        Returns:
            格式化后的消息文本
        """
        try:
            # 根据API返回的数据格式化消息
            logger.info(f"格式化数据: {data}")
            date_str = data.get('create_date', '')
            channel = data.get('channel', '')
            new_users = data.get('new_users', 0)
            charge_amount = data.get('charge_amount', 0)
            money_withdraw = data.get('money_withdraw', 0)
            charge_withdraw_diff = data.get('charge_withdraw_diff', 0)
            newuser_charged = data.get('newuser_charged', 0)
            newuser_charge_money = data.get('newuser_charge_money', 0)
            
            logger.info(f"提取的字段 - 日期: {date_str}, 渠道: {channel}, 新用户: {new_users}")
            
            message = f"📊 {report_type}\n"
            message += f"━━━━━━━━━━━━━━━━\n"
            message += f"📅 日期：{date_str}\n"
            message += f"🎯 渠道：{channel}\n"
            message += f"👥 新增用户数：{new_users}\n"
            message += f"💰 充值金额：{charge_amount}\n"
            message += f"💸 提现金额：{money_withdraw}\n"
            message += f"📈 充提差：{charge_withdraw_diff}\n"
            message += f"🆕 新增付费人数：{newuser_charged}\n"
            message += f"💎 新增付费金额：{newuser_charge_money}"
            
            return message
            
        except Exception as e:
            logger.error(f"格式化消息时出错: {str(e)}")
            return f"❌ 数据格式化失败: {str(e)}"