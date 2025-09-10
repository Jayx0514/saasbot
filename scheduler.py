import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Optional, Callable, Coroutine
import pytz

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        """初始化调度器"""
        self.tasks = {}
        self.running = False
        self.loop = None
    
    async def start(self):
        """启动调度器"""
        self.running = True
        self.loop = asyncio.get_running_loop()
        logger.info("调度器已启动")
    
    async def stop(self):
        """停止调度器"""
        self.running = False
        for task_id, task in self.tasks.items():
            if not task['task'].done():
                task['task'].cancel()
        logger.info("调度器已停止")
    
    def add_interval_task(self, task_id: str, interval_minutes: int, 
                          callback: Callable[[], Coroutine], *args, **kwargs):
        """添加按间隔时间执行的任务
        
        Args:
            task_id: 任务ID
            interval_minutes: 间隔分钟数
            callback: 回调函数
            *args, **kwargs: 回调函数的参数
        """
        if task_id in self.tasks:
            # 如果任务已存在，取消旧任务
            if not self.tasks[task_id]['task'].done():
                self.tasks[task_id]['task'].cancel()
        
        # 创建新任务
        task = self.loop.create_task(
            self._run_interval_task(interval_minutes, callback, *args, **kwargs)
        )
        
        self.tasks[task_id] = {
            'type': 'interval',
            'interval': interval_minutes,
            'callback': callback,
            'args': args,
            'kwargs': kwargs,
            'task': task
        }
        
        logger.info(f"已添加间隔任务 {task_id}，间隔 {interval_minutes} 分钟")
    
    def add_daily_task(self, task_id: str, hour: int, minute: int, 
                       callback: Callable[[], Coroutine], *args, **kwargs):
        """添加每日定时执行的任务
        
        Args:
            task_id: 任务ID
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            callback: 回调函数
            *args, **kwargs: 回调函数的参数
        """
        if task_id in self.tasks:
            # 如果任务已存在，取消旧任务
            if not self.tasks[task_id]['task'].done():
                self.tasks[task_id]['task'].cancel()
        
        # 创建新任务
        task = self.loop.create_task(
            self._run_daily_task(hour, minute, callback, *args, **kwargs)
        )
        
        self.tasks[task_id] = {
            'type': 'daily',
            'hour': hour,
            'minute': minute,
            'callback': callback,
            'args': args,
            'kwargs': kwargs,
            'task': task
        }
        
        logger.info(f"已添加每日任务 {task_id}，时间 {hour:02d}:{minute:02d}")
    
    def remove_task(self, task_id: str):
        """移除任务
        
        Args:
            task_id: 任务ID
        """
        if task_id in self.tasks:
            if not self.tasks[task_id]['task'].done():
                self.tasks[task_id]['task'].cancel()
            del self.tasks[task_id]
            logger.info(f"已移除任务 {task_id}")
    
    async def _run_interval_task(self, interval_minutes: int, callback: Callable[[], Coroutine], 
                                *args, **kwargs):
        """运行间隔任务"""
        while self.running:
            try:
                await callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"执行间隔任务时出错: {str(e)}")
            
            # 等待下一次执行
            await asyncio.sleep(interval_minutes * 60)
    
    async def _run_daily_task(self, hour: int, minute: int, callback: Callable[[], Coroutine], 
                             *args, **kwargs):
        """运行每日任务（使用UTC时间）"""
        while self.running:
            # 计算下一次执行时间（使用UTC时间）
            utc_now = datetime.now(pytz.UTC)
            target_time = utc_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if target_time <= utc_now:
                # 如果目标时间已经过去，设置为明天
                target_time += timedelta(days=1)
            
            # 计算等待时间
            wait_seconds = (target_time - utc_now).total_seconds()
            logger.info(f"下次执行时间 (UTC): {target_time.strftime('%Y-%m-%d %H:%M:%S')}, 等待 {wait_seconds} 秒")
            
            # 等待到执行时间
            await asyncio.sleep(wait_seconds)
            
            # 执行任务
            try:
                await callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"执行每日任务时出错: {str(e)}")