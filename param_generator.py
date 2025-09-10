# -*- coding: utf-8 -*-
# -------------------------------
# 文件名   :   param_generator.py
# -------------------------------
# 说明 :   参数生成器，用于生成时间戳、随机数和签名
# 作者 :   Miya
# 邮箱 :   miya514521@gmail.com
# 创建日期 :   2025/02/10 15:02:15
# Miya出品，主打乱写
# -------------------------------

import time
import random
import hashlib
import json

class ParamGenerator:

    @staticmethod
    def add_common_params(request_data: dict, auto_generate_config: list) -> dict:
        """添加通用参数"""
        # 创建一个新的字典，避免修改原始数据
        data = request_data.copy()
        
        # 确保移除配置信息，避免被发送到服务器
        if 'auto_generate' in data:
            del data['auto_generate']
        
        # 处理自动生成的参数
        for param in auto_generate_config:
            param_name = param['name']
            param_type = param['type']
            
            if param_type == 'timestamp':
                value = int(ParamGenerator.generate_timestamp())  # 直接转换为整数
                data[param_name] = value
            elif param_type == 'random':
                length = param.get('length', 12)
                value = int(ParamGenerator.generate_random(length))  # 直接转换为整数
                data[param_name] = value
            elif param_type == 'signature':
                # 最后处理签名
                continue
                
        # 如果需要生成签名，在所有参数都添加完后计算
        if any(p['type'] == 'signature' for p in auto_generate_config):
            signature_param = next(p['name'] for p in auto_generate_config if p['type'] == 'signature')
            data[signature_param] = ParamGenerator.generate_signature(data)
            
        return data

    @staticmethod
    def generate_timestamp():
        """生成时间戳"""
        return str(int(time.time()))

    @staticmethod
    def generate_random(length=12):
        """生成指定长度的随机数"""
        first_digit = random.choice('123456789')
        rest_digits = ''.join(random.choice('0123456789') for _ in range(length - 1))
        return first_digit + rest_digits

    @staticmethod
    def generate_signature(data):
        """根据规则生成签名"""
        
        # 排除不参与签名的字段
        exclude_keys = {"timestamp", "signature", "track"}
        
        def sort_and_stringify(obj):
            """递归处理对象，按照规则排序并转换为 JSON 字符串"""
            if isinstance(obj, dict):
                sorted_items = {k: sort_and_stringify(v) for k, v in sorted(obj.items()) if k not in exclude_keys and not isinstance(v, list)}
                return json.dumps(sorted_items, separators=(',', ':'), ensure_ascii=False)  # 确保无空格
            return obj  # 直接返回非 dict 类型的值
        
        # 处理 JSON 并转换成字符串
        sorted_json_str = sort_and_stringify(data)
        
        # 打印用于签名的参数
        # print("\n=== 签名参数 ===")
        # print(f"原始数据: {data}")
        # print(f"参与签名的字符串: {sorted_json_str}")
        # print("==================\n")
        
        # 计算 MD5 并转换为大写
        md5_hash = hashlib.md5(sorted_json_str.encode('utf-8')).hexdigest().upper()
        
        return md5_hash
