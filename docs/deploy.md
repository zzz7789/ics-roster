# ics-roster 部署说明

多人排班的 ICS 订阅服务：网页面板维护排班，服务端直接对外提供日历订阅地址。
本包为**空数据**部署包，首次启动自动建表并创建管理员账号。

**对外访问端口：21117**（容器内仍为 8000，由 compose 做端口映射）

## 一、包内容

```
ics-roster/
├─ backend/
│  ├─ app/                后端源码（FastAPI + SQLAlchemy）
│  ├─ static/             已构建前端（含 PWA 图标与 manifest，无需再 npm build）
│  └─ requirements.txt
├─ frontend/              前端源码（含 public/ 图标；仅在重新构建前端时需要）
├─ widget/                iOS Scriptable 桌面小组件（可选）
├─ database/schema.sql    参考 DDL
├─ docs/
├─ Dockerfile
├─ docker-compose.yml     对外 21117 → 容器 8000
├─ .env                   部署配置（账号、订阅 token 等）
├─ start.sh               Linux / macOS 直接启动（21117）
└─ start.bat              Windows 直接启动（21117）
```

数据文件（SQLite 库、会话密钥）都在运行后自动生成，**不在包内**。

## 二、启动方式

### 方式 1：Docker（推荐）

```bash
cd ics-roster
docker compose up -d --build
```

- 访问：`http://<服务器IP>:21117`
- 端口映射：宿主机 `21117` → 容器 `8000`
- 数据卷：当前目录下 `./data`（`ics-roster.db`、`secret.key`）
- 自动读取同目录 `.env`

### 方式 2：直接跑 Python

```bash
./start.sh          # Linux / macOS（无执行权限先 chmod +x start.sh）
start.bat           # Windows
```

脚本自动建虚拟环境、装依赖、读 `.env`，监听 `0.0.0.0:21117`，数据落在 `backend/data/`。

## 三、默认账号

见 `.env` 的 `ICS_ROSTER_ADMIN_USER` / `ICS_ROSTER_ADMIN_PASSWORD`。
账号只在数据库**还没有任何用户**时创建；登录后建议在页面右上角「改密码」修改。
密码留空则随机生成并打印在启动日志里。

## 四、配置项（.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `ICS_ROSTER_TEAM_TOKEN` | 团队整表订阅地址的 token | 必填 |
| `ICS_ROSTER_ADMIN_USER` | 首次启动创建的管理员用户名 | `zy` |
| `ICS_ROSTER_ADMIN_PASSWORD` | 管理员密码，留空则随机生成并打印日志 | — |
| `ICS_ROSTER_SESSION_DAYS` | 登录会话有效天数 | `7` |
| `ICS_ROSTER_CORS` | 跨域前端地址，同域部署留空 | 空 |
| `ICS_ROSTER_DB` | SQLite 路径 | `backend/data/ics-roster.db`（Docker 内 `/data/ics-roster.db`） |
| `ICS_ROSTER_SECRET` | 会话签名密钥，留空自动生成 `secret.key` | 空 |

## 五、手机使用

- 浏览器访问 `http://<服务器IP>:21117`，窄屏自动重排：表格横向滚动、首列冻结、点击格子从底部弹出班次选择
- **添加到主屏幕**
  - iOS：Safari → 分享 → 添加到主屏幕 → 独立窗口打开，图标为蓝色日历
  - Android：Chrome 菜单 → 添加到主屏幕（读取 `manifest.webmanifest`）
  - ⚠️ 如果之前添加过旧版本，iOS 会缓存旧图标：先**删除桌面图标**，再重新添加（页面已带 `?v=3` 版本串）
- 手机端隐藏了「团队订阅 token」输入框（低频配置），需要时在电脑上操作
- `http://内网IP` 属于非安全上下文，复制订阅地址会自动降级实现（仍可用）

## 六、日历订阅

- 团队整表：电脑上「复制订阅地址」（`/api/calendar/team.ics?token=...`）
- 单人订阅：侧栏「订阅」，或「人员 → 管理」里复制
- 早班 / 晚班为定时事件，休息为**全天事件**
- iPhone：设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅的日历
- iOS 订阅日历由系统调度刷新，一般 1 小时左右；着急可在日历 App 下拉刷新

## 七、备份与升级

```bash
# Docker
docker compose stop && tar czf backup-$(date +%F).tgz data && docker compose start

# 直接运行
cp backend/data/ics-roster.db backup-$(date +%F).db   # secret.key 一起备份更好
```

升级：替换 `backend/`、`frontend/` 后重新构建前端（或直接用包内 `backend/static`），
表结构由 SQLAlchemy `create_all` 自动补齐，不动已有数据。

## 八、常见问题

- **21117 被占用 / 想换端口**：改 `docker-compose.yml` 的 `ports` 左侧数字，或改 `start.sh` / `start.bat` 的 `--port`
- **手机页面自动放大**：本包已修（输入框 16px），旧缓存请强制刷新
- **手机点格子没反应**：本包已修（班次选择器改为渲染到 body，规避 iOS 滚动容器内 fixed 定位问题）
- **主屏幕图标不对**：删除旧图标重新添加；确认服务器上 `/apple-touch-icon.png` 返回 200
- **手机连不上**：确认同网段、防火墙放行 21117
- **订阅时间不对**：容器已设 `TZ=Asia/Shanghai`，直接运行请确认系统时区
