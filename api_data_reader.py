import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pytz
import pyotp
import time
from param_generator import ParamGenerator

logger = logging.getLogger(__name__)

class ApiDataReader:
    def __init__(self, api_url: str, api_token: str, config_loader=None):
        """初始化 API 数据读取器
        
        Args:
            api_url: API 请求地址
            api_token: API 认证令牌（已废弃，保留用于兼容性）
            config_loader: 配置加载器
        """
        self.api_url = api_url
        self.api_token = api_token  # 保留用于兼容性
        self.config_loader = config_loader
        self.headers = {
            'Content-Type': 'application/json'
        }
        # 缓存渠道组映射关系
        self.channel_name_to_value_map = {}
        # 设置印度时区
        self.india_tz = pytz.timezone('Asia/Kolkata')
        # 登录相关
        self.login_token = None
        self.token_expiry = None
        
        # 启动时尝试从文件加载token
        if self.config_loader:
            self._load_token_on_startup()
    
    def _create_ssl_connector(self):
        """创建SSL连接器
        
        Returns:
            aiohttp.TCPConnector 或 None
        """
        if self.config_loader and hasattr(self.config_loader, 'get_ssl_verify'):
            ssl_verify = self.config_loader.get_ssl_verify()
            if not ssl_verify:
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                logger.warning("SSL证书验证已禁用，这可能存在安全风险")
                return aiohttp.TCPConnector(ssl=ssl_context)
        return None
    
    def _load_token_on_startup(self):
        """启动时从文件加载token"""
        try:
            token_data = self.config_loader.load_token_from_file()
            if token_data:
                self.login_token = token_data.get('token')
                self.token_expiry = token_data.get('expiry_time')
                logger.info("启动时从文件加载到有效token")
            else:
                logger.info("启动时未找到有效token，需要重新登录")
        except Exception as e:
            logger.error(f"启动时加载token失败: {str(e)}")
    
    def _reset_token_state(self):
        """重置token状态，清除可能有问题的状态"""
        logger.info("重置token状态")
        self.login_token = None
        self.token_expiry = None
    
        """检查实例健康状态
        
        Returns:
            如果实例状态正常返回True
        """
        try:
            # 检查必要的配置
            if not self.config_loader:
                logger.warning("实例健康检查失败：配置加载器未初始化")
                return False
            
            # 检查API配置
            data_config = self.config_loader.get_api_data_config()
            if not data_config:
                logger.warning("实例健康检查失败：数据API配置未找到")
                return False
            
            # 检查登录配置
            login_config = self.config_loader.get_api_login_config()
            if not login_config:
                logger.warning("实例健康检查失败：登录API配置未找到")
                return False
            
            logger.debug("实例健康检查通过")
            return True
            
        except Exception as e:
            logger.error(f"实例健康检查时出错: {str(e)}")
            return False
    
    def generate_totp_code(self, secret: str) -> str:
        """生成TOTP验证码
        
        Args:
            secret: TOTP密钥
            
        Returns:
            6位数字验证码
        """
        totp = pyotp.TOTP(secret)
        return totp.now()
    
    def generate_totp_codes_with_offsets(self, secret: str) -> list:
        """生成多个时间窗口的TOTP验证码
        
        Args:
            secret: TOTP密钥
            
        Returns:
            包含不同时间偏移验证码的列表
        """
        totp = pyotp.TOTP(secret)
        current_time = time.time()
        codes = []
        
        # 生成前后几个时间窗口的验证码 (每个窗口30秒)
        for offset in [-5, -4, -3, -2, -1, 0, 1, 2]:
            timestamp = current_time + (offset * 30)
            code = totp.at(timestamp)
            codes.append({
                'offset': offset,
                'code': code,
                'timestamp': timestamp
            })
        
        return codes
    
    async def try_login_with_code(self, login_config: dict, totp_code: str) -> Optional[str]:
        """使用指定验证码尝试登录
        
        Args:
            login_config: 登录配置
            totp_code: TOTP验证码
            
        Returns:
            登录token，如果失败返回None
        """
        try:
            # 准备登录请求数据（使用与auth_manager.py相同的格式）
            login_data = {
                'userName': login_config.get('username', ''),
                'pwd': login_config.get('password', ''),
                'vCode': totp_code,
                'language': 'zh'
            }
            
            # 添加通用参数（与auth_manager.py保持一致）
            auto_generate_config = [
                {"name": "timestamp", "type": "timestamp"},
                {"name": "random", "type": "random", "length": 12},
                {"name": "signature", "type": "signature"}
            ]
            
            # 使用参数生成器添加通用参数
            login_data = ParamGenerator.add_common_params(login_data, auto_generate_config)
            
            # 添加必要的headers
            headers = {
                'Content-Type': 'application/json',
                'Domainurl': login_config.get('url', '').replace('/api/Login/Login', '')
            }
            
            connector = self._create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    login_config.get('url', ''),
                    json=login_data,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug(f"登录响应: {result}")
                        
                        # 检查响应格式（兼容不同的API响应格式）
                        if result.get('success') and result.get('code') == 200:
                            # 格式1: {success: true, code: 200, data: {token: ...}}
                            token = result.get('data', {}).get('token')
                        elif result.get('code') == 0 and result.get('msg') == 'Succeed':
                            # 格式2: {code: 0, msg: 'Succeed', data: {token: ...}}
                            token = result.get('data', {}).get('token')
                        elif 'response' in result and 'data' in result['response'] and 'token' in result['response']['data']:
                            # 格式3: {response: {data: {token: ...}}}
                            token = result['response']['data']['token']
                        else:
                            # 检查错误信息
                            error_msg = result.get('message') or result.get('msg') or result.get('response', {}).get('msg', '未知错误')
                            logger.error(f"登录失败: {error_msg}")
                            return None
                        
                        if token and token.strip():
                            logger.info(f"使用验证码 {totp_code} 登录成功")
                            return token
                        else:
                            logger.error("登录响应中未找到有效token")
                            return None
                    else:
                        logger.error(f"登录请求失败，状态码: {response.status}")
                        response_text = await response.text()
                        logger.error(f"响应内容: {response_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"尝试登录时出错: {str(e)}", exc_info=True)
            return None

    async def login_and_get_token(self) -> Optional[str]:
        """登录并获取token（支持多时间窗口重试）
        
        Returns:
            登录token，如果失败返回None
        """
        try:
            if not self.config_loader:
                logger.error("配置加载器未初始化")
                return None
                
            # 获取登录配置
            login_config = self.config_loader.get_api_login_config()
            if not login_config:
                logger.error("未找到登录配置")
                return None
            
            logger.info(f"正在登录，用户名: {login_config.get('username', '')}")
            
            # 生成多个时间窗口的验证码
            totp_secret = login_config.get('totp_secret', '')
            if not totp_secret:
                logger.error("TOTP密钥为空")
                return None
            
            codes_info = self.generate_totp_codes_with_offsets(totp_secret)
            
            # 首先尝试当前时间的验证码
            current_code = self.generate_totp_code(totp_secret)
            logger.info(f"尝试当前验证码: {current_code}")
            
            token = await self.try_login_with_code(login_config, current_code)
            if token:
                # 登录成功，保存token
                self.login_token = token
                self.token_expiry = time.time() + 24 * 3600
                
                # 同步更新AuthManager的token缓存
                from auth_manager import AuthManager
                AuthManager._token_cache["main_login_token"] = token
                logger.debug("已同步更新AuthManager token缓存")
                
                if self.config_loader.save_token_to_file(token, self.token_expiry):
                    logger.info("登录成功，已获取新token并保存到文件")
                else:
                    logger.warning("登录成功，但保存token到文件失败")
                
                return token
            
            # 如果当前时间验证码失败，尝试其他时间窗口的验证码
            logger.info("当前验证码登录失败，尝试其他时间窗口的验证码...")
            for code_info in codes_info:
                if code_info['code'] == current_code:
                    continue  # 跳过已经尝试过的当前验证码
                
                logger.info(f"尝试偏移 {code_info['offset']} 的验证码: {code_info['code']}")
                token = await self.try_login_with_code(login_config, code_info['code'])
                if token:
                    # 登录成功，保存token
                    self.login_token = token
                    self.token_expiry = time.time() + 24 * 3600
                    
                    # 同步更新AuthManager的token缓存
                    from auth_manager import AuthManager
                    AuthManager._token_cache["main_login_token"] = token
                    logger.debug("已同步更新AuthManager token缓存")
                    
                    if self.config_loader.save_token_to_file(token, self.token_expiry):
                        logger.info(f"使用偏移 {code_info['offset']} 的验证码登录成功，已保存token")
                    else:
                        logger.warning("登录成功，但保存token到文件失败")
                    
                    return token
            
            logger.error("所有时间窗口的验证码都尝试失败")
            return None
                        
        except Exception as e:
            logger.error(f"登录过程中出错: {str(e)}", exc_info=True)
            return None
    
    def is_token_expired(self) -> bool:
        """检查token是否过期
        
        Returns:
            如果token过期或不存在返回True
        """
        if not self.login_token:
            logger.debug("Token不存在")
            return True
        if not self.token_expiry:
            logger.debug("Token过期时间未设置")
            return True
        
        current_time = time.time()
        is_expired = current_time > self.token_expiry
        if is_expired:
            logger.debug(f"Token已过期，当前时间: {current_time}, 过期时间: {self.token_expiry}")
        else:
            logger.debug(f"Token仍然有效，当前时间: {current_time}, 过期时间: {self.token_expiry}")
        return is_expired
    
    async def ensure_valid_token(self) -> bool:
        """确保有有效的token
        
        Returns:
            如果成功获取有效token返回True
        """
        if self.is_token_expired():
            logger.info("Token已过期，重新登录")
            # 清除可能有问题的旧token状态
            self._reset_token_state()
            token = await self.login_and_get_token()
            if token:
                logger.info("重新登录成功，获取到新token")
                return True
            else:
                logger.error("重新登录失败，无法获取有效token")
                # 登录失败时重置状态，避免状态污染
                self._reset_token_state()
                return False
        else:
            logger.debug("Token仍然有效，无需重新登录")
            return True
    
    def get_india_date(self, date_obj: datetime = None) -> str:
        """获取印度时区的日期字符串
        
        Args:
            date_obj: 日期对象，如果为None则使用当前时间
            
        Returns:
            印度时区的日期字符串，格式为 YYYY-MM-DD
        """
        if date_obj is None:
            india_now = datetime.now(self.india_tz)
        else:
            # 将输入的日期对象转换为印度时区
            if date_obj.tzinfo is None:
                # 如果日期对象没有时区信息，假设为UTC
                utc_dt = pytz.utc.localize(date_obj)
            else:
                utc_dt = date_obj.astimezone(pytz.utc)
            india_now = utc_dt.astimezone(self.india_tz)
        
        return india_now.strftime('%Y-%m-%d')
    
    def get_india_datetime(self) -> datetime:
        """获取印度时区的当前时间
        
        Returns:
            印度时区的当前时间
        """
        return datetime.now(self.india_tz)
    
    def get_india_yesterday_date(self) -> str:
        """获取印度时区的昨天日期
        
        Returns:
            印度时区的昨天日期字符串，格式为 YYYY-MM-DD
        """
        india_yesterday = datetime.now(self.india_tz) - timedelta(days=1)
        return india_yesterday.strftime('%Y-%m-%d')
    
    def get_india_hour(self, hours_ago: int = 0) -> str:
        """获取印度时区的特定小时时间
        
        Args:
            hours_ago: 几个小时前，默认为0（当前小时）
            
        Returns:
            印度时区的特定小时时间字符串，格式为 YYYY-MM-DD HH:00:00
        """
        india_time = datetime.now(self.india_tz) - timedelta(hours=hours_ago)
        # 将分钟和秒设置为0，只保留小时
        india_time = india_time.replace(minute=0, second=0, microsecond=0)
        return india_time.strftime('%Y-%m-%d %H:%M:%S')
    
    async def get_package_list(self) -> Optional[dict]:
        """获取包列表数据"""
        try:
            logger.info("正在获取包列表数据...")
            
            # 确保有有效的token
            if not await self.ensure_valid_token():
                logger.error("无法获取有效token")
                return None
            
            # 准备请求参数
            request_data = {
                "sortField": "id",
                "orderBy": "Desc",
                "pageNo": 1,
                "pageSize": 1000
            }
            
            # 从auth_manager导入验签功能
            from auth_manager import AuthManager
            
            # 使用认证管理器发送带认证和验签的请求
            response = AuthManager.send_authenticated_request(
                endpoint='/api/Package/GetPageList',
                data=request_data,
                method='POST',
                config_loader=self.config_loader
            )
            
            if 'error' not in response and response.get('status_code') == 200:
                logger.info("包列表获取成功")
                # 直接返回整个response，保持数据结构完整
                return response
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
            
            # 确保有有效的token
            if not await self.ensure_valid_token():
                logger.error("无法获取有效token")
                return None
            
            # 准备请求参数
            request_data = {
                "startTime": start_date,
                "endTime": end_date,
                "pageNo": 1,
                "pageSize": 1000,
                "orderBy": "Desc"
            }
            
            # 从auth_manager导入验签功能
            from auth_manager import AuthManager
            
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
    
    async def read_data(self, report_date: str = None, report_type: int = 0, 
                       start_time: str = None, end_time: str = None) -> List[Dict[str, Any]]:
        """使用新的包数据接口读取数据
        
        Args:
            report_date: 报表日期，格式为 YYYY-MM-DD，默认为印度时区的当天
            report_type: 报表类型，0 表示日报
            start_time: 开始时间，格式为 YYYY-MM-DD HH:MM:SS，用于时报查询
            end_time: 结束时间，格式为 YYYY-MM-DD HH:MM:SS，用于时报查询
            
        Returns:
            数据列表，格式与原来的read_data保持兼容
        """
        try:
            # 如果未指定日期，使用印度时区的当天日期
            if not report_date:
                report_date = self.get_india_date()
                logger.info(f"使用印度时区当前日期: {report_date}")
            
            logger.info(f"开始处理包数据，目标日期: {report_date}")
            
            # 1. 获取包列表，建立ID和包名的对应关系
            package_list_response = await self.get_package_list()
            if not package_list_response:
                logger.error("无法获取包列表数据")
                return []
            
            # 从响应中提取数据，支持不同的响应格式
            logger.debug(f"包列表响应结构: {list(package_list_response.keys()) if package_list_response else 'None'}")
            
            package_data = None
            if 'response' in package_list_response and 'data' in package_list_response['response']:
                # 格式1: {response: {data: {list: [...]}}}
                package_data = package_list_response['response']['data']
                logger.debug("使用格式1: response.response.data")
            elif 'data' in package_list_response:
                # 格式2: {data: {list: [...]}}
                package_data = package_list_response['data']
                logger.debug("使用格式2: response.data")
            else:
                logger.error(f"无法识别的响应格式，顶级字段: {list(package_list_response.keys()) if package_list_response else 'None'}")
            
            if not package_data:
                logger.error("包列表响应中未找到数据字段")
                logger.error(f"完整响应结构: {package_list_response}")
                return []
            
            # 建立ID到包名的映射
            id_to_package_name = {}
            package_list = package_data.get('list', [])
            for package in package_list:
                package_id = package.get('id')
                package_name = package.get('channelPackageName')
                if package_id is not None and package_name:
                    id_to_package_name[package_id] = package_name
            
            logger.info(f"建立了 {len(id_to_package_name)} 个包的ID映射关系")
            
            # 2. 获取包分析数据
            analysis_response = await self.get_package_analysis(report_date, report_date)
            if not analysis_response or 'data' not in analysis_response:
                logger.error("无法获取包分析数据")
                return []
            
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
            
            # 4. 转换数据格式以保持与原接口的兼容性
            converted_data = []
            for analysis_item in analysis_list:
                package_id = analysis_item.get('packageId')
                package_name = analysis_item.get('packageName', '')
                
                # 如果packageId存在于映射中，使用映射的名称，否则使用原始名称
                if package_id in id_to_package_name:
                    mapped_package_name = id_to_package_name[package_id]
                    logger.debug(f"包ID {package_id} 映射: {package_name} -> {mapped_package_name}")
                    package_name = mapped_package_name
                
                # 检查是否匹配配置中的渠道
                if package_name in target_channels:
                    # 转换为与原接口兼容的格式
                    converted_item = {
                        'create_time': report_date,
                        'channel': package_name,
                        'register': analysis_item.get('newMemberCount', 0),
                        'new_charge_user': analysis_item.get('newMemberRechargeCount', 0),
                        'new_charge': analysis_item.get('newMemberRechargeAmount', 0),  # 使用正确的字段
                        'charge_total': analysis_item.get('rechargeAmount', 0),
                        'withdraw_total': analysis_item.get('withdrawAmount', 0),
                        'charge_withdraw_diff': analysis_item.get('chargeWithdrawDiff', 0)
                    }
                    converted_data.append(converted_item)
                    logger.debug(f"匹配到渠道数据: {package_name}")
            
            logger.info(f"最终匹配到 {len(converted_data)} 条数据")
            return converted_data
            
        except Exception as e:
            logger.error(f"读取包数据时出错: {str(e)}")
            return []
    
    async def read_data_old(self, report_date: str = None, report_type: int = 0, 
                       start_time: str = None, end_time: str = None) -> List[Dict[str, Any]]:
        """从 API 读取数据
        
        Args:
            report_date: 报表日期，格式为 YYYY-MM-DD，默认为印度时区的当天
            report_type: 报表类型，0 表示日报
            start_time: 开始时间，格式为 YYYY-MM-DD HH:MM:SS，用于时报查询
            end_time: 结束时间，格式为 YYYY-MM-DD HH:MM:SS，用于时报查询
            
        Returns:
            数据列表
        """
        try:
            # 确保有有效的token
            if not await self.ensure_valid_token():
                logger.error("无法获取有效token")
                return []
            
            # 如果未指定日期，使用印度时区的当天日期
            if not report_date:
                report_date = self.get_india_date()
                logger.info(f"使用印度时区当前日期: {report_date}")
            
            # 获取数据API配置
            data_config = self.config_loader.get_api_data_config()
            if not data_config:
                logger.error("未找到数据API配置")
                return []
            
            # 准备请求数据
            request_data = {
                "page": 1,
                "pageSize": data_config.get('page_size', 1000),
                "create_time": [report_date, report_date],
                "channel": []
            }
            
            logger.info(f"正在获取数据，日期: {report_date}")
            
            # 发送请求
            headers = {
                'Authorization': f'Bearer {self.login_token}',
                'Content-Type': 'application/json'
            }
            
            connector = self._create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    data_config.get('url', ''),
                    json=request_data,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('success') and result.get('code') == 200:
                            items = result.get('data', {}).get('items', [])
                            logger.info(f"成功获取数据，共 {len(items)} 条记录")
                            return items
                        else:
                            logger.error(f"API返回错误: {result.get('message', '未知错误')}")
                            # 如果是token过期，尝试重新登录
                            if result.get('code') == 401:
                                logger.info("Token可能过期，尝试重新登录")
                                # 重置token状态避免状态污染
                                self._reset_token_state()
                                if await self.login_and_get_token():
                                    # 重新尝试请求，但避免无限递归
                                    logger.info("重新登录成功，重新尝试数据请求")
                                    # 直接重新发送请求，而不是递归调用
                                    headers = {
                                        'Authorization': f'Bearer {self.login_token}',
                                        'Content-Type': 'application/json'
                                    }
                                    async with session.post(
                                        data_config.get('url', ''),
                                        json=request_data,
                                        headers=headers
                                    ) as retry_response:
                                        if retry_response.status == 200:
                                            retry_result = await retry_response.json()
                                            if retry_result.get('success') and retry_result.get('code') == 200:
                                                items = retry_result.get('data', {}).get('items', [])
                                                logger.info(f"重新登录后成功获取数据，共 {len(items)} 条记录")
                                                return items
                                            else:
                                                logger.error(f"重新登录后API仍返回错误: {retry_result.get('message', '未知错误')}")
                                        else:
                                            logger.error(f"重新登录后数据请求仍失败，状态码: {retry_response.status}")
                                else:
                                    logger.error("重新登录失败，清除token状态")
                                    self._reset_token_state()
                    else:
                        logger.error(f"数据请求失败，状态码: {response.status}")
                        # 如果是401错误，也尝试重新登录
                        if response.status == 401:
                            logger.info("HTTP 401错误，尝试重新登录")
                            # 重置token状态避免状态污染
                            self._reset_token_state()
                            if await self.login_and_get_token():
                                logger.info("重新登录成功，重新尝试数据请求")
                                # 直接重新发送请求
                                headers = {
                                    'Authorization': f'Bearer {self.login_token}',
                                    'Content-Type': 'application/json'
                                }
                                async with session.post(
                                    data_config.get('url', ''),
                                    json=request_data,
                                    headers=headers
                                ) as retry_response:
                                    if retry_response.status == 200:
                                        retry_result = await retry_response.json()
                                        if retry_result.get('success') and retry_result.get('code') == 200:
                                            items = retry_result.get('data', {}).get('items', [])
                                            logger.info(f"重新登录后成功获取数据，共 {len(items)} 条记录")
                                            return items
                                        else:
                                            logger.error(f"重新登录后API仍返回错误: {retry_result.get('message', '未知错误')}")
                                    else:
                                        logger.error(f"重新登录后数据请求仍失败，状态码: {retry_response.status}")
                            else:
                                logger.error("重新登录失败，清除token状态")
                                self._reset_token_state()
                        
        except Exception as e:
            logger.error(f"读取数据时出错: {str(e)}", exc_info=True)
        
        return []
        
    async def get_channel_groups(self) -> List[Dict[str, Any]]:
        """获取渠道组信息
        
        Returns:
            渠道组列表
        """
        try:
            # 构建请求参数，只需要获取渠道组信息
            india_date = self.get_india_date()
            params = {
                "page": 1,
                "size": 1,
                "createTime": [
                    india_date,
                    india_date
                ],
                "reportType": 0,
                "channel": ""
            }
            
            logger.info("开始获取渠道组信息")
            
            connector = self._create_ssl_connector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(self.api_url, json=params, headers=self.headers) as response:
                    if response.status != 200:
                        logger.error(f"API 请求失败，状态码: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    # 检查响应格式
                    if data.get('code') != 0 or 'data' not in data:
                        logger.error(f"API 响应格式错误: {data}")
                        return []
                    
                    # 获取渠道组信息
                    channel_groups = data['data'].get('channelGroup', [])
                    logger.info(f"获取到渠道组信息: {len(channel_groups)} 个渠道")
                    
                    return channel_groups
        
        except Exception as e:
            logger.error(f"获取渠道组信息时出错: {str(e)}")
            return []
    
    async def build_channel_name_to_value_map(self) -> Dict[str, str]:
        """构建渠道名称到value的映射关系
        
        Returns:
            渠道名称到value的字典映射
        """
        try:
            channel_groups = await self.get_channel_groups()
            
            # 构建映射关系
            self.channel_name_to_value_map = {}
            for channel in channel_groups:
                channel_name = channel.get('name', '').strip()
                channel_value = channel.get('value', '').strip()
                
                # 跳过空的或者"请选择渠道ID"这样的默认项
                if channel_name and channel_value and channel_name != "请选择渠道ID":
                    self.channel_name_to_value_map[channel_name] = channel_value
            
            # logger.info(f"构建渠道映射关系完成: {self.channel_name_to_value_map}")
            return self.channel_name_to_value_map
        
        except Exception as e:
            logger.error(f"构建渠道映射关系时出错: {str(e)}")
            return {}
    
    async def get_channel_value_by_name(self, channel_name: str) -> str:
        """根据渠道名称获取对应的value
        
        Args:
            channel_name: 渠道名称，如 "FBA8-18"
            
        Returns:
            对应的渠道value，如果找不到返回空字符串
        """
        try:
            # 如果映射关系还没有建立，先建立映射关系
            if not self.channel_name_to_value_map:
                await self.build_channel_name_to_value_map()
            
            channel_value = self.channel_name_to_value_map.get(channel_name, '')
            if channel_value:
                logger.info(f"找到渠道 '{channel_name}' 对应的value: {channel_value}")
            else:
                logger.warning(f"未找到渠道 '{channel_name}' 对应的value")
            
            return channel_value
        
        except Exception as e:
            logger.error(f"获取渠道value时出错: {str(e)}")
            return ""
    
    async def read_data_by_config_channels(self, config_channel_names: List[str], report_date: str = None, report_type: int = 0) -> List[Dict[str, Any]]:
        """根据配置文件中的渠道名称列表查询数据
        
        Args:
            config_channel_names: 配置文件中的渠道名称列表，如 ["FBA8-18", "FBPX-35"]
            report_date: 报表日期，格式为 YYYY-MM-DD，默认为印度时区的当天
            report_type: 报表类型，0 表示日报
            
        Returns:
            数据列表
        """
        logger.info(f"根据配置渠道查询数据: {config_channel_names}")
        return await self.read_data(report_date=report_date, report_type=report_type, channel_names=config_channel_names)
    
    async def read_hourly_data(self, hours_ago: int = 0, channel_names: List[str] = None) -> List[Dict[str, Any]]:
        """查询指定小时前的时报数据
        
        Args:
            hours_ago: 几个小时前，默认为0（当前小时）
            channel_names: 指定的渠道名称列表，如 ["FBA8-18", "FBPX-35"]，为空则查询所有渠道
            
        Returns:
            数据列表
        """
        # 获取印度时区的特定小时时间
        end_time = self.get_india_hour(hours_ago)
        start_time = self.get_india_hour(hours_ago + 1)  # 上一个小时
        
        logger.info(f"查询时报数据: {start_time} 到 {end_time}")
        return await self.read_data(
            report_type=1,  # 时报类型
            channel_names=channel_names,
            start_time=start_time,
            end_time=end_time
        )
    
    async def read_yesterday_data(self, channel_names: List[str] = None) -> List[Dict[str, Any]]:
        """查询印度时区昨天的日报数据
        
        Args:
            channel_names: 指定的渠道名称列表，如 ["FBA8-18", "FBPX-35"]，为空则查询所有渠道
            
        Returns:
            数据列表
        """
        yesterday_date = self.get_india_yesterday_date()
        logger.info(f"查询印度时区昨天的日报数据: {yesterday_date}")
        return await self.read_data(
            report_date=yesterday_date,
            report_type=0,  # 日报类型
            channel_names=channel_names
        )

class ApiDataSender:
    def __init__(self, bot, config_loader=None):
        """初始化数据发送器
        
        Args:
            bot: Telegram Bot 实例
            config_loader: 配置加载器实例
        """
        self.bot = bot
        self.config_loader = config_loader
        
        # 发送配置
        self.batch_size = 5  # 每批发送的群组数量
        self.delay_seconds = 2  # 批次间的延迟时间（秒）
        
    
    def update_config(self, config_loader):
        """更新配置加载器
        
        Args:
            config_loader: 新的配置加载器实例
        """
        self.config_loader = config_loader
        logger.info("ApiDataSender 配置已更新")
    
    async def format_message(self, data: Dict[str, Any]) -> str:
        """格式化消息内容
        
        Args:
            data: API 返回的数据项
            
        Returns:
            格式化后的消息文本
        """
        try:
            # 根据新的 API 返回的数据格式化消息
            create_time = data.get('create_time', '')
            channel = data.get('channel', '')
            
            # 新增用户数
            register = data.get('register', '0')
            
            # 付费相关
            new_charge_user = data.get('new_charge_user', 0)
            new_charge = data.get('new_charge', '0')
            
            # 充值提现相关
            charge_total = data.get('charge_total', '0')
            withdraw_total = data.get('withdraw_total', '0')
            charge_withdraw_diff = data.get('charge_withdraw_diff', '0')
            
            # 格式化消息
            message = f"日期：{create_time}\n"
            message += f"渠道：{channel}\n"
            message += f"新增：{register}\n"
            message += f"付费人数：{new_charge_user}\n"
            message += f"付费金额：{new_charge}\n"
            message += f"总充：{charge_total}\n"
            message += f"总提：{withdraw_total}\n"
            message += f"充提差：{charge_withdraw_diff}"
            
            return message
            
        except Exception as e:
            logger.error(f"格式化消息时出错: {str(e)}")
            return f"❌ 数据格式化失败: {str(e)}"
    
    async def send_data(self, data: Dict[str, Any]) -> bool:
        """发送数据到目标群组
        
        Args:
            data: API 返回的数据项
            
        Returns:
            是否发送成功
        """
        try:
            # 获取渠道来源
            channel_source = data.get('channel', '')
            logger.info(f"从数据中获取到的渠道来源: {channel_source}")
            
            if not channel_source:
                logger.warning("数据中没有渠道来源信息")
                return False
            
            # 从配置中获取群组配置
            if not self.config_loader:
                logger.error("配置加载器未初始化")
                return False
            
            # 获取所有群组配置
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置")
                return False
            
            # 查找包含该渠道的群组
            target_groups = []
            for group_name, group_config in groups_config.items():
                channel_ids = group_config.get('channel_ids', [])
                for channel_config in channel_ids:
                    channel_id = channel_config.get('id', '')
                    if channel_id == channel_source:
                        tg_group = group_config.get('tg_group', '')
                        if tg_group:
                            target_groups.append({
                                'group_name': group_config.get('name', group_name),
                                'tg_group': tg_group
                            })
                        break
            
            if not target_groups:
                logger.warning(f"没有为渠道来源 '{channel_source}' 配置目标群组")
                return False
            
            # 格式化单条数据消息
            single_message = await self.format_message(data)
            logger.info(f"格式化后的单条消息内容: {single_message}")
            
            # 使用配置的发送间隔参数
            total_sent = 0
            
            logger.info(f"使用发送间隔配置: 每 {self.batch_size} 个群组间隔 {self.delay_seconds} 秒")
            
            for i, group_info in enumerate(target_groups):
                chat_id = int(group_info['tg_group'])
                group_name = group_info['group_name']
                
                # 发送单条数据消息
                await self.bot.send_message(chat_id=chat_id, text=single_message)
                total_sent += 1
                logger.info(f"已发送单条数据到群组 {group_name} ({chat_id})，当前批次: {i % self.batch_size + 1}/{min(self.batch_size, len(target_groups) - (i // self.batch_size) * self.batch_size)}")
                
                # 每发送batch_size个群组后暂停delay_seconds秒，但最后一批不需要暂停
                if (i + 1) % self.batch_size == 0 and i + 1 < len(target_groups):
                    logger.info(f"已发送 {self.batch_size} 个群组，暂停 {self.delay_seconds} 秒")
                    await asyncio.sleep(self.delay_seconds)
            
            logger.info(f"发送完成，共发送到 {total_sent} 个群组")
            return True
        except Exception as e:
            logger.error(f"发送数据时出错: {str(e)}")
            return False
    
    async def send_grouped_data(self, data_list: List[Dict[str, Any]]) -> bool:
        """按群组汇总发送数据
        
        Args:
            data_list: API 返回的数据列表
            
        Returns:
            是否发送成功
        """
        try:
            if not data_list:
                logger.warning("数据列表为空")
                return False
            
            # 从配置中获取群组配置
            if not self.config_loader:
                logger.error("配置加载器未初始化")
                return False
            
            groups_config = self.config_loader.get_groups_config()
            if not groups_config:
                logger.warning("未找到群组配置")
                return False
            
            # 按群组汇总数据
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
                            tg_group = group_config.get('tg_group', '')
                            if tg_group:
                                if tg_group not in group_data_map:
                                    group_data_map[tg_group] = {
                                        'group_name': group_config.get('name', group_name),
                                        'data_list': []
                                    }
                                group_data_map[tg_group]['data_list'].append(data)
                            break
            
            if not group_data_map:
                logger.warning("没有找到匹配的群组配置")
                return False
            
            # 发送汇总数据到每个群组
            total_sent = 0
            total_groups = len(group_data_map)
            
            logger.info(f"准备向 {total_groups} 个群组发送汇总数据")
            
            for i, (tg_group, group_info) in enumerate(group_data_map.items()):
                chat_id = int(tg_group)
                group_name = group_info['group_name']
                data_list = group_info['data_list']
                
                logger.info(f"处理群组 {group_name} ({chat_id})，包含 {len(data_list)} 条数据")
                
                # 生成汇总消息（文本表格格式）
                messages = await self._generate_grouped_messages(data_list, group_name)
                
                # 发送消息
                for j, message in enumerate(messages):
                    await self.bot.send_message(chat_id=chat_id, text=message)
                    logger.info(f"已发送第 {j + 1}/{len(messages)} 条消息到群组 {group_name}")
                
                total_sent += 1
                logger.info(f"群组 {group_name} 发送完成，共 {len(messages)} 条消息")
                
                # 每发送batch_size个群组后暂停delay_seconds秒，但最后一批不需要暂停
                if (i + 1) % self.batch_size == 0 and i + 1 < total_groups:
                    logger.info(f"已发送 {self.batch_size} 个群组，暂停 {self.delay_seconds} 秒")
                    await asyncio.sleep(self.delay_seconds)
            
            logger.info(f"汇总发送完成，共发送到 {total_sent} 个群组")
            return True
            
        except Exception as e:
            logger.error(f"发送汇总数据时出错: {str(e)}")
            return False
    
    async def _generate_grouped_messages(self, data_list: List[Dict[str, Any]], group_name: str) -> List[str]:
        """生成群组汇总消息，格式为表格形式，支持一键复制
        
        Args:
            data_list: 数据列表
            group_name: 群组名称
            
        Returns:
            消息列表
        """
        try:
            if not data_list:
                return []
            
            # 提取日期（使用第一条数据的日期）
            report_date = data_list[0].get('create_time', '')
            
            # 生成消息头部（日期部分）
            header = f"📅 日期：{report_date}\n\n"
            
            # 生成表格头部（使用空格分隔，便于复制）
            table_header = "渠道号 - 新增 - 付费人数 - 付费金额 - 总充 - 总提 - 充提差\n"
            
            # 生成表格数据行
            table_rows = []
            for data in data_list:
                channel = data.get('channel', '')
                register = data.get('register', '0')
                new_charge_user = data.get('new_charge_user', 0)
                new_charge = data.get('new_charge', '0')
                charge_total = data.get('charge_total', '0')
                withdraw_total = data.get('withdraw_total', '0')
                charge_withdraw_diff = data.get('charge_withdraw_diff', '0')
                
                # 格式化数据行（使用空格分隔）
                row = f"{channel} - {register} - {new_charge_user} - {new_charge} - {charge_total} - {withdraw_total} - {charge_withdraw_diff}"
                table_rows.append(row)
            
            # 组合完整消息
            full_message = header + table_header + "\n".join(table_rows)
            
            # 检查消息长度，如果超过4000字符则分割
            if len(full_message) <= 4000:
                return [full_message]
            else:
                # 如果超过4000字符，需要分割
                messages = []
                current_message = header + table_header
                
                for row in table_rows:
                    # 检查添加这一行是否会超过4000字符
                    if len(current_message + "\n" + row) > 4000:
                        # 当前消息已满，保存并开始新消息
                        messages.append(current_message)
                        current_message = header + table_header + row
                    else:
                        # 添加到当前消息
                        current_message += "\n" + row
                
                # 添加最后一条消息
                if current_message != header + table_header:
                    messages.append(current_message)
                
                logger.info(f"为群组 {group_name} 生成了 {len(messages)} 条消息")
                return messages
            
        except Exception as e:
            logger.error(f"生成群组汇总消息时出错: {str(e)}")
            return []