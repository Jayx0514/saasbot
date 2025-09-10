import re
import asyncio
import time
from typing import Optional, Union
from telegram import Update

# 添加全局速率限制器
class RateLimiter:
    def __init__(self, max_per_second=25):
        self.max_per_second = max_per_second
        self.tokens = max_per_second  # 令牌桶初始容量
        self.last_token_time = time.time()  # 上次更新令牌的时间
        self.lock = asyncio.Lock()
        self._task = None
        self._loop = None
    
    async def acquire(self):
        """获取发送权限，使用令牌桶算法"""
        async with self.lock:
            current_time = time.time()
            time_passed = current_time - self.last_token_time
            
            # 根据经过的时间添加令牌
            new_tokens = time_passed * self.max_per_second
            self.tokens = min(self.max_per_second, self.tokens + new_tokens)
            self.last_token_time = current_time
            
            if self.tokens >= 1:
                # 有令牌可用
                self.tokens -= 1
                return True, False  # 不需要延迟
            else:
                # 计算需要等待的时间
                wait_time = (1 - self.tokens) / self.max_per_second
                await asyncio.sleep(wait_time)
                self.tokens = 0
                self.last_token_time = time.time()
                return True, True  # 已经等待过，不需要额外延迟
    
    async def start_async(self):
        """异步方式启动速率限制器"""
        self.tokens = self.max_per_second
        self.last_token_time = time.time()
    
    async def stop_async(self):
        """异步方式停止速率限制器"""
        pass
    
    def start(self):
        """同步方式启动速率限制器（不执行任何操作）"""
        pass
    
    def stop(self):
        """同步方式停止速率限制器（不执行任何操作）"""
        pass

# 创建全局速率限制器实例
global_rate_limiter = RateLimiter(max_per_second=25)

async def get_channel_id(update: Update) -> str | None:
    """获取频道ID"""
    if not update.message or not update.message.forward_origin:
        return None
    
    origin = update.message.forward_origin
    if origin.type == 'channel':
        return str(origin.chat.id)
    return None

