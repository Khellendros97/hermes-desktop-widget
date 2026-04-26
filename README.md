# Hermes Desktop Panel

桌面悬浮助手面板 —— 为 [Hermes Agent Gateway](https://github.com/srun-hermes/hermes-gateway) 设计的 Dynamic Island 风格桌面客户端。

![Hidden](hidden_after.png)  |  ![Notify](notify_after.png)  |  ![Chat](chat_after2.png)

---

## 功能

- **三态 Dynamic Island**：隐藏条 → 通知气泡 → 全聊界面，平滑过渡动画
- **流式响应**：实时渲染 Hermes 的流式回复，支持 Markdown + 代码高亮
- **聊天记录持久化**：SQLite 本地存储，重启不丢失
- **快捷操作**：Approve / Deny 一键填入指令
- **网页链接检测**：消息中的 URL 自动渲染为可点击链接
- **门户快速入口**：一键打开配置的门户网站
- **托盘驻留**：系统托盘图标，点击展开/折叠
- **拖拽移动**：通知态下拖拽窗口任意位置
- **自动隐藏**：鼠标离开后自动折叠为隐藏条

## 安装

### 依赖

- Python 3.10+
- PyQt6
- websocket-client

```bash
git clone https://github.com/your-org/hermes-panel.git
cd hermes-panel
pip install -r requirements.txt
```

### 启动

```bash
python main.py
```

首次启动须在托盘右键 → Settings 中配置服务器地址与 Token。

## Hermes 服务端初始化

`hermes_setup/` 目录包含了服务端初始化所需的所有文件：

```
hermes_setup/
├── gateway/                          # Desktop 平台适配器
│   └── platforms/
│       └── desktop.py                # WebSocket 平台（aiohttp）
└── hermes-desktop-channel-skill/     # Hermes 安装 Skill
    └── hermes-desktop-channel-setup/
        └── SKILL.md                  # 配置指南
```

### 安装步骤

1. 将 `hermes_setup/` **整个目录发送给 Hermes**（在聊天中上传/拖入）
2. 在消息中告知 Hermes：
   > 请按照 `hermes_setup/hermes-desktop-channel-skill/hermes-desktop-channel-setup/SKILL.md` 的说明，在服务器上配置 Desktop 渠道
3. Hermes 会读取 SKILL 中的配置指南，自动完成以下操作：
   - 安装依赖（`aiohttp`）
   - 编辑 `~/.hermes/config.yaml`，添加 Desktop 渠道配置
   - 重启 Gateway 使配置生效
4. 确认日志中有 `Listening on ws://0.0.0.0:8643/ws` 输出，表示 Desktop 渠道启动成功

> 💡 若需自定义 Token、端口或启用 TLS/SSL，在发送给 Hermes 时一并说明即可。

## 配置

右键托盘图标 → **Settings** 进入配置面板：

| 配置项 | 说明 |
|--------|------|
| Server (Host) | Hermes 服务器地址 |
| Server (Port) | WebSocket 端口（默认 8643） |
| Server (Token) | 认证令牌 |
| Portal URL | 门户网站地址（可选，配置后显示 🏠 按钮） |
| Hide Delay | 通知态自动隐藏延迟（毫秒） |

### 存储位置

- **配置文件**：Windows 注册表 `HKCU\Software\HermesPanel\config`
- **数据库**：`%APPDATA%\HermesPanel\messages.db`
- **日志**：`%APPDATA%\HermesPanel\panel.log`

## 使用

### 界面状态

| 状态 | 触发 | 交互 |
|------|------|------|
| **HIDDEN** | 默认状态 | 鼠标悬停顶部 → 展开通知 |
| **NOTIFY** | 悬停 / 收到通知 | 点击 → 展开聊天；拖拽 → 移动窗口；🏠 → 打开门户 |
| **CHAT** | 点击通知 / 托盘图标 | 输入消息；快捷按钮（Approve / Deny）；🏠 → 门户；⚙ → 设置 |

### 快捷键

| 按键 | 行为 |
|------|------|
| `Enter` | 发送消息 |
| `Shift+Enter` | 换行 |

### 快捷指令

- **Approve** — 在输入框填入 `/approve`
- **Deny** — 在输入框填入 `/deny`

## 项目结构

```
hermes-panel/
├── main.py                 # 入口，Application 组装
├── requirements.txt        # Python 依赖
├── hermes_panel/
│   ├── __init__.py         # 版本号
│   ├── panel.py            # DynamicIsland 主 UI + MessageBubble + NotifyStrip
│   ├── client.py           # WebSocket 客户端（自动重连）
│   ├── protocol.py         # 消息协议（delta/done/auth）
│   ├── config.py           # QSettings 配置管理
│   ├── store.py            # SQLite 消息存储
│   ├── tray.py             # 系统托盘
│   ├── settings_dialog.py  # 设置对话框
│   └── resources/
│       └── styles.qss      # 全局样式表
├── tests/
│   ├── test_panel_notify.py
│   ├── test_protocol.py
│   └── test_store.py
├── docs/
│   └── plans/              # 设计文档
└── scripts/
    └── build_exe.py        # PyInstaller 打包脚本
```

## 开发

```bash
# 运行测试
python -m pytest tests/ -v

# 打包为独立 exe
python scripts/build_exe.py
```

## 技术栈

- **PyQt6** — 跨平台桌面 UI
- **websocket-client** — WebSocket 通信（自动重连、心跳保活）
- **SQLite / WAL** — 本地消息持久化
- **QPropertyAnimation** — 界面状态过渡动画
- **QSS** — 暗色主题样式
- **PyInstaller** — 单文件分发

## 协议

MIT
