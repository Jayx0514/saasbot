# RA9Bot - Telegram数据报告机器人

一个功能强大的Telegram机器人，用于自动获取和发送数据报告，支持定时任务、Google Sheets集成和多种数据源。

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Windows/Linux/macOS

### 自动安装

1. 克隆项目到本地
```bash
git clone <your-repo-url>
cd ra9bot
```

2. 运行自动安装脚本
```bash
python setup.py
```

3. 激活虚拟环境
```bash
# Windows
.\venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

### 手动安装

如果自动安装失败，可以手动安装：

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows: .\venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## ⚙️ 配置

### 1. 基本配置

编辑 `config.yaml` 文件：

```yaml
# Telegram Bot Token
bot:
  token: "YOUR_BOT_TOKEN"

# 管理员ID列表
admins:
  - 123456789
  - 987654321

# API登录配置
api:
  ssl_verify: false
  login:
    username: "your_username"
    password: "your_password" 
    totp_secret: "YOUR_TOTP_SECRET"
    url: "https://your-api-domain.com/api/Login/Login"

# 群组和渠道配置
groups:
  GROUP_NAME:
    name: "群组显示名称"
    tg_group: "-123456789"  # Telegram群组ID
    channel_ids:
      - id: "CHANNEL_ID_1"
      - id: "CHANNEL_ID_2"
```

### 2. Google Sheets配置（可选）

如果需要使用Google Sheets功能：

1. 在Google Cloud Console创建服务账号
2. 下载凭据文件并重命名为 `credentials.json`
3. 将文件放在项目根目录

```yaml
google_sheets:
  credentials_file: "credentials.json"
  daily_sheet_name: "日报数据"
  hourly_sheet_name: "时报数据"
  group_spreadsheets:
    GROUP_NAME: "SPREADSHEET_ID"
```

## 🤖 功能特性

### 用户命令

- `/today` - 获取今日数据报告
- `/yesterday` - 获取昨日数据报告

### 管理员命令

- `/start` - 启动机器人管理界面
- `/getid` - 获取聊天和用户ID信息
- `/reload` - 重新加载配置文件
- `/testpackage` - 测试包数据处理功能

### 自动功能

- **定时报告**: 自动发送日报和时报
- **数据同步**: 自动同步数据到Google Sheets
- **多群组支持**: 支持向多个Telegram群组发送数据
- **渠道过滤**: 只处理配置中指定的渠道数据

## 📊 数据源

项目支持以下数据接口：

1. **包列表接口**: `/api/Package/GetPageList`
2. **包分析接口**: `/api/RptDataAnalysis/GetPackageAnalysis`

数据字段映射：
- 渠道: `packageName`
- 新增注册用户: `newMemberCount`
- 新增付费用户: `newMemberRechargeCount`
- 新增付费金额: `newMemberRechargeAmount`
- 总充值金额: `rechargeAmount`
- 总提现金额: `withdrawAmount`
- 充提差: `chargeWithdrawDiff`

## 🔐 安全特性

- **统一认证**: 所有API请求使用统一的登录认证
- **参数验签**: 自动生成时间戳、随机数和MD5签名
- **Token管理**: 自动管理和刷新访问令牌
- **SSL配置**: 支持SSL证书验证配置

## 🛠️ 开发

### 项目结构

```
ra9bot/
├── main.py                 # 主程序入口
├── config.yaml            # 配置文件
├── requirements.txt       # 依赖列表
├── setup.py              # 安装脚本
├── auth_manager.py       # 认证管理
├── api_client.py         # API客户端
├── param_generator.py    # 参数生成器
├── config_loader.py      # 配置加载器
├── api_data_reader.py    # 数据读取器
├── google_sheets_writer.py # Google表格写入器
├── scheduler.py          # 任务调度器
├── utils.py              # 工具函数
└── logs/                 # 日志目录
```

### 添加新功能

1. 在相应模块中添加新方法
2. 更新配置文件结构（如需要）
3. 添加相应的命令处理器
4. 更新文档

## 📝 日志

项目会自动创建日志文件：
- 位置: `logs/bot.log`
- 轮转: 每日轮转，保留30天
- 级别: INFO及以上

## 🔧 故障排除

### 常见问题

1. **Token过期**: 检查API登录配置和TOTP密钥
2. **群组ID错误**: 使用 `/getid` 命令获取正确的群组ID
3. **权限问题**: 确保机器人在目标群组中有发送消息权限
4. **依赖安装失败**: 尝试升级pip或使用国内镜像源

### 调试模式

启用详细日志记录：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📧 联系

如有问题请联系项目维护者。
