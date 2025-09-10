from typing import List, Dict, Any
import logging
import math
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from utils import AdminState
import asyncio

# 配置日志
logger = logging.getLogger(__name__)

class AdminHandler:
    def __init__(self, config_loader, admin_state: AdminState, user_command_handler=None, api_data_sender_manager=None):
        """初始化管理员处理器"""
        self.config_loader = config_loader
        self.admin_state = admin_state
        self.user_command_handler = user_command_handler
        self.api_data_sender_manager = api_data_sender_manager
        self.admins = config_loader.get_admins()
        self.items_per_page = 15  # 每页显示15条数据
    
    def is_admin(self, user_id: int) -> bool:
        # 确保管理员列表是整数列表
        if not isinstance(self.admins, list):
            logger.error(f"管理员列表不是列表类型: {type(self.admins)}")
            return False
            
        # 检查用户ID是否在管理员列表中
        is_admin = user_id in self.admins
        logger.info(f"用户 {user_id} 是否为管理员: {is_admin}")
        return is_admin
    
    def update_config(self, config_loader) -> None:
        """更新配置加载器"""
        self.config_loader = config_loader
        self.admins = config_loader.get_admins()
    
    async def handle_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /start 命令"""
        # 检查是否是回调查询
        message = update.message or (update.callback_query.message if update.callback_query else None)
        if not message:
            return
        
        if not update.effective_user or not self.is_admin(update.effective_user.id):
            await message.reply_text("Hello")
            return
        
        # 创建管理员键盘
        keyboard = [
            [InlineKeyboardButton("新增管理员", callback_data="add_admin"),
             InlineKeyboardButton("删除管理员", callback_data="delete_admin")],
            [InlineKeyboardButton("新增渠道分组", callback_data="add_channel_group"),
             InlineKeyboardButton("删除渠道分组", callback_data="delete_channel_group")],
            [InlineKeyboardButton("新增代投组", callback_data="add_investment_group"),
             InlineKeyboardButton("删除代投组", callback_data="delete_investment_group")],
            [InlineKeyboardButton("配置Google表格", callback_data="config_google_sheets")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await message.reply_text(
                "🔧 管理员控制面板\n━━━━━━━━━━━━━━━━\n请选择要执行的操作：",
                reply_markup=reply_markup
            )
            logger.info("管理员控制面板已发送")
        except Exception as e:
            logger.error(f"发送管理员控制面板失败: {str(e)}", exc_info=True)
            await message.reply_text("❌ 发送控制面板失败")

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理回调查询"""
        query = update.callback_query
        # 注释掉未定义的ppprint函数调用
        # ppprint(f"Received callback_data: {query.data}")
        logger.info(f"Received callback_data: {query.data}")
        try:
            # 先应答回调查询，避免按钮显示loading状态
            await query.answer()
            
            # 检查是否在私聊中
            if not update.effective_chat or update.effective_chat.type != 'private':
                logger.warning("回调查询不是在私聊中发起的")
                return
            
            if not update.effective_user:
                logger.warning("无法获取用户信息")
                await query.edit_message_text("❌ 无法获取用户信息")
                return
            
            user_id = update.effective_user.id
            logger.info(f"用户ID: {user_id}")
            
            if not self.is_admin(user_id):
                logger.warning(f"用户 {user_id} 不是管理员")
                await query.edit_message_text("❌ 您没有权限执行此操作")
                return
            
            data = query.data
            logger.info(f"处理回调查询数据: {data}")
            
            # 处理主菜单选项
            if data == "add_admin":
                logger.info("处理新增管理员请求")
                await self._handle_add_admin_request(query)
            elif data == "delete_admin":
                logger.info("处理删除管理员请求")
                await self._handle_delete_admin_request(query)
            elif data == "add_channel_group":
                logger.info("处理新增渠道分组请求")
                await self._handle_add_channel_group_request(query)
            elif data == "delete_channel_group":
                logger.info("处理删除渠道分组请求")
                await self._handle_delete_channel_group_request(query)
            elif data == "add_investment_group":
                logger.info("处理新增代投组请求")
                await self._handle_add_investment_group_request(query)
            elif data == "delete_investment_group":
                logger.info("处理删除代投组请求")
                await self._handle_delete_investment_group_request(query)
            elif data == "back_to_main":
                logger.info("返回主菜单")
                await self._back_to_main_menu(query)
            elif data == "noop":
                # 空操作，用于禁用的按钮
                pass
            
            # 处理管理员列表分页
            elif data.startswith("admin_page_"):
                page = int(data.split("_")[2])
                logger.info(f"显示管理员列表第 {page + 1} 页")
                await self._show_admin_list(query, page)
            elif data.startswith("delete_admin_"):
                admin_index = int(data.split("_")[2])
                logger.info(f"确认删除管理员索引: {admin_index}")
                await self._confirm_delete_admin(query, admin_index)
            
            # 处理渠道分组列表分页
            elif data.startswith("channel_page_"):
                page = int(data.split("_")[2])
                logger.info(f"显示渠道分组列表第 {page + 1} 页")
                await self._show_channel_group_list(query, page)
            
            # 处理群组选择分页（添加渠道）
            elif data.startswith("add_channel_page_"):
                page = int(data.split("_")[3])
                logger.info(f"显示添加渠道群组列表第 {page + 1} 页")
                await self._show_groups_for_channel_addition(query, page)
            elif data.startswith("add_channel_to_group_"):
                group_index = int(data.split("_")[4])
                logger.info(f"选择群组添加渠道索引: {group_index}")
                await self._handle_add_channel_to_group(query, group_index)
            
            # 处理群组选择分页（删除渠道）
            elif data.startswith("delete_channel_page_"):
                page = int(data.split("_")[3])
                logger.info(f"显示删除渠道群组列表第 {page + 1} 页")
                await self._show_groups_for_channel_deletion(query, page)
            elif data.startswith("delete_channel_from_group_"):
                logger.info(f"收到删除渠道回调数据: {data}")
                parts = data.split("_")
                logger.info(f"回调数据分割结果: {parts}")
                
                # 查找最后一个数字作为group_index
                group_index = None
                for part in reversed(parts):
                    try:
                        group_index = int(part)
                        break
                    except ValueError:
                        continue
                
                if group_index is None:
                    logger.error(f"无法从回调数据中解析群组索引: {data}")
                    await query.edit_message_text("❌ 无效的回调数据")
                    return
                
                logger.info(f"选择群组删除渠道索引: {group_index}")
                await self._handle_delete_channel_from_group(query, group_index)
            
            # 处理渠道ID选择分页（删除渠道）
            elif data.startswith("delete_channel_id_page_"):
                parts = data.split("_")
                page = int(parts[3])
                group_index = int(parts[4])
                logger.info(f"显示删除渠道ID列表第 {page + 1} 页，群组索引: {group_index}")
                await self._show_channel_ids_for_deletion(query, page, group_index)
            elif data.startswith("delete_channel_id_"):
                channel_id_index = int(data.split("_")[3])
                logger.info(f"确认删除渠道ID索引: {channel_id_index}")
                await self._confirm_delete_channel_id(query, channel_id_index)
            
            # 处理代投组选择分页（删除代投组）
            elif data.startswith("delete_investment_page_"):
                page = int(data.split("_")[3])
                logger.info(f"显示删除代投组列表第 {page + 1} 页")
                await self._show_investment_groups_for_deletion(query, page)
            elif data.startswith("delete_investment_group_"):
                group_index = int(data.split("_")[3])
                logger.info(f"确认删除代投组索引: {group_index}")
                await self._confirm_delete_investment_group(query, group_index)
            elif data.startswith("confirm_delete_investment_"):
                group_index = int(data.split("_")[3])
                logger.info(f"执行删除代投组索引: {group_index}")
                await self._execute_delete_investment_group(query, group_index)
            
            # 处理Google表格配置
            elif data == "config_google_sheets":
                logger.info("处理Google表格配置请求")
                await self._handle_config_google_sheets_request(query)
            elif data.startswith("google_sheets_page_"):
                page = int(data.split("_")[3])
                logger.info(f"显示Google表格配置第 {page + 1} 页")
                await self._handle_config_google_sheets_request(query, page)
            elif data.startswith("set_spreadsheet_"):
                group_name = data.split("_", 2)[2]  # 获取群组名称
                logger.info(f"设置群组 {group_name} 的表格ID")
                await self._handle_set_spreadsheet_request(query, group_name)
            elif data.startswith("remove_spreadsheet_"):
                group_name = data.split("_", 2)[2]  # 获取群组名称
                logger.info(f"删除群组 {group_name} 的表格ID")
                await self._handle_remove_spreadsheet_request(query, group_name)
            
            # 处理旧版渠道分组删除（兼容性）
            elif data.startswith("delete_channel_"):
                channel_index = int(data.split("_")[2])
                logger.info(f"确认删除渠道分组索引: {channel_index}")
                await self._confirm_delete_channel_group(query, channel_index)
            else:
                logger.warning(f"未知的回调查询数据: {data}")
                await query.edit_message_text("❌ 未知的操作")
                
        except Exception as e:
            logger.error(f"处理回调查询时出错: {str(e)}", exc_info=True)
            try:
                await query.edit_message_text(f"❌ 处理操作时出错: {str(e)}")
            except Exception as inner_e:
                logger.error(f"发送错误消息失败: {str(inner_e)}")
                # 如果编辑消息失败，尝试发送新消息
                try:
                    await query.message.reply_text(f"❌ 处理操作时出错: {str(e)}")
                except:
                    pass
    
    async def _handle_add_admin_request(self, query) -> None:
        """处理新增管理员请求"""
        try:
            user_id = query.from_user.id
            logger.info(f"设置用户 {user_id} 等待输入新管理员ID")
            
            # 设置状态
            self.admin_state.set_waiting_for_add_admin_id(user_id)
            
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "👤 新增管理员\n━━━━━━━━━━━━━━━━\n请输入新管理员的用户ID：",
                reply_markup=reply_markup
            )
            logger.info("新增管理员界面已显示")
            
        except Exception as e:
            logger.error(f"处理新增管理员请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示新增管理员界面失败: {str(e)}")
    
    async def _handle_delete_admin_request(self, query) -> None:
        """处理删除管理员请求"""
        try:
            await self._show_admin_list(query, 0)
        except Exception as e:
            logger.error(f"显示管理员列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示管理员列表失败: {str(e)}")
    
    async def _show_admin_list(self, query, page: int = 0) -> None:
        """显示管理员列表"""
        try:
            user_id = query.from_user.id
            admin_list = self.config_loader.get_admins()
            
            if not admin_list:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "❌ 当前没有管理员",
                    reply_markup=reply_markup
                )
                return
                
            # 设置状态
            self.admin_state.set_admin_list_selection(user_id, admin_list, page)
            
            # 计算分页
            total_items = len(admin_list)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"👥 管理员列表 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要删除的管理员：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                admin_id = admin_list[i]
                # 检查是否是当前用户
                status = " (当前用户)" if admin_id == user_id else ""
                button_text = f"{i + 1}. {admin_id}{status}"
                
                # 当前用户不能删除自己
                if admin_id != user_id:
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_admin_{i}")])
                else:
                    keyboard.append([InlineKeyboardButton(f"🚫 {button_text}", callback_data="noop")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"admin_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"admin_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示管理员列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示管理员列表失败: {str(e)}")
    
    async def _confirm_delete_admin(self, query, admin_index: int) -> None:
        """确认删除管理员"""
        try:
            user_id = query.from_user.id
            data = self.admin_state.get_admin_list_data(user_id)
            admin_list = data['admin_list']
            
            if admin_index < 0 or admin_index >= len(admin_list):
                await query.edit_message_text("❌ 无效的管理员索引")
                return
                
            admin_to_delete = admin_list[admin_index]
            
            # 不能删除自己
            if admin_to_delete == user_id:
                await query.edit_message_text("❌ 不能删除自己")
                return
                
            # 不能删除最后一个管理员
            if len(admin_list) <= 1:
                await query.edit_message_text("❌ 不能删除最后一个管理员")
                return
                
            # 执行删除
            if self.config_loader.remove_admin(admin_to_delete):
                await query.edit_message_text(f"✅ 已成功删除管理员 {admin_to_delete}")
                
                # 重新加载配置
                await self._reload_config(query)
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
            else:
                await query.edit_message_text(f"❌ 删除管理员 {admin_to_delete} 失败")
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
                
        except Exception as e:
            logger.error(f"删除管理员失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 删除管理员失败: {str(e)}")
    
    async def _handle_add_channel_group_request(self, query) -> None:
        """处理新增渠道分组请求"""
        try:
            await self._show_groups_for_channel_addition(query, 0)
        except Exception as e:
            logger.error(f"处理新增渠道分组请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示群组列表失败: {str(e)}")

    async def _handle_delete_channel_group_request(self, query) -> None:
        """处理删除渠道分组请求"""
        try:
            await self._show_groups_for_channel_deletion(query, 0)
        except Exception as e:
            logger.error(f"显示群组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示群组列表失败: {str(e)}")
    
    async def _show_groups_for_channel_addition(self, query, page: int = 0) -> None:
        """显示群组列表供用户选择添加渠道"""
        try:
            groups_config = self.config_loader.get_groups_config()
            
            if not groups_config:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "❌ 当前没有群组配置",
                    reply_markup=reply_markup
                )
                return
            
            # 转换为列表以便分页
            group_items = list(groups_config.items())
            
            # 计算分页
            total_items = len(group_items)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"🏷️ 选择群组添加渠道 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要添加渠道的群组：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                group_name, group_config = group_items[i]
                group_display_name = group_config.get('name', group_name)
                button_text = f"{i + 1}. {group_display_name}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"add_channel_to_group_{i}")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"add_channel_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"add_channel_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示群组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示群组列表失败: {str(e)}")
    
    async def _show_groups_for_channel_deletion(self, query, page: int = 0) -> None:
        """显示群组列表供用户选择删除渠道"""
        try:
            groups_config = self.config_loader.get_groups_config()
            
            if not groups_config:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "❌ 当前没有群组配置",
                    reply_markup=reply_markup
                )
                return
            
            # 转换为列表以便分页
            group_items = list(groups_config.items())
            
            # 计算分页
            total_items = len(group_items)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"🗑️ 选择群组删除渠道 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要删除渠道的群组：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                group_name, group_config = group_items[i]
                group_display_name = group_config.get('name', group_name)
                button_text = f"{i - start_index + 1}. {group_display_name}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_channel_from_group_{i}")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"delete_channel_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"delete_channel_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示群组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示群组列表失败: {str(e)}")
    
    async def _handle_add_channel_to_group(self, query, group_index: int) -> None:
        """处理选择群组添加渠道"""
        try:
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            
            if group_index < 0 or group_index >= len(group_items):
                await query.edit_message_text("❌ 无效的群组索引")
                return
            
            group_name, group_config = group_items[group_index]
            group_display_name = group_config.get('name', group_name)
            
            # 设置状态等待输入新渠道ID
            user_id = query.from_user.id
            self.admin_state.set_waiting_for_new_channel_id(user_id, group_name)
            
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📝 为群组「{group_display_name}」添加渠道\n━━━━━━━━━━━━━━━━\n"
                f"请输入新的渠道ID（如：FBA8-18）：\n\n"
                f"💡 支持批量添加，用换行或|分隔多个渠道ID\n"
                f"例如：\nFBA8-18\nFBWX-77\nFBNYC-103\n\n"
                f"或者：FBA8-18|FBWX-77|FBNYC-103",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"处理选择群组添加渠道失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 处理选择群组失败: {str(e)}")

    async def _handle_delete_channel_from_group(self, query, group_index: int) -> None:
        """处理选择群组删除渠道"""
        try:
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            
            if group_index < 0 or group_index >= len(group_items):
                await query.edit_message_text("❌ 无效的群组索引")
                return
            
            group_name, group_config = group_items[group_index]
            group_display_name = group_config.get('name', group_name)
            channel_ids = group_config.get('channel_ids', [])
            
            if not channel_ids:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"❌ 群组「{group_display_name}」没有配置的渠道",
                    reply_markup=reply_markup
                )
                return
            
            # 设置状态等待输入要删除的渠道ID
            user_id = query.from_user.id
            self.admin_state.set_waiting_for_delete_channel_ids(user_id, group_name)
            
            # 显示当前群组的渠道列表
            current_channels = [channel.get('id', '') for channel in channel_ids]
            channels_text = '\n'.join([f"• {channel}" for channel in current_channels])
            
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🗑️ 删除群组「{group_display_name}」的渠道\n━━━━━━━━━━━━━━━━\n"
                f"当前渠道列表：\n{channels_text}\n\n"
                f"请输入要删除的渠道ID：\n\n"
                f"💡 支持多种输入格式：\n"
                f"• 换行分隔：\nFBA8-18\nFBWX-77\n"
                f"• |分隔：FBA8-18|FBWX-77\n"
                f"• 带•符号：• FBHZDB-11\n"
                f"• 混合格式：FBA8-18|• FBWX-77\n\n"
                f"💡 不存在的渠道ID会自动跳过",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"处理选择群组删除渠道失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 处理选择群组失败: {str(e)}")
    
    async def _show_channel_ids_for_deletion(self, query, page: int = 0, group_index: int = None) -> None:
        """显示渠道ID列表供用户选择删除"""
        try:
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            
            # 如果没有指定group_index，从状态中获取
            if group_index is None:
                user_id = query.from_user.id
                state_data = self.admin_state.get_state(user_id)
                if state_data and 'selected_group_index' in state_data:
                    group_index = state_data['selected_group_index']
                else:
                    await query.edit_message_text("❌ 未找到选中的群组，请重新选择")
                    return
            
            if group_index < 0 or group_index >= len(group_items):
                await query.edit_message_text("❌ 无效的群组索引")
                return
            
            group_name, group_config = group_items[group_index]
            group_display_name = group_config.get('name', group_name)
            channel_ids = group_config.get('channel_ids', [])
            
            if not channel_ids:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"❌ 群组「{group_display_name}」没有配置的渠道",
                    reply_markup=reply_markup
                )
                return
            
            # 设置状态
            user_id = query.from_user.id
            self.admin_state.set_channel_id_list_selection(user_id, channel_ids, group_index, page)
            
            # 计算分页
            total_items = len(channel_ids)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"🗑️ 删除群组「{group_display_name}」的渠道 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要删除的渠道ID：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                channel_id = channel_ids[i].get('id', '')
                button_text = f"{i + 1}. {channel_id}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_channel_id_{i}")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"delete_channel_id_page_{page - 1}_{group_index}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"delete_channel_id_page_{page + 1}_{group_index}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示渠道ID列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示渠道ID列表失败: {str(e)}")
    
    async def _confirm_delete_channel_id(self, query, channel_id_index: int) -> None:
        """确认删除渠道ID"""
        try:
            user_id = query.from_user.id
            state_data = self.admin_state.get_state(user_id)
            
            if not state_data or 'channel_ids' not in state_data:
                await query.edit_message_text("❌ 状态数据丢失")
                return
            
            channel_ids = state_data['channel_ids']
            group_index = state_data.get('selected_group_index', 0)
            
            if channel_id_index < 0 or channel_id_index >= len(channel_ids):
                await query.edit_message_text("❌ 无效的渠道ID索引")
                return
            
            channel_to_delete = channel_ids[channel_id_index].get('id', '')
            
            # 执行删除
            if self.config_loader.remove_channel_id_from_group(group_index, channel_to_delete):
                await query.edit_message_text(f"✅ 已成功删除渠道ID：{channel_to_delete}")
                
                # 重新加载配置
                await self._reload_config(query)
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
            else:
                await query.edit_message_text(f"❌ 删除渠道ID {channel_to_delete} 失败")
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
                
        except Exception as e:
            logger.error(f"删除渠道ID失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 删除渠道ID失败: {str(e)}")
    
    async def _handle_add_investment_group_request(self, query) -> None:
        """处理新增代投组请求"""
        try:
            user_id = query.from_user.id
            self.admin_state.set_waiting_for_new_investment_group_name(user_id)
            
            keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🏷️ 新增代投组\n━━━━━━━━━━━━━━━━\n请输入代投组名称（如：投流3组）：",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"处理新增代投组请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示新增代投组界面失败: {str(e)}")
    
    async def _handle_delete_investment_group_request(self, query) -> None:
        """处理删除代投组请求"""
        try:
            await self._show_investment_groups_for_deletion(query, 0)
        except Exception as e:
            logger.error(f"显示代投组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示代投组列表失败: {str(e)}")
    
    async def _show_investment_groups_for_deletion(self, query, page: int = 0) -> None:
        """显示代投组列表供用户选择删除"""
        try:
            groups_config = self.config_loader.get_groups_config()
            
            if not groups_config:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "❌ 当前没有代投组配置",
                    reply_markup=reply_markup
                )
                return
            
            # 转换为列表以便分页
            group_items = list(groups_config.items())
            
            # 计算分页
            total_items = len(group_items)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"🗑️ 删除代投组 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要删除的代投组：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                group_name, group_config = group_items[i]
                group_display_name = group_config.get('name', group_name)
                tg_group = group_config.get('tg_group', '')
                channel_count = len(group_config.get('channel_ids', []))
                button_text = f"{i + 1}. {group_display_name} ({tg_group}, {channel_count}个渠道)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_investment_group_{i}")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"delete_investment_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"delete_investment_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示代投组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示代投组列表失败: {str(e)}")
    
    async def _confirm_delete_investment_group(self, query, group_index: int) -> None:
        """确认删除代投组"""
        try:
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            
            if group_index < 0 or group_index >= len(group_items):
                await query.edit_message_text("❌ 无效的代投组索引")
                return
            
            group_name, group_config = group_items[group_index]
            group_display_name = group_config.get('name', group_name)
            tg_group = group_config.get('tg_group', '')
            channel_ids = group_config.get('channel_ids', [])
            channel_count = len(channel_ids)
            
            # 显示确认信息
            text = f"⚠️ 确认删除代投组\n━━━━━━━━━━━━━━━━\n"
            text += f"代投组名称：{group_display_name}\n"
            text += f"群组ID：{tg_group}\n"
            text += f"渠道数量：{channel_count}个\n"
            if channel_ids:
                channel_names = [channel.get('id', '') for channel in channel_ids]
                text += f"渠道列表：{', '.join(channel_names)}\n"
            text += f"\n⚠️ 此操作将删除整个代投组配置！"
            
            keyboard = [
                [InlineKeyboardButton("✅ 确认删除", callback_data=f"confirm_delete_investment_{group_index}")],
                [InlineKeyboardButton("❌ 取消", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"确认删除代投组失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 确认删除代投组失败: {str(e)}")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(query)
    
    async def _execute_delete_investment_group(self, query, group_index: int) -> None:
        """执行删除代投组"""
        try:
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            
            if group_index < 0 or group_index >= len(group_items):
                await query.edit_message_text("❌ 无效的代投组索引")
                return
            
            group_name, group_config = group_items[group_index]
            
            # 执行删除
            if self.config_loader.remove_group_config(group_name):
                await query.edit_message_text(f"✅ 已成功删除代投组：{group_name}")
                
                # 重新加载配置
                await self._reload_config(query)
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
            else:
                await query.edit_message_text(f"❌ 删除代投组 {group_name} 失败")
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
                
        except Exception as e:
            logger.error(f"执行删除代投组失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 执行删除代投组失败: {str(e)}")
    
    async def _show_channel_group_list(self, query, page: int = 0) -> None:
        """显示渠道分组列表"""
        try:
            user_id = query.from_user.id
            channel_groups = self.config_loader.get_channel_groups_config()
            
            if not channel_groups:
                keyboard = [[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "❌ 当前没有渠道分组配置",
                    reply_markup=reply_markup
                )
                return
            
            # 设置状态
            self.admin_state.set_channel_group_list_selection(user_id, channel_groups, page)
            
            # 转换为列表以便分页
            channel_items = list(channel_groups.items())
            
            # 计算分页
            total_items = len(channel_items)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息文本
            text = f"🏷️ 渠道分组列表 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            text += "请选择要删除的渠道分组：\n\n"
            
            # 构建键盘
            keyboard = []
            for i in range(start_index, end_index):
                channel_name, group_ids = channel_items[i]
                group_ids_str = ", ".join(map(str, group_ids))
                button_text = f"{i + 1}. {channel_name} → [{group_ids_str}]"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_channel_{i}")])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"channel_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"channel_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"显示渠道分组列表失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示渠道分组列表失败: {str(e)}")
    
    async def _confirm_delete_channel_group(self, query, channel_index: int) -> None:
        """确认删除渠道分组"""
        try:
            user_id = query.from_user.id
            data = self.admin_state.get_channel_group_list_data(user_id)
            channel_groups = data['channel_groups']
            
            channel_items = list(channel_groups.items())
            
            if channel_index < 0 or channel_index >= len(channel_items):
                await query.edit_message_text("❌ 无效的渠道分组索引")
                return
            
            channel_name, group_ids = channel_items[channel_index]
            
            # 执行删除
            if self.config_loader.remove_channel_group_config(channel_name):
                group_ids_str = ", ".join(map(str, group_ids))
                await query.edit_message_text(f"✅ 已成功删除渠道分组：{channel_name} → [{group_ids_str}]")
                
                # 重新加载配置
                await self._reload_config(query)
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
            else:
                await query.edit_message_text(f"❌ 删除渠道分组 {channel_name} 失败")
                
                # 延迟后返回主菜单
                await asyncio.sleep(2)
                await self._back_to_main_menu(query)
                
        except Exception as e:
            logger.error(f"删除渠道分组失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 删除渠道分组失败: {str(e)}")
    
    async def _back_to_main_menu(self, update_or_query) -> None:
        """返回主菜单"""
        try:
            # 清除用户状态
            if hasattr(update_or_query, 'from_user'):
                # 是query对象
                user_id = update_or_query.from_user.id
                self.admin_state.clear_state(user_id)
            elif hasattr(update_or_query, 'effective_user'):
                # 是update对象
                user_id = update_or_query.effective_user.id
                self.admin_state.clear_state(user_id)
            
            # 重新显示主菜单
            keyboard = [
                [InlineKeyboardButton("新增管理员", callback_data="add_admin"),
                 InlineKeyboardButton("删除管理员", callback_data="delete_admin")],
                [InlineKeyboardButton("新增渠道分组", callback_data="add_channel_group"),
                 InlineKeyboardButton("删除渠道分组", callback_data="delete_channel_group")],
                [InlineKeyboardButton("新增代投组", callback_data="add_investment_group"),
                 InlineKeyboardButton("删除代投组", callback_data="delete_investment_group")],
                [InlineKeyboardButton("配置Google表格", callback_data="config_google_sheets")],                 
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update_or_query, 'edit_message_text'):
                # 是query对象
                await update_or_query.edit_message_text(
                    "🔧 管理员控制面板\n━━━━━━━━━━━━━━━━\n请选择要执行的操作：",
                    reply_markup=reply_markup
                )
            elif hasattr(update_or_query, 'message'):
                # 是update对象
                await update_or_query.message.reply_text(
                "🔧 管理员控制面板\n━━━━━━━━━━━━━━━━\n请选择要执行的操作：",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"返回主菜单失败: {str(e)}", exc_info=True)
            if hasattr(update_or_query, 'edit_message_text'):
                await update_or_query.edit_message_text("❌ 返回主菜单失败")
            elif hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text("❌ 返回主菜单失败")
    
    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理管理员文本消息"""
        try:
            if not update.message or not update.effective_user:
                return
            
            user_id = update.effective_user.id
            message_text = update.message.text.strip()
            
            logger.info(f"收到用户 {user_id} 的消息: {message_text}")
            
            # 处理新增管理员ID输入
            if self.admin_state.is_waiting_for_add_admin_id(user_id):
                logger.info(f"处理用户 {user_id} 的新增管理员ID输入")
                await self._handle_add_admin_id_input(update, message_text)
            
            # 处理新增渠道名称输入
            elif self.admin_state.is_waiting_for_new_channel_group_name(user_id):
                logger.info(f"处理用户 {user_id} 的渠道名称输入")
                await self._handle_channel_group_name_input(update, message_text)
            
            # 处理渠道群组ID输入
            elif self.admin_state.is_waiting_for_channel_group_id(user_id):
                logger.info(f"处理用户 {user_id} 的渠道群组ID输入")
                await self._handle_channel_group_id_input(update, message_text)
            
            # 处理新渠道ID输入
            elif self.admin_state.is_waiting_for_new_channel_id(user_id):
                logger.info(f"处理用户 {user_id} 的新渠道ID输入")
                await self._handle_new_channel_id_input(update, message_text)
            
            # 处理删除渠道ID输入
            elif self.admin_state.is_waiting_for_delete_channel_ids(user_id):
                logger.info(f"处理用户 {user_id} 的删除渠道ID输入")
                await self._handle_delete_channel_ids_input(update, message_text)
            
            # 处理新代投组名称输入
            elif self.admin_state.is_waiting_for_new_investment_group_name(user_id):
                logger.info(f"处理用户 {user_id} 的新代投组名称输入")
                await self._handle_new_investment_group_name_input(update, message_text)
            
            # 处理新代投组群组ID输入
            elif self.admin_state.is_waiting_for_new_investment_group_id(user_id):
                logger.info(f"处理用户 {user_id} 的新代投组群组ID输入")
                await self._handle_new_investment_group_id_input(update, message_text)
            
            # 处理表格ID输入
            elif self.admin_state.is_waiting_for_spreadsheet_id(user_id):
                logger.info(f"处理用户 {user_id} 的表格ID输入")
                await self._handle_spreadsheet_id_input(update, message_text)
            else:
                logger.debug(f"用户 {user_id} 当前没有等待的输入状态")
                
        except Exception as e:
            logger.error(f"处理管理员消息失败: {str(e)}", exc_info=True)
    
    async def _handle_add_admin_id_input(self, update: Update, admin_id_str: str) -> None:
        """处理新增管理员ID输入"""
        try:
            admin_id = int(admin_id_str)
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的用户ID（数字格式）")
            return
        
        # 检查是否已经是管理员
        if admin_id in self.config_loader.get_admins():
            await update.message.reply_text(f"⚠️ 用户 {admin_id} 已经是管理员")
            return
        
        # 添加管理员
        if self.config_loader.add_admin(admin_id):
            await update.message.reply_text(f"✅ 已成功添加管理员：{admin_id}")
            
            # 清除状态并重新加载配置
            self.admin_state.clear_state(update.effective_user.id)
            await self._reload_config(update)
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
        else:
            await update.message.reply_text(f"❌ 添加管理员 {admin_id} 失败")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
    
    async def _handle_channel_group_name_input(self, update: Update, channel_name: str) -> None:
        """处理渠道名称输入"""
        # 检查渠道名称是否已存在
        existing_groups = self.config_loader.get_channel_groups_config()
        if channel_name in existing_groups:
            await update.message.reply_text(f"⚠️ 渠道 {channel_name} 已存在，请输入其他名称")
            return
        
        # 设置等待群组ID输入状态
        self.admin_state.set_waiting_for_channel_group_id(update.effective_user.id, channel_name)
        
        await update.message.reply_text(
            f"📝 渠道名称：{channel_name}\n\n现在请输入对应的群组ID（数字格式，如：-4632986596）："
        )
    
    async def _handle_channel_group_id_input(self, update: Update, group_id_str: str) -> None:
        """处理渠道群组ID输入"""
        try:
            group_id = int(group_id_str)
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的群组ID（数字格式）")
            return
            
        # 获取正在添加的渠道名称
        user_id = update.effective_user.id
        channel_name = self.admin_state.get_channel_name(user_id)
        if not channel_name:
            await update.message.reply_text("❌ 渠道名称丢失，请重新开始操作")
            return
            
        # 添加渠道分组配置
        if self.config_loader.add_channel_group_config(channel_name, group_id):
            await update.message.reply_text(f"✅ 已成功添加渠道分组：{channel_name} → {group_id}")
            
            # 清除状态并重新加载配置
            self.admin_state.clear_state(user_id)
            await self._reload_config(update)
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
        else:
            await update.message.reply_text(f"❌ 添加渠道分组失败")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
    
    async def _handle_new_channel_id_input(self, update: Update, channel_id_str: str) -> None:
        """处理新渠道ID输入"""
        try:
            channel_id_input = channel_id_str.strip()
            if not channel_id_input:
                await update.message.reply_text("❌ 渠道ID不能为空")
                return
            
            # 分割多个渠道ID（支持换行和|分隔）
            channel_ids = []
            # 先按换行分割
            lines = channel_id_input.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 再按|分割
                parts = line.split('|')
                for part in parts:
                    part = part.strip()
                    if part:
                        channel_ids.append(part)
            if not channel_ids:
                await update.message.reply_text("❌ 请输入有效的渠道ID")
                return
            
            # 获取正在添加的群组名称
            user_id = update.effective_user.id
            group_name = self.admin_state.get_group_name(user_id)
            if not group_name:
                await update.message.reply_text("❌ 群组名称丢失，请重新开始操作")
                return
            
            # 批量添加渠道ID
            success_count = 0
            failed_channels = []
            
            for channel_id in channel_ids:
                # 检查格式是否符合要求 (例如 FBA8-18)
                # if not re.match(r'^[A-Z0-9-]+$', channel_id):
                #     failed_channels.append(f"{channel_id}(格式错误)")
                #     continue
                
                # 添加渠道ID
                if self.config_loader.add_channel_id_to_group(group_name, channel_id):
                    success_count += 1
                else:
                    failed_channels.append(channel_id)
            
            # 生成结果消息
            result_message = f"📝 批量添加渠道ID结果\n━━━━━━━━━━━━━━━━\n"
            result_message += f"群组：{group_name}\n"
            result_message += f"成功添加：{success_count} 个\n"
            
            if failed_channels:
                result_message += f"失败：{len(failed_channels)} 个\n"
                result_message += f"失败列表：{', '.join(failed_channels)}"
            else:
                result_message += f"✅ 所有渠道ID添加成功！"
            
            await update.message.reply_text(result_message)
            
            # 清除状态并重新加载配置
            self.admin_state.clear_state(user_id)
            await self._reload_config(update)
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
                
        except Exception as e:
            logger.error(f"处理新渠道ID输入失败: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 处理新渠道ID输入失败: {str(e)}")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
    
    async def _handle_delete_channel_ids_input(self, update: Update, channel_ids_str: str) -> None:
        """处理删除渠道ID输入"""
        try:
            channel_ids_input = channel_ids_str.strip()
            if not channel_ids_input:
                await update.message.reply_text("❌ 渠道ID不能为空")
                return
            
            # 分割多个渠道ID（支持换行、|分隔和•符号格式）
            channel_ids_to_delete = []
            lines = channel_ids_input.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 处理带•符号的格式
                if line.startswith('•'):
                    channel_id = line[1:].strip()  # 去掉•符号
                    if channel_id:
                        channel_ids_to_delete.append(channel_id)
                else:
                    # 处理|分隔的格式
                    parts = line.split('|')
                    for part in parts:
                        part = part.strip()
                        if part:
                            channel_ids_to_delete.append(part)
            
            if not channel_ids_to_delete:
                await update.message.reply_text("❌ 请输入有效的渠道ID")
                return
            
            # 获取正在删除的群组名称
            user_id = update.effective_user.id
            group_name = self.admin_state.get_delete_channel_group_name(user_id)
            if not group_name:
                await update.message.reply_text("❌ 群组名称丢失，请重新开始操作")
                return
            
            # 获取群组索引
            groups_config = self.config_loader.get_groups_config()
            group_items = list(groups_config.items())
            group_index = None
            for i, (name, config) in enumerate(group_items):
                if name == group_name:
                    group_index = i
                    break
            
            if group_index is None:
                await update.message.reply_text("❌ 找不到指定的群组")
                return
            
            # 批量删除渠道ID
            success_count = 0
            failed_channels = []
            skipped_channels = []
            
            for channel_id in channel_ids_to_delete:
                # 检查渠道ID是否存在于该群组中
                current_channel_ids = [channel.get('id', '') for channel in group_items[group_index][1].get('channel_ids', [])]
                
                if channel_id not in current_channel_ids:
                    skipped_channels.append(channel_id)
                    continue
                
                # 删除渠道ID - 使用group_name而不是group_index
                if self.config_loader.remove_channel_id_from_group_by_name(group_name, channel_id):
                    success_count += 1
                else:
                    failed_channels.append(channel_id)
            
            # 生成结果消息
            result_message = f"🗑️ 批量删除渠道ID结果\n━━━━━━━━━━━━━━━━\n"
            result_message += f"群组：{group_name}\n"
            result_message += f"成功删除：{success_count} 个\n"
            
            if skipped_channels:
                result_message += f"跳过（不存在）：{len(skipped_channels)} 个\n"
                result_message += f"跳过列表：{', '.join(skipped_channels)}\n"
            
            if failed_channels:
                result_message += f"失败：{len(failed_channels)} 个\n"
                result_message += f"失败列表：{', '.join(failed_channels)}"
            elif not skipped_channels:
                result_message += f"✅ 所有渠道ID删除成功！"
            else:
                result_message += f"✅ 存在的渠道ID已全部删除！"
            
            await update.message.reply_text(result_message)
            
            # 清除状态并重新加载配置
            self.admin_state.clear_state(user_id)
            await self._reload_config(update)
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
                
        except Exception as e:
            logger.error(f"处理删除渠道ID输入失败: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 处理删除渠道ID输入失败: {str(e)}")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
    
    async def _handle_new_investment_group_name_input(self, update: Update, group_name: str) -> None:
        """处理新增代投组名称输入"""
        # 检查代投组名称是否已存在
        existing_groups = self.config_loader.get_groups_config()
        if group_name in existing_groups:
            await update.message.reply_text(f"⚠️ 代投组 {group_name} 已存在，请输入其他名称")
            return
        
        # 设置等待群组ID输入状态
        self.admin_state.set_waiting_for_new_investment_group_id(update.effective_user.id, group_name)
        
        await update.message.reply_text(
            f"📝 代投组名称：{group_name}\n\n现在请输入对应的群组ID（数字格式，如：-4632986596）："
        )
    
    async def _handle_new_investment_group_id_input(self, update: Update, group_id_str: str) -> None:
        """处理新增代投组群组ID输入"""
        try:
            group_id = int(group_id_str)
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的群组ID（数字格式）")
            return
            
        # 获取正在添加的代投组名称
        user_id = update.effective_user.id
        group_name = self.admin_state.get_investment_group_name(user_id)
        if not group_name:
            await update.message.reply_text("❌ 代投组名称丢失，请重新开始操作")
            return
            
        # 添加代投组配置
        if self.config_loader.add_investment_group_config(group_name, group_id):
            await update.message.reply_text(f"✅ 已成功添加代投组：{group_name} → {group_id}")
            
            # 清除状态并重新加载配置
            self.admin_state.clear_state(user_id)
            await self._reload_config(update)
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
        else:
            await update.message.reply_text(f"❌ 添加代投组失败")
            
            # 延迟后返回主菜单
            await asyncio.sleep(2)
            await self._back_to_main_menu(update)
    
    async def _reload_config(self, update_or_query) -> None:
        """重新加载配置"""
        try:
            # 重新加载配置文件
            self.config_loader.reload_config()
            
            # 更新管理员列表
            self.admins = self.config_loader.get_admins()
            
            # 通知其他组件更新配置
            await self._notify_components_config_updated()
            
            # 发送重载成功消息
            if hasattr(update_or_query, 'message'):
                # 是update对象
                await update_or_query.message.reply_text("🔄 配置已重新加载")
            elif hasattr(update_or_query, 'reply_text'):
                # 是message对象
                await update_or_query.reply_text("🔄 配置已重新加载")
            else:
                # 是query对象
                await update_or_query.message.reply_text("🔄 配置已重新加载")
            
            logger.info("管理员配置已重新加载")
            
        except Exception as e:
            error_msg = f"❌ 重新加载配置失败：{str(e)}"
            logger.error(error_msg)
            
            if hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text(error_msg)
            elif hasattr(update_or_query, 'reply_text'):
                await update_or_query.reply_text(error_msg)
            else:
                await update_or_query.message.reply_text(error_msg)
    
    async def _notify_components_config_updated(self):
        """通知所有组件配置已更新"""
        try:
            # 通知 user_command_handler 更新配置
            if self.user_command_handler:
                self.user_command_handler.update_config(self.config_loader)
                logger.info("已通知 UserCommandHandler 配置更新")
            
            # 通知 api_data_sender_manager 更新配置
            if self.api_data_sender_manager:
                self.api_data_sender_manager.update_config(self.config_loader)
                logger.info("已通知 ApiDataSenderManager 配置更新")
            
            logger.info("已通知所有组件配置更新")
        except Exception as e:
            logger.error(f"通知组件配置更新失败: {str(e)}")
    
    async def _handle_config_google_sheets_request(self, query, page: int = 0) -> None:
        """处理Google表格配置请求"""
        try:
            # 获取所有群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                await query.edit_message_text("❌ 未找到任何群组配置")
                return
            
            # 获取Google表格配置
            google_sheets_config = self.config_loader.get_google_sheets_config()
            group_spreadsheets = google_sheets_config.get('group_spreadsheets', {})
            
            # 转换为列表以便分页
            group_items = list(groups_config.items())
            
            # 计算分页
            total_items = len(group_items)
            total_pages = math.ceil(total_items / self.items_per_page)
            start_index = page * self.items_per_page
            end_index = min(start_index + self.items_per_page, total_items)
            
            # 构建消息头部（不分页的基本信息）
            message = f"📊 Google表格配置 (第{page + 1}/{total_pages}页)\n━━━━━━━━━━━━━━━━\n"
            message += f"📋 日报工作表: {google_sheets_config.get('daily_sheet_name', 'Daily-Report')}\n"
            message += f"📋 时报工作表: {google_sheets_config.get('hourly_sheet_name', 'Hourly-Report')}\n"
            message += f"🔑 凭据文件: {google_sheets_config.get('credentials_file', 'credentials.json')}\n\n"
            message += "📝 代投组表格配置:\n"
            
            # 构建键盘
            keyboard = []
            
            # 显示当前页的群组
            for i in range(start_index, end_index):
                group_name, group_config = group_items[i]
                spreadsheet_id = group_spreadsheets.get(group_name, "未配置")
                status = "✅" if spreadsheet_id != "未配置" else "❌"
                display_id = spreadsheet_id if len(spreadsheet_id) <= 30 else f"{spreadsheet_id[:27]}..."
                message += f"{status} {group_name}: {display_id}\n"
                
                # 为每个群组添加配置按钮
                if spreadsheet_id == "未配置":
                    keyboard.append([
                        InlineKeyboardButton(f"📝 配置 {group_name}", callback_data=f"set_spreadsheet_{group_name}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton(f"🔄 更新 {group_name}", callback_data=f"set_spreadsheet_{group_name}"),
                        InlineKeyboardButton(f"🗑️ 删除 {group_name}", callback_data=f"remove_spreadsheet_{group_name}")
                    ])
            
            # 添加分页按钮
            if total_pages > 1:
                page_buttons = []
                if page > 0:
                    page_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"google_sheets_page_{page - 1}"))
                if page < total_pages - 1:
                    page_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"google_sheets_page_{page + 1}"))
                if page_buttons:
                    keyboard.append(page_buttons)
            
            # 添加返回按钮
            keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup)
            logger.info(f"Google表格配置界面已显示 (第{page + 1}/{total_pages}页)")
            
        except Exception as e:
            logger.error(f"处理Google表格配置请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示Google表格配置界面失败: {str(e)}")
    
    async def _handle_set_spreadsheet_request(self, query, group_name: str) -> None:
        """处理设置表格ID请求"""
        try:
            user_id = query.from_user.id
            logger.info(f"设置用户 {user_id} 等待输入群组 {group_name} 的表格ID")
            
            # 设置状态
            self.admin_state.set_waiting_for_spreadsheet_id(user_id, group_name)
            
            keyboard = [[InlineKeyboardButton("🔙 返回配置菜单", callback_data="config_google_sheets")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📊 配置Google表格\n━━━━━━━━━━━━━━━━\n"
                f"群组: {group_name}\n"
                f"请输入Google表格ID：\n\n"
                f"💡 提示：表格ID可以从Google表格URL中获取\n"
                f"例如：https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit\n"
                f"表格ID为：1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                reply_markup=reply_markup
            )
            logger.info(f"设置群组 {group_name} 表格ID界面已显示")
            
        except Exception as e:
            logger.error(f"处理设置表格ID请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 显示设置表格ID界面失败: {str(e)}")
    
    async def _handle_remove_spreadsheet_request(self, query, group_name: str) -> None:
        """处理删除表格ID请求"""
        try:
            # 删除群组的表格ID配置
            success = self.config_loader.remove_group_spreadsheet_id(group_name)
            
            if success:
                await query.edit_message_text(
                    f"✅ 成功删除群组 {group_name} 的表格ID配置\n\n"
                    f"该群组将不再写入Google表格，但数据播报功能不受影响。",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 返回配置菜单", callback_data="config_google_sheets")
                    ]])
                )
                logger.info(f"成功删除群组 {group_name} 的表格ID配置")
            else:
                await query.edit_message_text(
                    f"❌ 删除群组 {group_name} 的表格ID配置失败\n\n"
                    f"可能该群组未配置表格ID。",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 返回配置菜单", callback_data="config_google_sheets")
                    ]])
                )
                logger.warning(f"删除群组 {group_name} 的表格ID配置失败")
            
        except Exception as e:
            logger.error(f"处理删除表格ID请求失败: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ 删除表格ID配置失败: {str(e)}")
    
    async def _handle_spreadsheet_id_input(self, update: Update, spreadsheet_id: str) -> None:
        """处理表格ID输入"""
        try:
            user_id = update.effective_user.id
            group_name = self.admin_state.get_spreadsheet_group_name(user_id)
            
            if not group_name:
                await update.message.reply_text("❌ 无法获取群组名称，请重新开始配置")
                self.admin_state.clear_state(user_id)
                return
            
            # 验证表格ID格式（简单的长度和字符检查）
            spreadsheet_id = spreadsheet_id.strip()
            if len(spreadsheet_id) < 20 or len(spreadsheet_id) > 50:
                await update.message.reply_text("❌ 表格ID格式不正确，请检查后重新输入")
                return
            
            # 设置群组的表格ID
            success = self.config_loader.set_group_spreadsheet_id(group_name, spreadsheet_id)
            
            if success:
                await update.message.reply_text(
                    f"✅ 成功设置群组 {group_name} 的表格ID：{spreadsheet_id}\n\n"
                    f"该群组的数据将自动写入Google表格。"
                )
                logger.info(f"成功设置群组 {group_name} 的表格ID: {spreadsheet_id}")
            else:
                await update.message.reply_text(f"❌ 设置群组 {group_name} 的表格ID失败")
                logger.error(f"设置群组 {group_name} 的表格ID失败")
            
            # 清除状态
            self.admin_state.clear_state(user_id)
            
            # 延迟后返回Google表格配置菜单
            await asyncio.sleep(2)
            await self._back_to_google_sheets_config(update)
            
        except Exception as e:
            logger.error(f"处理表格ID输入失败: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 处理表格ID输入失败: {str(e)}")
            self.admin_state.clear_state(update.effective_user.id)
    
    async def _back_to_google_sheets_config(self, update_or_query) -> None:
        """返回Google表格配置菜单"""
        try:
            # 清除用户状态
            if hasattr(update_or_query, 'from_user'):
                # 是query对象
                user_id = update_or_query.from_user.id
                self.admin_state.clear_state(user_id)
            elif hasattr(update_or_query, 'effective_user'):
                # 是update对象
                user_id = update_or_query.effective_user.id
                self.admin_state.clear_state(user_id)
            
            # 创建一个模拟的query对象来调用Google表格配置
            if hasattr(update_or_query, 'message'):
                # 是update对象，需要创建模拟query
                class MockQuery:
                    def __init__(self, message):
                        self.message = message
                        
                    async def edit_message_text(self, text, reply_markup=None):
                        # 发送新消息而不是编辑
                        await self.message.reply_text(text, reply_markup=reply_markup)
                
                mock_query = MockQuery(update_or_query.message)
                await self._handle_config_google_sheets_request(mock_query)
            else:
                # 是query对象，直接调用
                await self._handle_config_google_sheets_request(update_or_query)
                
        except Exception as e:
            logger.error(f"返回Google表格配置菜单失败: {str(e)}", exc_info=True)
            if hasattr(update_or_query, 'edit_message_text'):
                await update_or_query.edit_message_text("❌ 返回Google表格配置菜单失败")
            elif hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text("❌ 返回Google表格配置菜单失败")