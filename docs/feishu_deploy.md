# 飞书机器人入口与云端部署说明

## 当前第一版能力

- 飞书机器人菜单按钮打开云端网页工具。
- 用户第一次进入时会识别飞书身份。
- 未授权用户只能提交使用申请，不能进入海报工具。
- 管理员可以在管理页同意或拒绝申请。
- 用户点击“导出图片”或“批量导出”时，会记录导出日志，并给管理员发送飞书通知。
- 权限申请会发送飞书消息卡片，管理员可以直接在卡片里点“同意 / 拒绝”。
- 飞书卡片按钮需要配置卡片回调地址。

## 飞书菜单里填写什么

机器人菜单的“跳转至指定链接”里填写云端 HTTPS 地址：

```text
https://你的云端域名/feishu/start
```

不要填写：

```text
http://127.0.0.1:8765
```

`127.0.0.1` 只代表打开者自己的电脑，别人点开不会访问到你的工具。

## 云端环境变量

部署平台里需要配置：

```text
APP_PUBLIC_BASE_URL=https://你的云端域名
FEISHU_APP_ID=你的 App ID
FEISHU_APP_SECRET=你的 App Secret
FEISHU_ADMIN_OPEN_ID=接收通知的管理员 open_id
ADMIN_TOKEN=一串只有你知道的管理口令
FEISHU_REQUIRE_LOGIN=true
```

可选：

```text
POSTER_DB_PATH=/app/data/poster_tool.sqlite
HOST=0.0.0.0
PORT=8765
```

本地测试时，如果没有配置飞书信息，程序会自动使用本地测试用户，并默认通过权限。

## 管理员页面

上线后访问：

```text
https://你的云端域名/admin/requests?admin_token=你的 ADMIN_TOKEN
```

这里可以同意或拒绝用户申请。

## 启动命令

本地：

```bash
python src/web_app.py
```

云端：

```bash
python src/web_app.py --host 0.0.0.0
```

部署平台如果支持 `Procfile`，会自动使用：

```text
web: python src/web_app.py --host 0.0.0.0
```

## 飞书权限建议

飞书应用里建议开通：

- 机器人能力。
- 网页应用能力。
- 获取用户身份相关权限。
- 发送消息相关权限。

## 卡片回调配置

如果要在飞书消息卡片里直接点击“同意 / 拒绝”，需要在飞书开放平台配置回调地址：

```text
https://你的云端域名/feishu/card/callback
```

当前 Render 部署对应：

```text
https://four-star-poster-tool.onrender.com/feishu/card/callback
```

配置位置通常在：

```text
事件与回调 / 回调配置 / 卡片回调
```

如果飞书要求验证请求地址，保存时它会向这个地址发送验证请求，后端会自动返回 `challenge`。
