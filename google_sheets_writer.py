import logging
import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GoogleSheetsWriter:
    def __init__(self, config_loader=None):
        """初始化Google表格写入器
        
        Args:
            config_loader: 配置加载器实例
        """
        self.config_loader = config_loader
        self.credentials_file = self.config_loader.get_google_sheets_credentials_file() if config_loader else "credentials.json"
        self.service = None
        self._initialize_service()
        
        # 速率限制控制
        self.last_request_time = 0
        self.min_request_interval = 1.2  # 最小请求间隔（秒），稍微保守一些
        self.max_retries = 5  # 增加重试次数
        self.base_delay = 3.0  # 增加基础延迟时间
        
        # 操作队列，确保API请求顺序执行
        self._operation_queue = asyncio.Queue()
        self._queue_worker_running = False
        
        # 缓存机制
        self._sheet_id_cache = {}  # 缓存工作表ID
        self._header_cache = {}    # 缓存表头状态
    
    def _initialize_service(self):
        """初始化Google Sheets服务"""
        try:
            if not os.path.exists(self.credentials_file):
                logger.error(f"Google服务账户凭据文件不存在: {self.credentials_file}")
                return
            
            # 加载服务账户凭据
            credentials = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # 构建Google Sheets服务
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info("Google Sheets服务初始化成功")
            
        except Exception as e:
            logger.error(f"初始化Google Sheets服务失败: {str(e)}")
    
    async def _rate_limit_delay(self):
        """速率限制延迟"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            delay = self.min_request_interval - time_since_last_request
            logger.debug(f"速率限制延迟: {delay:.2f}秒")
            await asyncio.sleep(delay)
        
        self.last_request_time = time.time()
    
    async def _execute_with_retry(self, operation, operation_name, max_retries=None):
        """执行操作并处理重试逻辑
        
        Args:
            operation: 要执行的操作函数
            operation_name: 操作名称（用于日志）
            max_retries: 最大重试次数，默认使用实例变量
            
        Returns:
            操作结果
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                await self._rate_limit_delay()
                result = operation()
                logger.debug(f"{operation_name} 执行成功")
                return result
                
            except HttpError as e:
                if e.resp.status == 429:  # 速率限制错误
                    if attempt < max_retries:
                        delay = self.base_delay * (2 ** attempt)  # 指数退避
                        logger.warning(f"{operation_name} 遇到速率限制 (429)，第 {attempt + 1} 次重试，延迟 {delay} 秒")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"{operation_name} 达到最大重试次数，放弃操作: {str(e)}")
                        raise
                else:
                    logger.error(f"{operation_name} HTTP错误: {str(e)}")
                    raise
                    
            except Exception as e:
                if attempt < max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"{operation_name} 执行失败，第 {attempt + 1} 次重试，延迟 {delay} 秒: {str(e)}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"{operation_name} 达到最大重试次数，放弃操作: {str(e)}")
                    raise
    
    async def _start_queue_worker(self):
        """启动队列工作器"""
        if self._queue_worker_running:
            return
        
        self._queue_worker_running = True
        logger.info("启动Google Sheets操作队列工作器")
        
        while self._queue_worker_running:
            try:
                # 等待队列中的操作
                operation_data = await asyncio.wait_for(
                    self._operation_queue.get(), 
                    timeout=30.0  # 30秒超时
                )
                
                operation_func = operation_data['operation']
                operation_name = operation_data['name']
                future = operation_data['future']
                
                try:
                    result = await self._execute_with_retry(operation_func, operation_name)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                    
                self._operation_queue.task_done()
                
            except asyncio.TimeoutError:
                # 超时，继续循环
                continue
            except Exception as e:
                logger.error(f"队列工作器错误: {str(e)}")
                await asyncio.sleep(1)
    
    async def _queue_operation(self, operation, operation_name):
        """将操作加入队列
        
        Args:
            operation: 要执行的操作函数
            operation_name: 操作名称
            
        Returns:
            操作结果
        """
        future = asyncio.Future()
        operation_data = {
            'operation': operation,
            'name': operation_name,
            'future': future
        }
        
        # 启动队列工作器（如果还没有启动）
        if not self._queue_worker_running:
            asyncio.create_task(self._start_queue_worker())
        
        await self._operation_queue.put(operation_data)
        return await future
    
    def get_india_datetime(self) -> datetime:
        """获取印度时区的当前时间
        
        Returns:
            印度时区的当前时间
        """
        india_tz = pytz.timezone('Asia/Kolkata')
        return datetime.now(india_tz)
    
    def format_datetime_for_sheet(self, dt: datetime) -> str:
        """格式化日期时间用于表格显示
        
        Args:
            dt: 日期时间对象
            
        Returns:
            格式化后的日期时间字符串
        """
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    async def write_daily_data(self, spreadsheet_id: str, sheet_name: str, data_list: List[Dict[str, Any]], group_name: str) -> bool:
        """写入日报数据到Google表格（相同数据日期则覆盖，不同数据日期则新增写入）
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            data_list: 数据列表
            group_name: 群组名称
            
        Returns:
            是否写入成功
        """
        try:
            if not self.service:
                logger.error("Google Sheets服务未初始化")
                return False
            
            if not data_list:
                logger.warning("日报数据为空")
                return False
            
            # 获取印度时区的当前时间
            india_now = self.get_india_datetime()
            timestamp = self.format_datetime_for_sheet(india_now)
            
            # 获取数据日期（使用第一条数据的日期）
            data_date = data_list[0].get('create_time', '')
            
            # 检查是否存在相同日期的数据，如果存在则删除
            await self._delete_rows_by_date(spreadsheet_id, sheet_name, data_date, group_name)
            
            # 准备写入的数据
            rows_to_insert = []
            
            for data in data_list:
                # 提取数据字段
                create_time = data.get('create_time', '')
                channel = data.get('channel', '')
                register = data.get('register', '0')
                new_charge_user = data.get('new_charge_user', 0)
                new_charge = data.get('new_charge', '0')
                charge_total = data.get('charge_total', '0')
                withdraw_total = data.get('withdraw_total', '0')
                charge_withdraw_diff = data.get('charge_withdraw_diff', '0')
                
                # 构建行数据：时间戳 | 群组 | 日期 | 渠道 | 新增注册用户 | 新增付费人数 | 新增付费金额 | 总充值金额 | 总提现金额 | 充提差
                row = [
                    timestamp,  # 写入时间（印度时间）
                    group_name,  # 群组名称
                    create_time,  # 数据日期
                    channel,  # 渠道
                    register,  # 新增注册用户
                    new_charge_user,  # 新增付费人数
                    new_charge,  # 新增付费金额
                    charge_total,  # 总充值金额
                    withdraw_total,  # 总提现金额
                    charge_withdraw_diff  # 充提差
                ]
                rows_to_insert.append(row)
            
            # 在第一行（表头）下面插入数据
            # 使用batchUpdate来插入行
            sheet_id = await self._get_sheet_id(spreadsheet_id, sheet_name)
            if sheet_id is None:
                logger.error(f"无法获取工作表ID: {sheet_name}")
                return False
            
            # 先插入空行
            insert_request = {
                'insertDimension': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': 1,  # 在第二行插入（第一行是表头）
                        'endIndex': 1 + len(rows_to_insert)  # 插入多行
                    }
                }
            }
            
            # 使用队列执行插入操作
            await self._queue_operation(
                lambda: self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': [insert_request]}
                ).execute(),
                f"插入日报数据行到工作表 {sheet_name}"
            )
            
            # 然后写入数据到插入的行
            range_name = f"{sheet_name}!A2:J{1 + len(rows_to_insert)}"
            body = {
                'values': rows_to_insert
            }
            
            # 使用队列执行数据写入
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute(),
                f"写入日报数据到工作表 {sheet_name}"
            )
            
            logger.info(f"日报数据写入成功，群组: {group_name}，工作表: {sheet_name}，插入 {len(rows_to_insert)} 行数据")
            return True
            
        except HttpError as e:
            logger.error(f"Google Sheets API错误: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"写入日报数据时出错: {str(e)}")
            return False
    
    async def write_hourly_data(self, spreadsheet_id: str, sheet_name: str, data_list: List[Dict[str, Any]], group_name: str) -> bool:
        """写入时报数据到Google表格（只删除数据日期不是今天的数据，其他情况新增写入）
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            data_list: 数据列表
            group_name: 群组名称
            
        Returns:
            是否写入成功
        """
        try:
            if not self.service:
                logger.error("Google Sheets服务未初始化")
                return False
            
            if not data_list:
                logger.warning("时报数据为空")
                return False
            
            # 获取印度时区的当前时间
            india_now = self.get_india_datetime()
            timestamp = self.format_datetime_for_sheet(india_now)
            
            # 获取数据日期（使用第一条数据的日期）
            data_date = data_list[0].get('create_time', '')
            
            # 删除数据日期不是今天的数据
            await self._delete_old_hourly_data(spreadsheet_id, sheet_name, group_name)
            
            # 准备写入的数据
            rows_to_insert = []
            
            for data in data_list:
                # 提取数据字段
                create_time = data.get('create_time', '')
                channel = data.get('channel', '')
                register = data.get('register', '0')
                new_charge_user = data.get('new_charge_user', 0)
                new_charge = data.get('new_charge', '0')
                charge_total = data.get('charge_total', '0')
                withdraw_total = data.get('withdraw_total', '0')
                charge_withdraw_diff = data.get('charge_withdraw_diff', '0')
                
                # 构建行数据：时间戳 | 群组 | 日期 | 渠道 | 新增注册用户 | 新增付费人数 | 新增付费金额 | 总充值金额 | 总提现金额 | 充提差
                row = [
                    timestamp,  # 写入时间（印度时间）
                    group_name,  # 群组名称
                    create_time,  # 数据日期
                    channel,  # 渠道
                    register,  # 新增注册用户
                    new_charge_user,  # 新增付费人数
                    new_charge,  # 新增付费金额
                    charge_total,  # 总充值金额
                    withdraw_total,  # 总提现金额
                    charge_withdraw_diff  # 充提差
                ]
                rows_to_insert.append(row)
            
            # 在第一行（表头）下面插入数据
            # 使用batchUpdate来插入行
            sheet_id = await self._get_sheet_id(spreadsheet_id, sheet_name)
            if sheet_id is None:
                logger.error(f"无法获取工作表ID: {sheet_name}")
                return False
            
            # 先插入空行
            insert_request = {
                'insertDimension': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': 1,  # 在第二行插入（第一行是表头）
                        'endIndex': 1 + len(rows_to_insert)  # 插入多行
                    }
                }
            }
            
            # 使用队列执行插入操作
            await self._queue_operation(
                lambda: self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': [insert_request]}
                ).execute(),
                f"插入时报数据行到工作表 {sheet_name}"
            )
            
            # 然后写入数据到插入的行
            range_name = f"{sheet_name}!A2:J{1 + len(rows_to_insert)}"
            body = {
                'values': rows_to_insert
            }
            
            # 使用队列执行数据写入
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute(),
                f"写入时报数据到工作表 {sheet_name}"
            )
            
            logger.info(f"时报数据写入成功，群组: {group_name}，工作表: {sheet_name}，插入 {len(rows_to_insert)} 行数据")
            return True
            
        except HttpError as e:
            logger.error(f"Google Sheets API错误: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"写入时报数据时出错: {str(e)}")
            return False
    
    async def _delete_rows_by_date(self, spreadsheet_id: str, sheet_name: str, date: str, group_name: str) -> bool:
        """删除指定日期和群组的数据行
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            date: 日期
            group_name: 群组名称
            
        Returns:
            是否删除成功
        """
        try:
            # 读取工作表数据
            range_name = f"{sheet_name}!A:J"  # 读取A到J列
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute(),
                f"读取工作表 {sheet_name} 数据用于删除指定日期数据"
            )
            
            values = result.get('values', [])
            if not values:
                logger.info(f"工作表 {sheet_name} 为空，无需删除")
                return True
            
            # 找到要删除的行索引
            rows_to_delete = []
            for i, row in enumerate(values):
                if len(row) >= 3:  # 确保有足够的列
                    row_date = row[2] if len(row) > 2 else ''  # 第三列是日期
                    row_group = row[1] if len(row) > 1 else ''  # 第二列是群组
                    if row_date == date and row_group == group_name:
                        rows_to_delete.append(i + 1)  # Google Sheets行号从1开始
            
            if not rows_to_delete:
                logger.info(f"未找到日期为 {date} 且群组为 {group_name} 的数据行")
                return True
            
            # 批量删除行（按连续范围分组）
            if rows_to_delete:
                # 对行号排序
                rows_to_delete.sort()
                
                # 分组连续的行号
                delete_requests = []
                start_row = rows_to_delete[0]
                end_row = start_row
                
                for i in range(1, len(rows_to_delete)):
                    if rows_to_delete[i] == end_row + 1:
                        # 连续行，扩展范围
                        end_row = rows_to_delete[i]
                    else:
                        # 不连续，添加当前范围并开始新范围
                        delete_requests.append({
                            'deleteDimension': {
                                'range': {
                                    'sheetId': await self._get_sheet_id(spreadsheet_id, sheet_name),
                                    'dimension': 'ROWS',
                                    'startIndex': start_row - 1,  # 转换为0基索引
                                    'endIndex': end_row
                                }
                            }
                        })
                        start_row = rows_to_delete[i]
                        end_row = start_row
                
                # 添加最后一个范围
                delete_requests.append({
                    'deleteDimension': {
                        'range': {
                            'sheetId': await self._get_sheet_id(spreadsheet_id, sheet_name),
                            'dimension': 'ROWS',
                            'startIndex': start_row - 1,  # 转换为0基索引
                            'endIndex': end_row
                        }
                    }
                })
                
                # 批量执行删除操作
                await self._queue_operation(
                    lambda: self.service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={'requests': delete_requests}
                    ).execute(),
                    f"删除工作表 {sheet_name} 中的指定日期数据"
                )
                
                logger.info(f"批量删除了 {len(rows_to_delete)} 行数据，日期: {date}，群组: {group_name}，分 {len(delete_requests)} 个批次")
            return True
            
        except Exception as e:
            logger.error(f"删除数据行时出错: {str(e)}")
            return False
    
    async def _delete_old_hourly_data(self, spreadsheet_id: str, sheet_name: str, group_name: str) -> bool:
        """删除数据日期不是今天的时报数据
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            group_name: 群组名称
            
        Returns:
            是否删除成功
        """
        try:
            # 读取工作表数据
            range_name = f"{sheet_name}!A:J"  # 读取A到J列
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute(),
                f"读取工作表 {sheet_name} 数据用于删除旧时报数据"
            )
            
            values = result.get('values', [])
            if not values:
                logger.info(f"工作表 {sheet_name} 为空，无需删除")
                return True
            
            # 获取当前日期（印度时间）
            india_now = self.get_india_datetime()
            current_date = india_now.date()
            
            # 找到要删除的行索引（数据日期不是今天的数据）
            rows_to_delete = []
            for i, row in enumerate(values):
                if len(row) >= 3:  # 确保有足够的列
                    row_date_str = row[2] if len(row) > 2 else ''  # 第三列是日期
                    row_group = row[1] if len(row) > 1 else ''  # 第二列是群组
                    
                    if row_group == group_name and row_date_str:
                        try:
                            # 解析数据日期
                            row_date = datetime.strptime(row_date_str, '%Y-%m-%d').date()
                            # 计算日期差
                            date_diff = (current_date - row_date).days
                            
                            # 如果数据日期不是今天，则删除
                            if date_diff > 0:
                                rows_to_delete.append(i + 1)  # Google Sheets行号从1开始
                                logger.info(f"标记删除行 {i + 1}，数据日期: {row_date_str}，日期差: {date_diff} 天")
                        except ValueError:
                            logger.warning(f"无法解析日期格式: {row_date_str}")
                            continue
            
            if not rows_to_delete:
                logger.info(f"未找到需要删除的旧数据（不是今天的数据）")
                return True
            
            # 批量删除行（按连续范围分组）
            if rows_to_delete:
                # 对行号排序
                rows_to_delete.sort()
                
                # 分组连续的行号
                delete_requests = []
                start_row = rows_to_delete[0]
                end_row = start_row
                
                for i in range(1, len(rows_to_delete)):
                    if rows_to_delete[i] == end_row + 1:
                        # 连续行，扩展范围
                        end_row = rows_to_delete[i]
                    else:
                        # 不连续，添加当前范围并开始新范围
                        delete_requests.append({
                            'deleteDimension': {
                                'range': {
                                    'sheetId': await self._get_sheet_id(spreadsheet_id, sheet_name),
                                    'dimension': 'ROWS',
                                    'startIndex': start_row - 1,  # 转换为0基索引
                                    'endIndex': end_row
                                }
                            }
                        })
                        start_row = rows_to_delete[i]
                        end_row = start_row
                
                # 添加最后一个范围
                delete_requests.append({
                    'deleteDimension': {
                        'range': {
                            'sheetId': await self._get_sheet_id(spreadsheet_id, sheet_name),
                            'dimension': 'ROWS',
                            'startIndex': start_row - 1,  # 转换为0基索引
                            'endIndex': end_row
                        }
                    }
                })
                
                # 批量执行删除操作
                await self._queue_operation(
                    lambda: self.service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={'requests': delete_requests}
                    ).execute(),
                    f"删除工作表 {sheet_name} 中的旧时报数据"
                )
                
                logger.info(f"批量删除了 {len(rows_to_delete)} 行旧数据（不是今天的数据），群组: {group_name}，分 {len(delete_requests)} 个批次")
            return True
            
        except Exception as e:
            logger.error(f"删除旧时报数据时出错: {str(e)}")
            return False
    
    async def _get_sheet_id(self, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
        """获取工作表的ID
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            
        Returns:
            工作表ID，如果未找到返回None
        """
        # 检查缓存
        cache_key = f"{spreadsheet_id}_{sheet_name}"
        if cache_key in self._sheet_id_cache:
            logger.debug(f"从缓存获取工作表ID: {sheet_name}")
            return self._sheet_id_cache[cache_key]
        
        try:
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute(),
                f"获取工作表 {sheet_name} 的ID"
            )
            
            sheets = result.get('sheets', [])
            for sheet in sheets:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    # 缓存结果
                    self._sheet_id_cache[cache_key] = sheet_id
                    return sheet_id
            
            logger.error(f"未找到工作表: {sheet_name}")
            return None
            
        except Exception as e:
            logger.error(f"获取工作表ID时出错: {str(e)}")
            return None
    
    async def create_sheet_if_not_exists(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """如果工作表不存在则创建
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            
        Returns:
            是否成功
        """
        try:
            # 检查工作表是否存在
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute(),
                f"检查工作表 {sheet_name} 是否存在"
            )
            
            sheets = result.get('sheets', [])
            sheet_exists = any(sheet['properties']['title'] == sheet_name for sheet in sheets)
            
            if sheet_exists:
                logger.info(f"工作表 {sheet_name} 已存在")
                return True
            
            # 创建工作表
            request = {
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }
            
            await self._queue_operation(
                lambda: self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': [request]}
                ).execute(),
                f"创建工作表 {sheet_name}"
            )
            
            logger.info(f"成功创建工作表: {sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"创建工作表时出错: {str(e)}")
            return False
    
    async def ensure_sheet_headers(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """确保工作表有正确的表头
        
        Args:
            spreadsheet_id: Google表格ID
            sheet_name: 工作表名称
            
        Returns:
            是否成功
        """
        try:
            # 检查缓存
            cache_key = f"{spreadsheet_id}_{sheet_name}_headers"
            if cache_key in self._header_cache:
                logger.debug(f"从缓存获取表头状态: {sheet_name}")
                return self._header_cache[cache_key]
            
            # 检查第一行是否已经有表头
            range_name = f"{sheet_name}!A1:J1"
            result = await self._queue_operation(
                lambda: self.service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute(),
                f"检查工作表 {sheet_name} 的表头"
            )
            
            values = result.get('values', [])
            if values and len(values[0]) >= 10:
                logger.info(f"工作表 {sheet_name} 已有表头")
                # 缓存结果
                self._header_cache[cache_key] = True
                return True
            
            # 创建表头
            headers = [
                '写入时间',
                '群组',
                '数据日期',
                '渠道',
                '新增注册用户',
                '新增付费人数',
                '新增付费金额',
                '总充值金额',
                '总提现金额',
                '充提差'
            ]
            
            body = {
                'values': [headers]
            }
            
            await self._queue_operation(
                lambda: self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A1",
                    valueInputOption='RAW',
                    body=body
                ).execute(),
                f"创建工作表 {sheet_name} 的表头"
            )
            
            # 缓存结果
            cache_key = f"{spreadsheet_id}_{sheet_name}_headers"
            self._header_cache[cache_key] = True
            
            logger.info(f"成功创建表头: {sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"创建表头时出错: {str(e)}")
            return False 