class AdminState:
    """管理员状态管理类 - 重写版本"""
    def __init__(self):
        self.states = {}  # 用户状态存储
        self.selected_group = {}  # 组选择状态（保留兼容性）

    def _set_state(self, user_id: int, state: str, **kwargs) -> None:
        """设置用户状态（内部方法）"""
        self.states[user_id] = {'state': state, **kwargs}

    def _get_state(self, user_id: int) -> Optional[dict]:
        """获取用户状态（内部方法）"""
        return self.states.get(user_id)

    def _is_state(self, user_id: int, state: str) -> bool:
        """检查用户是否处于指定状态（内部方法）"""
        user_state = self._get_state(user_id)
        return user_state is not None and user_state.get('state') == state

    def clear_state(self, user_id: int) -> None:
        """清除用户的所有状态"""
        self.states.pop(user_id, None)
        self.selected_group.pop(user_id, None)

    # === 管理员相关状态 ===
    def set_waiting_for_add_admin_id(self, user_id: int) -> None:
        """设置用户正在等待输入新管理员ID"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_add_admin_id')
        
    def is_waiting_for_add_admin_id(self, user_id: int) -> bool:
        """检查用户是否正在等待输入新管理员ID"""
        return self._is_state(user_id, 'waiting_for_add_admin_id')

    def set_admin_list_selection(self, user_id: int, admin_list: list, page: int = 0) -> None:
        """设置管理员列表选择状态"""
        self.clear_state(user_id)
        self._set_state(user_id, 'admin_list_selection', admin_list=admin_list, page=page)
        
    def is_admin_list_selection(self, user_id: int) -> bool:
        """检查是否在管理员列表选择状态"""
        return self._is_state(user_id, 'admin_list_selection')
    
    def get_admin_list_data(self, user_id: int) -> dict:
        """获取管理员列表数据"""
        user_state = self._get_state(user_id)
        if user_state and user_state.get('state') == 'admin_list_selection':
            return {
                'admin_list': user_state.get('admin_list', []),
                'page': user_state.get('page', 0)
            }
        return {'admin_list': [], 'page': 0}

    # === 渠道分组相关状态 ===
    def set_waiting_for_new_channel_group_name(self, user_id: int) -> None:
        """设置用户正在等待输入新渠道名称"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_new_channel_group_name')
        
    def is_waiting_for_new_channel_group_name(self, user_id: int) -> bool:
        """检查用户是否正在等待输入新渠道名称"""
        return self._is_state(user_id, 'waiting_for_new_channel_group_name')
                
    def set_waiting_for_channel_group_id(self, user_id: int, channel_name: str) -> None:
        """设置用户正在等待输入渠道群组ID"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_channel_group_id', channel_name=channel_name)
        
    def is_waiting_for_channel_group_id(self, user_id: int) -> bool:
        """检查用户是否正在等待输入渠道群组ID"""
        return self._is_state(user_id, 'waiting_for_channel_group_id')

    def get_channel_name(self, user_id: int) -> Optional[str]:
        """获取当前正在处理的渠道名称"""
        user_state = self._get_state(user_id)
        if user_state and user_state.get('state') == 'waiting_for_channel_group_id':
            return user_state.get('channel_name')
        return None

    def set_channel_group_list_selection(self, user_id: int, channel_groups: dict, page: int = 0) -> None:
        """设置渠道分组列表选择状态"""
        self.clear_state(user_id)
        self._set_state(user_id, 'channel_group_list_selection', channel_groups=channel_groups, page=page)
        
    def is_channel_group_list_selection(self, user_id: int) -> bool:
        """检查是否在渠道分组列表选择状态"""
        return self._is_state(user_id, 'channel_group_list_selection')
    
    def get_channel_group_list_data(self, user_id: int) -> dict:
        """获取渠道分组列表数据"""
        user_state = self._get_state(user_id)
        if user_state and user_state.get('state') == 'channel_group_list_selection':
            return {
                'channel_groups': user_state.get('channel_groups', {}),
                'page': user_state.get('page', 0)
            }
        return {'channel_groups': {}, 'page': 0}

    # === 新群组配置相关状态 ===
    def set_waiting_for_new_channel_id(self, user_id: int, group_name: str) -> None:
        """设置用户正在等待输入新渠道ID"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_new_channel_id', group_name=group_name)
        
    def is_waiting_for_new_channel_id(self, user_id: int) -> bool:
        """检查用户是否正在等待输入新渠道ID"""
        return self._is_state(user_id, 'waiting_for_new_channel_id')

    def get_group_name(self, user_id: int) -> Optional[str]:
        """获取当前正在处理的群组名称"""
        user_state = self._get_state(user_id)
        if user_state and user_state.get('state') == 'waiting_for_new_channel_id':
            return user_state.get('group_name')
        return None

    def set_channel_id_list_selection(self, user_id: int, channel_ids: list, group_index: int, page: int = 0) -> None:
        """设置渠道ID列表选择状态"""
        self.clear_state(user_id)
        self._set_state(user_id, 'channel_id_list_selection', 
                       channel_ids=channel_ids, selected_group_index=group_index, page=page)
        
    def is_channel_id_list_selection(self, user_id: int) -> bool:
        """检查是否在渠道ID列表选择状态"""
        return self._is_state(user_id, 'channel_id_list_selection')
    
    def get_channel_id_list_data(self, user_id: int) -> dict:
        """获取渠道ID列表数据"""
        user_state = self._get_state(user_id)
        if user_state and user_state.get('state') == 'channel_id_list_selection':
            return {
                'channel_ids': user_state.get('channel_ids', []),
                'selected_group_index': user_state.get('selected_group_index', 0),
                'page': user_state.get('page', 0)
            }
        return {'channel_ids': [], 'selected_group_index': 0, 'page': 0}

    # === 兼容性方法（保留旧接口） ===
    def set_waiting_for_delete_admin(self, user_id: int) -> None:
        """设置用户正在等待输入要删除的管理员ID（兼容性方法）"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_delete_admin')
        
    def is_waiting_for_delete_admin(self, user_id: int) -> bool:
        """检查用户是否正在等待输入要删除的管理员ID（兼容性方法）"""
        return self._is_state(user_id, 'waiting_for_delete_admin')
    
    def set_waiting_for_delete_channel_group(self, user_id: int) -> None:
        """设置用户正在等待输入要删除的渠道分组名称（兼容性方法）"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_delete_channel_group')
        
    def is_waiting_for_delete_channel_group(self, user_id: int) -> bool:
        """检查用户是否正在等待输入要删除的渠道分组名称（兼容性方法）"""
        return self._is_state(user_id, 'waiting_for_delete_channel_group')

    # === 组选择相关（保留兼容性） ===
    def set_selected_group(self, user_id: int, group_id: str) -> None:
        """设置用户选择的组ID"""
        self.selected_group[user_id] = group_id

    def get_selected_group(self, user_id: int) -> Optional[str]:
        """获取用户选择的组ID"""
        return self.selected_group.get(user_id)

    def _clear_states_except_group(self, user_id: int) -> None:
        """清除除了组选择状态之外的所有状态（兼容性方法）"""
        group_id = self.selected_group.get(user_id)
        self.states.pop(user_id, None)
        if group_id:
            self.selected_group[user_id] = group_id

    # === 调试和工具方法 ===
    def get_user_state(self, user_id: int) -> Optional[dict]:
        """获取用户的完整状态（调试用）"""
        return self._get_state(user_id)

    def get_all_states(self) -> dict:
        """获取所有用户状态（调试用）"""
        return self.states.copy()

    def clear_all_states(self) -> None:
        """清除所有用户状态（调试用）"""
        self.states.clear()

    def get_state(self, user_id: int) -> Optional[dict]:
        """获取用户状态（通用方法）"""
        return self._get_state(user_id)

    # === 代投组相关状态 ===
    def set_waiting_for_new_investment_group_name(self, user_id: int) -> None:
        """设置用户正在等待输入新代投组名称"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_new_investment_group_name')
        
    def is_waiting_for_new_investment_group_name(self, user_id: int) -> bool:
        """检查用户是否正在等待输入新代投组名称"""
        return self._is_state(user_id, 'waiting_for_new_investment_group_name')

    def set_waiting_for_new_investment_group_id(self, user_id: int, group_name: str) -> None:
        """设置用户正在等待输入代投组群组ID"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_new_investment_group_id', group_name=group_name)
        
    def is_waiting_for_new_investment_group_id(self, user_id: int) -> bool:
        """检查用户是否正在等待输入代投组群组ID"""
        return self._is_state(user_id, 'waiting_for_new_investment_group_id')

    def get_investment_group_name(self, user_id: int) -> Optional[str]:
        """获取投资组名称"""
        state = self._get_state(user_id)
        return state.get('group_name') if state else None
    
    # === 删除渠道ID相关状态 ===
    def set_waiting_for_delete_channel_ids(self, user_id: int, group_name: str) -> None:
        """设置用户正在等待输入要删除的渠道ID列表"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_delete_channel_ids', group_name=group_name)
        
    def is_waiting_for_delete_channel_ids(self, user_id: int) -> bool:
        """检查用户是否正在等待输入要删除的渠道ID列表"""
        return self._is_state(user_id, 'waiting_for_delete_channel_ids')
        
    def get_delete_channel_group_name(self, user_id: int) -> Optional[str]:
        """获取要删除渠道的群组名称"""
        state = self._get_state(user_id)
        return state.get('group_name') if state else None
    
    # === Google表格配置相关状态 ===
    def set_waiting_for_spreadsheet_id(self, user_id: int, group_name: str) -> None:
        """设置用户正在等待输入表格ID"""
        self.clear_state(user_id)
        self._set_state(user_id, 'waiting_for_spreadsheet_id', group_name=group_name)
        
    def is_waiting_for_spreadsheet_id(self, user_id: int) -> bool:
        """检查用户是否正在等待输入表格ID"""
        return self._is_state(user_id, 'waiting_for_spreadsheet_id')
        
    def get_spreadsheet_group_name(self, user_id: int) -> Optional[str]:
        """获取要配置表格的群组名称"""
        state = self._get_state(user_id)
        return state.get('group_name') if state else None