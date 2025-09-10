# -*- coding: utf-8 -*-
# -------------------------------
# 文件名   :   api_client.py
# -------------------------------
# 说明 :   API客户端，用于发送 HTTP 请求
# 作者 :   Miya
# 邮箱 :   miya514521@gmail.com
# 创建日期 :   2025/02/10 10:45:33
# Miya出品，主打乱写
# -------------------------------

import requests
from requests.exceptions import RequestException
from param_generator import ParamGenerator
import urllib3

# 禁用SSL警告（当ssl_verify=false时）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ApiClient:
    def __init__(self, base_url, default_headers=None, config=None):
        self.base_url = base_url
        self.session = requests.Session()
        self.default_headers = default_headers or {}
        self.config = config or {}
        
    def send_request(self, method, endpoint, params=None, data=None, headers=None):
        url = f"{self.base_url}{endpoint}"
        headers = {**self.default_headers, **(headers or {})}
        
        # 确保 data 是字典类型
        request_data = {} if data is None else data.copy()
        
        # 从测试数据中提取请求参数，移除配置信息
        if isinstance(data, dict):
            request_data = {k: v for k, v in data.items() 
                           if not k.startswith('expected_') and k != 'casename'}
        
        # 如果有自动生成参数配置，则处理
        if 'auto_generate' in request_data:
            auto_generate_config = request_data.get('auto_generate', [])
            request_data = ParamGenerator.add_common_params(request_data, auto_generate_config)
        
        try:
            # 设置SSL验证
            verify_ssl = True
            if self.config.get('api', {}).get('ssl_verify') is False:
                verify_ssl = False
            
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=request_data,
                headers=headers,
                timeout=10,
                verify=verify_ssl
            )
            
            try:
                json_response = response.json() if response.content else {}
                return {
                    'status_code': response.status_code,
                    'response': json_response,
                    'headers': dict(response.headers)
                }
            except ValueError as e:
                return {
                    'status_code': response.status_code,
                    'error': f"JSON解析错误: {str(e)}",
                    'response': {'message': '响应不是有效的JSON格式'},
                    'raw_response': response.text
                }
        except requests.exceptions.ConnectionError as e:
            return {
                'status_code': 503,
                'error': f"连接错误: {str(e)}",
                'response': {'message': '服务不可用'}
            }
        except requests.exceptions.Timeout as e:
            return {
                'status_code': 504,
                'error': f"请求超时: {str(e)}",
                'response': {'message': '请求超时'}
            }
        except Exception as e:
            return {
                'status_code': 500,
                'error': str(e),
                'response': {'message': '系统错误'}
            }
        except RequestException as e:
            return {'error': str(e)}
        except ValueError:
            return {'error': 'Invalid JSON response'}
