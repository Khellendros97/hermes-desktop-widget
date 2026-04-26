---
name: hermes-desktop-channel-setup
description: 在 Hermes Agent 中配置 Desktop 渠道（基于 WebSocket 的双向实时通信平台），让你的桌面客户端接入 Hermes。支持 Token 认证、可选 TLS、自定义端口。适用于自建 Desktop Panel 客户端的用户。
category: devops
tags: [hermes, desktop, websocket, platform, channel, setup]
prerequisites:
  - Python 3.8+
  - aiohttp
  - Hermes Gateway 已运行
  - 网络可访问 WebSocket 端口
---

# Hermes Desktop 渠道配置指南

## 什么是 Desktop 渠道？

Hermes Desktop 渠道是一个基于 **WebSocket 的双向实时通信平台**。

- Desktop Panel 客户端通过 WebSocket 连接到 Hermes Gateway
- 支持实时接收消息并即时回复
- 通过 Token 进行身份认证，安全可靠
- 可选 TLS/SSL 加密传输

```
Desktop 客户端  ──WS/WSS──  Hermes Gateway  ──  AI Agent
```

## 环境要求

| 要求 | 说明 |
|------|------|
| Python | Python 3.8+ |
| aiohttp | `pip install aiohttp` |
| Token | 自定义访问令牌 |
| 网络 | WebSocket 端口可访问 |

## 配置步骤

### 1. 编辑 config.yaml

编辑 `~/.hermes/config.yaml`，添加或确认以下配置：

```yaml
# ~/.hermes/config.yaml
platforms:
  desktop:
    enabled: true            # 启用 Desktop 渠道
    token: "your-secret-token-here"   # ⚠️ 必填！建议使用随机字符串
    host: "0.0.0.0"          # 监听地址
    port: 8643               # WebSocket 端口
    # 可选：TLS 加密
    # tls_cert: "/path/to/cert.pem"
    # tls_key: "/path/to/key.pem"
```

> 💡 Token 建议使用随机字符串生成：
> ```bash
> openssl rand -hex 32
> ```

### 2. 重启 Gateway

```bash
hermes gateway run
```

### 3. 确认日志输出

启动后应看到类似输出：

```
[desktop] Listening on ws://0.0.0.0:8643/ws
```

### 4. 健康检查

```bash
curl http://localhost:8643/health
```

应返回：

```json
{"status": "ok", "platform": "desktop"}
```

## 客户端连接流程

### Step 1：建立 WebSocket 连接

```
ws://host:8643/ws
```

### Step 2：发送认证消息

```json
{"type": "auth", "token": "your-token"}
```

### Step 3：接收认证结果

```json
{"type": "auth_ok"}
```

### Step 4：发送消息

```json
{"type": "message", "text": "Hello Hermes!"}
```

## 支持的消息类型

| type | 说明 |
|------|------|
| `ping` / `pong` | 保持连接活跃，心跳检测 |
| `message` | 发送文本消息给 AI Agent |
| `delta` | AI 回复的流式片段（用于打字机效果） |
| `notification` | 系统通知提示 |
| `done` | 回复生成完毕信号 |

## 常见问题

**Q: Token 忘了怎么办？**
A: 修改 `config.yaml` 中的 `token` 值，重启 Gateway 即可。

**Q: 端口被占用？**
A: 修改 `port` 为其他端口（如 `8644`），记得更新客户端配置。

**Q: TLS 证书哪里来？**
A: 使用 Let's Encrypt 免费证书，或自行签发自签名证书。

**Q: 外网无法连接？**
A: 检查防火墙/安全组规则，确保 8643 端口（或其他自定义端口）可访问。

## 验证 Desktop 渠道是否正常工作

1. 启动 Gateway 后，检查日志确认 `[desktop] Listening on ws://...`
2. 用 curl 测试健康检查端点：`curl http://localhost:8643/health`
3. 使用客户端连接并发送消息，确认能收到 AI 回复

## 参考文件

- Gateway 配置：`~/.hermes/config.yaml`
- Desktop 平台注册：`hermes_cli/platforms.py`（已内置 desktop 平台）
- Desktop 适配器：`gateway/platforms/desktop.py`
