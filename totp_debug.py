# -*- coding: utf-8 -*-
# -------------------------------
# 文件名   :   totp_debug.py
# -------------------------------
# 说明 :   TOTP验证码调试工具，用于校对谷歌验证码偏移
# -------------------------------

import pyotp
import time
from datetime import datetime, timezone
from config_loader import ConfigLoader

class TOTPDebugger:
    def __init__(self):
        """初始化TOTP调试器"""
        self.config_loader = ConfigLoader()
        self.login_config = self.config_loader.config.get('api', {}).get('login', {})
        self.totp_secret = self.login_config.get('totp_secret', '')
        
        if not self.totp_secret:
            raise ValueError("未找到TOTP密钥配置")
            
        self.totp = pyotp.TOTP(self.totp_secret)
    
    def get_current_codes_with_offsets(self):
        """获取当前时间及前后偏移的验证码"""
        current_time = time.time()
        codes_info = []
        
        # 生成前后10个时间窗口的验证码 (每个窗口30秒)
        for offset in range(-10, 11):
            timestamp = current_time + (offset * 30)
            code = self.totp.at(timestamp)
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            codes_info.append({
                'offset': offset,
                'timestamp': timestamp,
                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S UTC'),
                'code': code,
                'is_current': offset == 0
            })
        
        return codes_info
    
    def find_code_offset(self, correct_code):
        """根据正确的验证码找到时间偏移"""
        codes_info = self.get_current_codes_with_offsets()
        
        matching_offsets = []
        for info in codes_info:
            if info['code'] == correct_code:
                matching_offsets.append(info)
        
        return matching_offsets
    
    def display_current_status(self):
        """显示当前TOTP状态"""
        print("=" * 60)
        print("🔐 TOTP验证码调试工具")
        print("=" * 60)
        
        current_time = time.time()
        current_dt = datetime.fromtimestamp(current_time, tz=timezone.utc)
        
        print(f"📅 当前UTC时间: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏰ 当前时间戳: {int(current_time)}")
        print(f"🔑 TOTP密钥: {self.totp_secret}")
        print(f"🎯 当前验证码: {self.totp.now()}")
        print()
        
        # 显示时间窗口内的所有验证码
        print("📋 时间窗口验证码列表:")
        print("-" * 60)
        print(f"{'偏移':<4} {'验证码':<8} {'UTC时间':<20} {'状态'}")
        print("-" * 60)
        
        codes_info = self.get_current_codes_with_offsets()
        for info in codes_info:
            status = "👉 当前" if info['is_current'] else ""
            print(f"{info['offset']:>3}  {info['code']:<8} {info['datetime']:<20} {status}")
        
        print("-" * 60)
    
    def interactive_debug(self):
        """交互式调试"""
        while True:
            self.display_current_status()
            
            print("\n🔧 请选择操作:")
            print("1. 输入正确的验证码进行比较")
            print("2. 刷新当前状态")
            print("3. 退出")
            
            choice = input("\n请输入选择 (1-3): ").strip()
            
            if choice == '1':
                self.compare_with_correct_code()
            elif choice == '2':
                continue
            elif choice == '3':
                print("👋 调试结束")
                break
            else:
                print("❌ 无效选择，请重新输入")
                input("按回车键继续...")
    
    def compare_with_correct_code(self):
        """与正确验证码进行比较"""
        print("\n" + "="*40)
        print("🎯 验证码比较")
        print("="*40)
        
        correct_code = input("请输入当前正确的谷歌验证码: ").strip()
        
        if not correct_code or len(correct_code) != 6 or not correct_code.isdigit():
            print("❌ 请输入6位数字验证码")
            input("按回车键继续...")
            return
        
        # 查找匹配的偏移
        matching_offsets = self.find_code_offset(correct_code)
        
        if not matching_offsets:
            print(f"❌ 未找到匹配的验证码 {correct_code}")
            print("可能的原因:")
            print("- 验证码输入错误")
            print("- 时间偏移超出了检测范围(-10到+10个时间窗口)")
            print("- TOTP密钥配置错误")
        else:
            print(f"✅ 找到匹配的验证码!")
            print(f"正确验证码: {correct_code}")
            print(f"系统当前验证码: {self.totp.now()}")
            print()
            
            print("📊 匹配的时间偏移:")
            for match in matching_offsets:
                offset_seconds = match['offset'] * 30
                if match['offset'] == 0:
                    print(f"  偏移: {match['offset']} (当前时间) - 无偏移")
                elif match['offset'] < 0:
                    print(f"  偏移: {match['offset']} ({offset_seconds}秒) - 系统时间快了{abs(offset_seconds)}秒")
                else:
                    print(f"  偏移: {match['offset']} (+{offset_seconds}秒) - 系统时间慢了{offset_seconds}秒")
                
                print(f"  对应时间: {match['datetime']}")
            
            # 给出建议
            if len(matching_offsets) == 1:
                offset = matching_offsets[0]['offset']
                if offset != 0:
                    offset_seconds = offset * 30
                    print(f"\n💡 建议:")
                    if offset < 0:
                        print(f"系统时间比正确时间快了约{abs(offset_seconds)}秒")
                        print("建议调整系统时间或在代码中添加时间偏移补偿")
                    else:
                        print(f"系统时间比正确时间慢了约{offset_seconds}秒")
                        print("建议调整系统时间或在代码中添加时间偏移补偿")
                else:
                    print(f"\n✅ 时间同步正常，无需调整")
        
        input("\n按回车键继续...")

def main():
    """主函数"""
    try:
        debugger = TOTPDebugger()
        debugger.interactive_debug()
    except Exception as e:
        print(f"❌ 错误: {e}")
        input("按回车键退出...")

if __name__ == "__main__":
    main()