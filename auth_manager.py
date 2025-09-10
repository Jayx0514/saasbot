# -*- coding: utf-8 -*-
# -------------------------------
# 文件名   :   auth_manager.py
# -------------------------------
# 说明 :   认证管理器，用于登录获取token
# 作者 :   Miya
# 邮箱 :   miya514521@gmail.com
# 创建日期 :   2025/02/12 15:54:12
# Miya出品，主打乱写
# -------------------------------

import os
import yaml
from config_loader import ConfigLoader
from api_client import ApiClient
from param_generator import ParamGenerator
import pyotp
import time
import json

class AuthManager:
    _token_cache = {}
    
    def __init__(self, config_loader=None):
        """初始化认证管理器
        
        Args:
            config_loader: 配置加载器实例
        """
        self.config_loader = config_loader or ConfigLoader()
        
    @staticmethod
    def get_token(config_loader=None, user_type: str = 'default') -> str:
        """
        获取登录token
        :param config_loader: 配置加载器
        :param user_type: 用户类型，暂时未使用，保持兼容性
        :return: token字符串
        """
        if not config_loader:
            config_loader = ConfigLoader()
            
        cache_key = "main_login_token"
        
        if cache_key in AuthManager._token_cache:
            return AuthManager._token_cache[cache_key]
        
        # 获取配置
        config = config_loader.config
        
        # 获取登录配置
        login_config = config.get('api', {}).get('login', {})
        if not login_config:
            raise ValueError("找不到登录配置")
        
        # 创建 API 客户端
        base_url = login_config.get('url', '').replace('/api/Login/Login', '')
        client = ApiClient(
            base_url=base_url,
            default_headers={'Content-Type': 'application/json'},
            config=config
        )
        
        # 生成TOTP验证码 - 尝试多个时间窗口
        totp_secret = login_config.get('totp_secret', '')
        totp = pyotp.TOTP(totp_secret)
        
        # 尝试当前时间和前后几个时间窗口的验证码
        import time
        current_time = time.time()
        time_windows = []
        
        # 生成前后5个时间窗口的验证码 (每个窗口30秒)，重点关注负偏移
        for offset in [-5, -4, -3, -2, -1, 0, 1, 2]:
            timestamp = current_time + (offset * 30)
            code = totp.at(timestamp)
            time_windows.append({
                'offset': offset,
                'timestamp': timestamp,
                'code': code
            })
        
        # 首先尝试当前时间的验证码
        totp_code = totp.now()
        
        # 实现多时间窗口重试逻辑
        def try_login_with_code(vcode):
            """使用指定验证码尝试登录"""
            # 准备登录数据
            login_data = {
                'userName': login_config.get('username', ''),
                'pwd': login_config.get('password', ''),
                'vCode': vcode,
                'language': 'zh'
            }
            
            # 自动生成参数配置
            auto_generate_config = [
                {"name": "timestamp", "type": "timestamp"},
                {"name": "random", "type": "random", "length": 12},
                {"name": "signature", "type": "signature"}
            ]
            
            # 使用参数生成器添加通用参数
            login_data = ParamGenerator.add_common_params(login_data, auto_generate_config)
            
            request_data = {
                'method': 'POST',
                'endpoint': '/api/Login/Login',
                'data': login_data,
                'headers': {
                    'Content-Type': 'application/json',
                    'Domainurl': login_config.get('url', '').replace('/api/Login/Login', '')
                }
            }
            
            return client.send_request(**request_data)
        
        # 首先尝试当前时间的验证码
        response = try_login_with_code(totp_code)
        
        # 检查是否成功
        if ('error' not in response and 'response' in response and 
            'data' in response['response'] and 'token' in response['response']['data'] and
            response['response']['data']['token']):
            pass  # 当前时间窗口成功
        else:
            # 尝试其他时间窗口的验证码
            for window in time_windows:
                if window['code'] == totp_code:
                    continue  # 跳过已经尝试过的当前验证码
                    
                response = try_login_with_code(window['code'])
                
                # 检查是否成功
                if ('error' not in response and 'response' in response and 
                    'data' in response['response'] and 'token' in response['response']['data'] and
                    response['response']['data']['token']):
                    break  # 找到有效的验证码，退出循环
        
        if 'error' not in response:
            if 'response' in response and 'data' in response['response'] and 'token' in response['response']['data']:
                token = response['response']['data']['token']
                
                # 检查token是否为有效值（不为None且不为空字符串）
                if token and token.strip():
                    expires_in = response['response']['data'].get('expiresIn', time.time() + 24 * 3600)  # 默认24小时
                    
                    # 保存token到缓存
                    AuthManager._token_cache[cache_key] = token
                    
                    # 保存token到文件（使用原有的保存机制）
                    config_loader.save_token_to_file(token, expires_in)
                    
                    return token
                else:
                    # 检查是否有错误消息
                    error_msg = response.get('response', {}).get('msg', 'Token无效')
                    raise Exception(f"登录失败: {error_msg}")
            else:
                raise KeyError("响应格式不正确，未找到 token")
        else:
            raise Exception(f"获取token失败: {response.get('error')}")
    
    def login_and_get_token(self) -> str:
        """登录并获取token（实例方法）"""
        return self.get_token(self.config_loader)
        
    def is_token_valid(self) -> bool:
        """检查token是否有效"""
        cache_key = "main_login_token"
        return cache_key in AuthManager._token_cache
        
    def clear_token_cache(self):
        """清除token缓存"""
        cache_key = "main_login_token"
        if cache_key in AuthManager._token_cache:
            del AuthManager._token_cache[cache_key]
            print("Token缓存已清除")
    
    @staticmethod
    def add_auth_params_to_request(request_data: dict, config_loader=None) -> dict:
        """为API请求添加通用参数验签
        
        Args:
            request_data: 原始请求数据
            config_loader: 配置加载器
            
        Returns:
            添加了验签参数的请求数据
        """
        if not config_loader:
            config_loader = ConfigLoader()
            
        # 获取token
        token = AuthManager.get_token(config_loader)
        if not token:
            raise Exception("无法获取有效token")
        
        # 获取登录配置以确定base URL
        login_config = config_loader.get_api_login_config()
        base_url = login_config.get('url', '').replace('/api/Login/Login', '')
        
        # 复制原始数据，避免修改原始数据
        enhanced_data = request_data.copy()
        
        # 如果没有data字段，创建一个
        if 'data' not in enhanced_data:
            enhanced_data['data'] = {}
        
        # 自动生成参数配置
        auto_generate_config = [
            {"name": "timestamp", "type": "timestamp"},
            {"name": "random", "type": "random", "length": 12},
            {"name": "signature", "type": "signature"}
        ]
        
        # 使用参数生成器添加通用参数
        enhanced_data['data'] = ParamGenerator.add_common_params(enhanced_data['data'], auto_generate_config)
        
        # 添加认证头部
        if 'headers' not in enhanced_data:
            enhanced_data['headers'] = {}
            
        enhanced_data['headers'].update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'Domainurl': base_url
        })
        
        return enhanced_data
    
    @staticmethod
    def send_authenticated_request(endpoint: str, data: dict = None, method: str = 'POST', config_loader=None) -> dict:
        """发送带认证的API请求
        
        Args:
            endpoint: API端点
            data: 请求数据
            method: HTTP方法
            config_loader: 配置加载器
            
        Returns:
            API响应数据
        """
        if not config_loader:
            config_loader = ConfigLoader()
            
        # 准备请求数据
        request_data = {
            'method': method,
            'endpoint': endpoint,
            'data': data or {}
        }
        
        # 添加认证参数
        authenticated_request = AuthManager.add_auth_params_to_request(request_data, config_loader)
        
        # 获取登录配置以确定base URL
        login_config = config_loader.get_api_login_config()
        base_url = login_config.get('url', '').replace('/api/Login/Login', '')
        
        # 创建API客户端
        client = ApiClient(
            base_url=base_url,
            default_headers=authenticated_request.get('headers', {}),
            config=config_loader.config
        )
        
        # 发送请求
        response = client.send_request(**authenticated_request)
        return response
