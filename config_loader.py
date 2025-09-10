import os
import yaml
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# 配置日志
logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_path: str = "config.yaml"):
        """初始化配置加载器"""
        self.config_path = config_path
        self.config = self._load_config()
        self.token_file = "token_cache.json"
        
    def save_token_to_file(self, token: str, expiry_time: float) -> bool:
        """保存token到文件
        
        Args:
            token: 登录token
            expiry_time: token过期时间戳
            
        Returns:
            是否保存成功
        """
        try:
            token_data = {
                "token": token,
                "expiry_time": expiry_time,
                "created_at": datetime.now().isoformat()
            }
            
            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Token已保存到文件: {self.token_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存token到文件失败: {str(e)}")
            return False
    
    def load_token_from_file(self) -> Optional[Dict[str, Any]]:
        """从文件加载token
        
        Returns:
            token数据字典，如果文件不存在或已过期返回None
        """
        try:
            if not os.path.exists(self.token_file):
                logger.info("Token文件不存在")
                return None
            
            with open(self.token_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            
            # 检查token是否过期
            current_time = datetime.now().timestamp()
            if current_time >= token_data.get('expiry_time', 0):
                logger.info("Token已过期")
                return None
            
            logger.info("从文件加载到有效token")
            return token_data
            
        except Exception as e:
            logger.error(f"从文件加载token失败: {str(e)}")
            return None
    
    def clear_token_file(self) -> bool:
        """清除token文件
        
        Returns:
            是否清除成功
        """
        try:
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
                logger.info("Token文件已清除")
            return True
        except Exception as e:
            logger.error(f"清除token文件失败: {str(e)}")
            return False

    def get_channel_groups_config(self) -> Dict[str, List[int]]:
        """获取渠道来源对应的目标群组配置"""
        if 'channel_groups' not in self.config:
            return {}
        
        return self.config['channel_groups']
    
    def add_channel_group_config(self, channel_name: str, group_id: int) -> bool:
        """添加渠道群组配置到channel_groups"""
        try:
            if 'channel_groups' not in self.config:
                self.config['channel_groups'] = {}
                
            # 如果渠道已存在，添加到列表中；如果不存在，创建新列表
            if channel_name in self.config['channel_groups']:
                if group_id not in self.config['channel_groups'][channel_name]:
                    self.config['channel_groups'][channel_name].append(group_id)
            else:
                self.config['channel_groups'][channel_name] = [group_id]
                
            self.save_config()
            return True
        except Exception as e:
            logger.error(f"添加渠道群组配置失败: {str(e)}")
            return False
    
    def remove_channel_group_config(self, channel_name: str) -> bool:
        """删除渠道群组配置从channel_groups"""
        try:
            if ('channel_groups' in self.config and 
                channel_name in self.config['channel_groups']):
                del self.config['channel_groups'][channel_name]
                self.save_config()
                return True
            return False
        except Exception as e:
            logger.error(f"删除渠道群组配置失败: {str(e)}")
            return False
    
    def get_channel_name_by_group_id(self, group_id: int) -> str:
        """根据群组ID获取对应的渠道名称
        
        Args:
            group_id: 群组ID
            
        Returns:
            渠道名称，如果找不到返回空字符串
        """
        try:
            channel_groups_config = self.get_channel_groups_config()
            logger.info(f"查找群组ID {group_id} 对应的渠道名称，当前配置: {channel_groups_config}")
            
            for channel_name, group_ids in channel_groups_config.items():
                logger.info(f"检查渠道 {channel_name}，群组列表: {group_ids}，类型: {type(group_ids)}")
                if group_id in group_ids:
                    logger.info(f"找到匹配！群组 {group_id} 属于渠道 {channel_name}")
                    return channel_name
            
            logger.warning(f"未找到群组ID {group_id} 对应的渠道名称")
            return ""
        except Exception as e:
            logger.error(f"根据群组ID获取渠道名称失败: {str(e)}")
            return ""
        
    def get_channel_groups(self) -> Dict[str, str]:
        """获取渠道群组配置"""
        if 'channel_groups' not in self.config:
            self.config['channel_groups'] = {}
        return self.config['channel_groups']
    
    def update_channel_group(self, channel_name: str, new_id: str) -> bool:
        """更新渠道群组ID"""
        try:
            if 'channel_groups' not in self.config:
                self.config['channel_groups'] = {}
                
            if channel_name not in self.config['channel_groups']:
                return False
                
            self.config['channel_groups'][channel_name] = new_id
            self.save_config()
            return True
        except Exception as e:
            logger.error(f"更新渠道群组ID失败: {str(e)}")
            return False
    
    def add_channel_group(self, channel_name: str, channel_id: str) -> bool:
        """添加渠道群组"""
        try:
            if 'channel_groups' not in self.config:
                self.config['channel_groups'] = {}
                
            self.config['channel_groups'][channel_name] = channel_id
            self.save_config()
            return True
        except Exception as e:
            logger.error(f"添加渠道群组失败: {str(e)}")
            return False
        
    def get_sending_interval_config(self) -> Dict[str, int]:
        """获取发送间隔配置"""
        if 'settings' not in self.config or 'sending_interval' not in self.config['settings']:
            # 默认配置：每20个群组间隔2秒
            return {
                'batch_size': 20,
                'delay_seconds': 2
            }
        
        interval_config = self.config['settings']['sending_interval']
        return {
            'batch_size': interval_config.get('batch_size', 20),
            'delay_seconds': interval_config.get('delay_seconds', 2)
        }
        
    def get_api_config(self) -> Dict[str, str]:
        """获取API配置（已废弃，保留用于兼容性）"""
        return {}
    
    def get_api_login_config(self) -> Dict[str, str]:
        """获取API登录配置"""
        api_config = self.config.get('api', {})
        login_config = api_config.get('login', {})
        return {
            'url': login_config.get('url', ''),
            'username': login_config.get('username', ''),
            'password': login_config.get('password', ''),
            'totp_secret': login_config.get('totp_secret', '')
        }
    
    def get_api_data_config(self) -> Dict[str, Any]:
        """获取API数据配置（已废弃，保留用于兼容性）"""
        logger.warning("get_api_data_config 已废弃，现在使用新的包数据接口")
        return {
            'url': '',
            'page_size': 1000
        }
    
    def get_ssl_verify(self) -> bool:
        """获取SSL验证配置
        
        Returns:
            是否进行SSL证书验证，默认为True（安全）
        """
        api_config = self.config.get('api', {})
        return api_config.get('ssl_verify', True)
        
    def get_api_data_sending_config(self) -> Dict[str, Any]:
        """获取 API 数据发送配置"""
        if 'api' not in self.config or 'data_sending' not in self.config['api']:
            return {
                'hourly_report': {'enabled': False},
                'daily_report': {'enabled': False}
            }
        
        return self.config['api']['data_sending']


    
    def add_admin(self, admin_id: int) -> bool:
        """添加新管理员"""
        try:
            if 'admins' not in self.config:
                self.config['admins'] = []
            if admin_id not in self.config['admins']:
                self.config['admins'].append(admin_id)
                self.save_config()
            return True
        except Exception as e:
            logger.error(f"添加管理员失败: {str(e)}")
            return False
    
    def remove_admin(self, admin_id: int) -> bool:
        """删除管理员"""
        try:
            if 'admins' in self.config and admin_id in self.config['admins']:
                self.config['admins'].remove(admin_id)
                self.save_config()
                return True
            return False
        except Exception as e:
            logger.error(f"删除管理员失败: {str(e)}")
            return False
    
    def remove_channel_group(self, channel_name: str) -> bool:
        """删除渠道分组"""
        try:
            if 'channel_groups' in self.config and channel_name in self.config['channel_groups']:
                del self.config['channel_groups'][channel_name]
                self.save_config()
                return True
            return False
        except Exception as e:
            logger.error(f"删除渠道分组失败: {str(e)}")
            return False

    # 删除重复的旧方法:
    # - update_target_channel_link (旧版本)
    # - update_target_channel_id (旧版本)
    # - update_source_channel_id (旧版本)
    # - add_target_channel (旧版本)
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件 {self.config_path} 不存在")
        
        with open(self.config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        
        return config
    
    def save_config(self) -> None:
        """保存配置到YAML文件"""
        with open(self.config_path, 'w', encoding='utf-8') as file:
            yaml.dump(self.config, file, allow_unicode=True)
    
    def get_bot_token(self) -> str:
        """获取机器人Token"""
        return self.config['bot']['token']
    
    # 删除重复的方法:
    # - get_source_channel
    # - get_target_channels
    # - update_target_channel_link
    # - update_target_channel_id
    # - update_source_channel_id
    # - add_target_channel
    
    def get_admins(self) -> List[int]:
        """获取管理员ID列表"""
        return self.config['admins']
    
    def get_forward_delay(self) -> int:
        """获取转发延迟（毫秒）"""
        return self.config['settings']['forward_delay_ms']
    
    def get_groups_config(self) -> Dict[str, Any]:
        """获取群组配置"""
        if 'groups' not in self.config:
            return {}
        
        return self.config['groups']
    
    def get_channel_ids_by_group_id(self, group_id: int) -> List[str]:
        """根据群组ID获取对应的渠道ID列表
        
        Args:
            group_id: 群组ID
            
        Returns:
            渠道ID列表，如果找不到返回空列表
        """
        try:
            groups_config = self.get_groups_config()
            # logger.info(f"查找群组ID {group_id} 对应的渠道ID列表，当前配置: {groups_config}")
            
            for group_name, group_config in groups_config.items():
                tg_group = group_config.get('tg_group', '')
                # 转换为整数进行比较
                try:
                    config_group_id = int(tg_group)
                    if config_group_id == group_id:
                        channel_ids = group_config.get('channel_ids', [])
                        # 提取渠道ID
                        channel_id_list = [channel.get('id', '') for channel in channel_ids if channel.get('id')]
                        # logger.info(f"找到匹配！群组 {group_id} 对应的渠道ID列表: {channel_id_list}")
                        return channel_id_list
                except (ValueError, TypeError):
                    logger.warning(f"群组配置中的tg_group不是有效数字: {tg_group}")
                    continue
            
            logger.warning(f"未找到群组ID {group_id} 对应的渠道ID列表")
            return []
        except Exception as e:
            logger.error(f"根据群组ID获取渠道ID列表失败: {str(e)}")
            return []
    
    def add_channel_id_to_group(self, group_name: str, channel_id: str) -> bool:
        """向指定群组添加渠道ID
        
        Args:
            group_name: 群组名称
            channel_id: 渠道ID
            
        Returns:
            是否添加成功
        """
        try:
            groups_config = self.get_groups_config()
            if group_name not in groups_config:
                logger.error(f"群组 {group_name} 不存在")
                return False
            
            group_config = groups_config[group_name]
            channel_ids = group_config.get('channel_ids', [])
            
            # 检查是否已存在
            for existing_channel in channel_ids:
                if existing_channel.get('id') == channel_id:
                    logger.warning(f"渠道ID {channel_id} 已存在于群组 {group_name} 中")
                    return False
            
            # 添加新渠道ID
            channel_ids.append({'id': channel_id})
            group_config['channel_ids'] = channel_ids
            
            # 保存配置
            self.save_config()
            logger.info(f"成功添加渠道ID {channel_id} 到群组 {group_name}")
            return True
            
        except Exception as e:
            logger.error(f"添加渠道ID到群组失败: {str(e)}")
            return False
    
    def remove_channel_id_from_group(self, group_index: int, channel_id: str) -> bool:
        """从指定群组删除渠道ID
        
        Args:
            group_index: 群组索引
            channel_id: 渠道ID
            
        Returns:
            是否删除成功
        """
        try:
            groups_config = self.get_groups_config()
            group_items = list(groups_config.items())
            
            if group_index < 0 or group_index >= len(group_items):
                logger.error(f"无效的群组索引: {group_index}")
                return False
            
            group_name, group_config = group_items[group_index]
            channel_ids = group_config.get('channel_ids', [])
            
            # 查找并删除指定渠道ID
            for i, channel in enumerate(channel_ids):
                if channel.get('id') == channel_id:
                    del channel_ids[i]
                    group_config['channel_ids'] = channel_ids
                    
                    # 保存配置
                    self.save_config()
                    logger.info(f"成功从群组 {group_name} 删除渠道ID {channel_id}")
                    return True
            
            logger.warning(f"在群组 {group_name} 中未找到渠道ID {channel_id}")
            return False
            
        except Exception as e:
            logger.error(f"从群组删除渠道ID失败: {str(e)}")
            return False
    
    def remove_channel_id_from_group_by_name(self, group_name: str, channel_id: str) -> bool:
        """从指定群组删除渠道ID（通过群组名称）
        
        Args:
            group_name: 群组名称
            channel_id: 渠道ID
            
        Returns:
            是否删除成功
        """
        try:
            groups_config = self.get_groups_config()
            
            if group_name not in groups_config:
                logger.error(f"群组 {group_name} 不存在")
                return False
            
            group_config = groups_config[group_name]
            channel_ids = group_config.get('channel_ids', [])
            
            # 查找并删除指定渠道ID
            for i, channel in enumerate(channel_ids):
                if channel.get('id') == channel_id:
                    del channel_ids[i]
                    group_config['channel_ids'] = channel_ids
                    
                    # 保存配置
                    self.save_config()
                    logger.info(f"成功从群组 {group_name} 删除渠道ID {channel_id}")
                    return True
            
            logger.warning(f"在群组 {group_name} 中未找到渠道ID {channel_id}")
            return False
            
        except Exception as e:
            logger.error(f"从群组删除渠道ID失败: {str(e)}")
            return False
    
    def add_investment_group_config(self, group_name: str, group_id: int) -> bool:
        """添加代投组配置
        
        Args:
            group_name: 代投组名称
            group_id: 群组ID
            
        Returns:
            是否添加成功
        """
        try:
            groups_config = self.get_groups_config()
            
            # 检查代投组名称是否已存在
            if group_name in groups_config:
                logger.warning(f"代投组 {group_name} 已存在")
                return False
            
            # 创建新的代投组配置
            new_group_config = {
                'name': group_name,
                'tg_group': str(group_id),
                'channel_ids': []
            }
            
            groups_config[group_name] = new_group_config
            
            # 保存配置
            self.save_config()
            logger.info(f"成功添加代投组配置：{group_name} → {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加代投组配置失败: {str(e)}")
            return False
    
    def remove_group_config(self, group_name: str) -> bool:
        """删除代投组配置
        
        Args:
            group_name: 代投组名称
            
        Returns:
            是否删除成功
        """
        try:
            groups_config = self.get_groups_config()
            
            if group_name not in groups_config:
                logger.warning(f"代投组 {group_name} 不存在")
                return False
            
            # 删除代投组配置
            del groups_config[group_name]
            
            # 保存配置
            self.save_config()
            logger.info(f"成功删除代投组配置：{group_name}")
            return True
            
        except Exception as e:
            logger.error(f"删除代投组配置失败: {str(e)}")
            return False

    def reload_config(self):
        """重新加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
    
    def get_google_sheets_config(self) -> Dict[str, Any]:
        """获取Google表格配置
        
        Returns:
            Google表格配置字典
        """
        if 'google_sheets' not in self.config:
            return {}
        
        return self.config['google_sheets']
    
    def get_group_spreadsheet_id(self, group_name: str) -> Optional[str]:
        """获取指定群组的表格ID
        
        Args:
            group_name: 群组名称
            
        Returns:
            表格ID，如果未配置返回None
        """
        try:
            google_sheets_config = self.get_google_sheets_config()
            group_spreadsheets = google_sheets_config.get('group_spreadsheets', {})
            return group_spreadsheets.get(group_name)
        except Exception as e:
            logger.error(f"获取群组 {group_name} 的表格ID失败: {str(e)}")
            return None
    
    def set_group_spreadsheet_id(self, group_name: str, spreadsheet_id: str) -> bool:
        """设置指定群组的表格ID
        
        Args:
            group_name: 群组名称
            spreadsheet_id: 表格ID
            
        Returns:
            是否设置成功
        """
        try:
            if 'google_sheets' not in self.config:
                self.config['google_sheets'] = {}
            
            if 'group_spreadsheets' not in self.config['google_sheets']:
                self.config['google_sheets']['group_spreadsheets'] = {}
            
            self.config['google_sheets']['group_spreadsheets'][group_name] = spreadsheet_id
            self.save_config()
            logger.info(f"成功设置群组 {group_name} 的表格ID: {spreadsheet_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置群组 {group_name} 的表格ID失败: {str(e)}")
            return False
    
    def remove_group_spreadsheet_id(self, group_name: str) -> bool:
        """删除指定群组的表格ID配置
        
        Args:
            group_name: 群组名称
            
        Returns:
            是否删除成功
        """
        try:
            google_sheets_config = self.get_google_sheets_config()
            group_spreadsheets = google_sheets_config.get('group_spreadsheets', {})
            
            if group_name in group_spreadsheets:
                del group_spreadsheets[group_name]
                self.save_config()
                logger.info(f"成功删除群组 {group_name} 的表格ID配置")
                return True
            
            logger.warning(f"群组 {group_name} 未配置表格ID")
            return False
            
        except Exception as e:
            logger.error(f"删除群组 {group_name} 的表格ID配置失败: {str(e)}")
            return False
    
    def get_google_sheets_credentials_file(self) -> str:
        """获取Google表格凭据文件路径
        
        Returns:
            凭据文件路径
        """
        google_sheets_config = self.get_google_sheets_config()
        return google_sheets_config.get('credentials_file', 'credentials.json')
    
    def get_daily_sheet_name(self) -> str:
        """获取日报工作表名称
        
        Returns:
            日报工作表名称
        """
        google_sheets_config = self.get_google_sheets_config()
        return google_sheets_config.get('daily_sheet_name', 'Daily-Report')
    
    def get_hourly_sheet_name(self) -> str:
        """获取时报工作表名称
        
        Returns:
            时报工作表名称
        """
        google_sheets_config = self.get_google_sheets_config()
        return google_sheets_config.get('hourly_sheet_name', 'Hourly-Report')
    
