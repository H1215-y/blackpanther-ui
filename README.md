# BlackPanther UI / 黑豹代理界面

黑豹代理的网页与 Python API 适配层。本包是 2026-11-23 整理的本地源码快照，尚未与当天实机源码逐文件核对，也未在全新环境完成安装验收。

## 包含什么

- 首页代理模式开关、节点选择与测速、订阅管理。
- 设备管理前端与状态适配模块。
- 当前特定服务商的登录/订阅捕获模块与凭据加密存储代码。

前端：`index.html`、`app.js`、`features.js`、`style.css`。
后端入口：`server.py`。其他 Python 模块为其导入依赖，不能只拷贝入口文件。

这不是 Mihomo 内核、XD 配置管理服务或 HAOS 镜像。浏览器不能直接打开 HTML 就获得完整功能。

## 后端依赖

- Python 环境及 `requirements.txt` 中的 cryptography（用于保存服务商凭据）。
- 已有 Mihomo 控制 API，兼容本适配层所调用的端点。
- 已有 XD 控制后端，提供 `/api/control/profiles` 等订阅管理接口。
- 设备开关需要独立的设备助手写入状态；该助手、Linux 防火墙和 DIRECT listener 不在本 UI 包内。
- 服务商自动登录功能还需要兼容的 WebDriver/Chromium 服务；模块绑定特定服务商域名允许名单，不能当作通用网站登录器。

## 配置与启动参考

复制 `config/server.env.example` 为 `config/server.env`，在部署机器本地填写真实值，不提交到 Git。

服务器环境变量：

| 变量 | 用途 |
|---|---|
| `XD_URL` | XD 控制服务基础地址；包内默认 `http://127.0.0.1:8088` |
| `CORE_URL` | Mihomo 控制 API；包内默认 `http://127.0.0.1:9091` |
| `XD_DATA` | 含 `server.env` 的目录 |
| `BP_STATE` | 可写状态目录；首次启动前自行创建 |
| `PORT` | 网页服务端口，默认 `8099` |
| `WEBDRIVER_URL` | 可选 WebDriver 地址，默认 `http://127.0.0.1:4445` |
| `FRAME_ANCESTORS` | 允许 iframe 嵌入的来源列表，默认 `'self'`；嵌入 HA 时填写其实际来源 |
| `BP_LAN_CIDR` | 路由器名单过滤网段，默认样例 `192.168.1.0/24` |
| `BP_GATEWAY_IP` / `BP_HOST_IP` | 名单中过滤路由器/黑豹自身，默认样例 `.1.1` / `.1.2` |

示例（Linux，仅供在已配置的后端环境中使用）：

```sh
python -m pip install -r requirements.txt
mkdir -p ./state
XD_DATA="$PWD/config" BP_STATE="$PWD/state" python server.py
```

服务默认监听所有网卡。应部署在受控网络内，按实际环境配置访问控制及 HTTPS；本包不修改路由器、系统网关或防火墙。

## 发布与备份边界

- 不包含真实控制密钥、订阅 URL、账号、浏览器会话、设备清单、MAC、日志和运行数据库。
- `.gitignore` 仅帮助防止误提交，不能清理已经进入 Git 历史的秘密。
- 配置样例中的值为空，需要部署者自行填写。
- 本地源码包只做静态语法和文件依赖检查，不等同于已经备份实机最新状态或完整复现运行环境。
- 服务商公开入口域名仍保留在代码中；上传前可按用途决定是否保留该专用功能。
- 未擅自选择开源许可证；公开发布前由仓库所有者决定授权方式，并核对使用素材及依赖的许可。
