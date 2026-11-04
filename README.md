# ics-roster

多人排班的 **ICS 生成 · 上传 · 可视化** 服务。

排班在网页上以「人员 × 日期」网格可视化编辑，服务端存储后直接对外提供 ICS 订阅地址，
手机 / Outlook / Google 日历订阅一次即可自动更新，无需反复导入导出文件。

## 特性

- **多人排班看板**：人员为行、日期为列的月视图，点格子选班次，颜色区分早班 / 晚班 / 夜班 / 休息
- **人员管理**：侧栏可直接新增 / 删除成员，删除时二次确认并同步清除其排班，订阅地址立即失效
- **导入 Excel 排班表**：直接吃「一人一行、一天一列」的月度排班表（早/晚/休 简称即可），自动识别表头、日期列与人员行
- **导入已有 ICS**：上传历史 `.ics` 排班文件，按「标题 + 时段」分组后逐组指定人员与班次
- **员工登录**：账号密码登录（HttpOnly Cookie 会话），未登录无法访问接口；日历订阅地址用独立 token，不需要登录
- **手机端可用**：窄屏自动重排，排班表横向滚动 + 首列冻结，班次选择改为底部弹层
- **iOS 桌面小组件**：`widget/` 下的 Scriptable 组件，订阅日历后在桌面看今天 / 本周 / 整月排班
- **ICS 订阅**：团队整表订阅 + 单人订阅，跨天班次（晚班）正确处理 `DTEND`
- **批量上传接口**：外部排班算法生成结果后，一次 `POST /api/shifts/bulk` 落库，同人同天自动覆盖
- **轻量部署**：Vue3 + FastAPI + SQLite，单容器（约 200 MB）+ 一个数据卷即可跑在 Linux 上
- **无第三方日历库**：ICS 由标准库生成，输出可控，便于按需调整字段（`COLOR`、`DESCRIPTION` 等）

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite（零 UI 框架依赖） |
| 后端 | FastAPI + SQLAlchemy 2.0 |
| 存储 | SQLite（表结构见 `database/schema.sql`） |
| 部署 | Docker / docker compose，Linux |

## 目录结构

```
ics-roster/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # FastAPI 入口，可托管前端静态文件
│  │  ├─ config.py          # 环境变量配置
│  │  ├─ db.py / models.py  # SQLite 会话与 ORM 模型（含 user）
│  │  ├─ deps.py            # require_user 登录校验依赖
│  │  ├─ schemas.py         # 请求响应模型
│  │  ├─ routers/
│  │  │  ├─ auth.py         # 登录 / 登出 / 当前用户 / 改密码
│  │  │  ├─ shifts.py       # 人员、班次类型、排班 CRUD
│  │  │  ├─ calendar.py     # ICS 订阅接口（token 鉴权，免登录）
│  │  │  └─ imports.py      # ICS / Excel 导入（预览 + 落库）
│  │  ├─ services/
│  │  │  ├─ auth.py         # pbkdf2 密码哈希 + HMAC 签名会话
│  │  │  ├─ ics.py          # RFC 5545 ICS 生成（含折行、转义、VTIMEZONE）
│  │  │  ├─ ics_import.py   # ICS 解析与 RRULE 展开
│  │  │  └─ xlsx_import.py  # Excel 排班表解析（零依赖）
│  │  └─ seed.py            # 默认班次类型 + 管理员账号初始化
│  └─ requirements.txt
├─ frontend/                # Vue3 排班看板
├─ widget/                  # iOS Scriptable 桌面小组件（读订阅日历）
├─ database/schema.sql      # 参考 DDL
├─ docs/roadmap.md          # 待确认的业务边界
├─ Dockerfile
└─ docker-compose.yml
```

## 快速开始（本地开发）

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ICS_ROSTER_TEAM_TOKEN=dev-team-token uvicorn app.main:app --reload --port 8210
```

- 接口文档：<http://127.0.0.1:8210/docs>
- 首次启动会自动建表并写入早班 / 晚班 / 夜班 / 休息四种班次类型

### 前端

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173，/api 已代理到 8210
```

### 生产构建

```bash
cd frontend && npm run build   # 产物输出到 backend/static，由 FastAPI 直接托管
```

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录（设置会话 Cookie） |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/me` | 当前登录用户 |
| POST | `/api/auth/password` | 修改密码 |
| GET | `/api/persons` | 人员列表（默认不含已停用） |
| POST | `/api/persons` | 新增人员 |
| PUT | `/api/persons/{id}` | 修改人员 |
| DELETE | `/api/persons/{id}` | 停用人员（软删除，保留历史排班） |
| DELETE | `/api/persons/{id}?purge=true` | 彻底删除人员并级联清除其全部排班（不可恢复） |
| POST | `/api/persons/{id}/token` | 轮换该人员的订阅 token |
| GET | `/api/shift-types` | 班次类型列表 |
| POST | `/api/shift-types` | 新增班次类型 |
| GET | `/api/shifts?from=&to=&person_id=` | 按区间查询排班 |
| POST | `/api/shifts` | 新增/覆盖一条排班 |
| POST | `/api/shifts/bulk` | 整批上传（排班算法结果落库） |
| PUT | `/api/shifts/{id}` | 修改排班 |
| DELETE | `/api/shifts/{id}` | 删除排班 |
| GET | `/api/calendar/team.ics?token=` | 团队整表 ICS 订阅 |
| GET | `/api/calendar/person/{id}/{token}.ics` | 单人 ICS 订阅 |
| POST | `/api/import/ics/preview` | 上传 ICS 解析预览（不落库） |
| POST | `/api/import/ics/apply` | 按确认的映射导入落库 |
| POST | `/api/import/excel/preview` | 上传 Excel 解析预览（不落库） |
| POST | `/api/import/excel/apply` | 按确认的映射导入落库 |

> 除 `/api/auth/login`、`/api/health`、`/api/calendar/*` 外，其余接口都需要登录会话。

批量上传示例：

```bash
curl -X POST http://127.0.0.1:8210/api/shifts/bulk \
  -H 'Content-Type: application/json' \
  -d '{"items":[
        {"person_id":1,"shift_type_id":1,"work_date":"2026-11-05","note":"早班值守"},
        {"person_id":2,"shift_type_id":2,"work_date":"2026-11-05","note":""}
      ]}'
```

## 登录与账号

- 首次启动若库里没有账号，会自动创建管理员：用户名 `admin`（可用 `ICS_ROSTER_ADMIN_USER` 改）。
- 密码来自 `ICS_ROSTER_ADMIN_PASSWORD`；**留空则随机生成并打印到服务日志**（`docker compose logs ics-roster` 里找「初始密码」）。
- 登录后顶栏「改密码」可修改；忘记密码可设好 `ICS_ROSTER_ADMIN_PASSWORD` 后删库重建，或用 sqlite 手工更新 `user.password_hash`。
- 会话保存在 HttpOnly Cookie，有效期默认 7 天（`ICS_ROSTER_SESSION_DAYS`）。
- 签名密钥自动生成到 `data/secret.key`（可用 `ICS_ROSTER_SECRET` 覆盖），重建密钥会让所有登录失效，但不影响数据。

## ICS 订阅

- 团队：`http://<host>:8000/api/calendar/team.ics?token=<ICS_ROSTER_TEAM_TOKEN>`
- 个人：`http://<host>:8000/api/calendar/person/<person_id>/<feed_token>.ics`

> iPhone：设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅的日历。
> 订阅地址内嵌 token，泄露后可在页面上「轮换 token」立即失效。

行为约定：

- 晚班等跨天班次的 `DTEND` 自动落到次日
- 没有起止时间的班次（如休息）输出为**全天事件**；`emit_to_calendar=false` 的班次才跳过
- 未指定 `from` / `to` 时默认取「半年前 ~ 一年后」，便于长期订阅

## 导入已有 ICS

网页顶栏「导入 ICS」按钮，或直接调接口：

```bash
# 1) 预览：只解析，返回分组与建议映射
curl -X POST http://127.0.0.1:8210/api/import/ics/preview \
  -F 'files=@排班.ics'

# 2) 落库：带上确认后的映射（group key -> 人员/班次）
curl -X POST http://127.0.0.1:8210/api/import/ics/apply \
  -F 'files=@排班.ics' \
  --form-string 'mapping={"张三 早班|08:00-16:00":{"person_id":1,"shift_type_id":1}}'
```

解析约定：

| 场景 | 处理方式 |
| --- | --- |
| 分组规则 | 按 `SUMMARY` + 时段（`08:00-16:00` / 全天）聚合，同一组只需指定一次映射 |
| 人员识别 | 标题里含已有人员名则自动匹配（取最长匹配）；匹配不到可由前端指定已有人员或「新建人员」 |
| 班次识别 | 标题含班次名优先，其次按起止时间精确匹配班次类型；全天事件默认落到「休息」类班次 |
| 重复规则 | `RRULE` 的 `FREQ=DAILY/WEEKLY/MONTHLY`，支持 `INTERVAL` / `COUNT` / `UNTIL` / `BYDAY` |
| 时间写法 | `;TZID=`、`;VALUE=DATE`（全天）、`Z` 结尾的 UTC，统一换算到 `Asia/Shanghai` |
| 幂等 | 同人同天已存在且班次相同则跳过；班次不同则覆盖 |
| 安全 | 单文件 ≤ 8MB；单次展开上限 2000 条事件，防止畸形 RRULE |

## 导入 Excel 排班表

网页顶栏「导入」→「导入 Excel」页签。要求表格形如：

| 序列 | 姓名 | 周一 | 周二 | … | 晚班 | 休息 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 张三 | 早 | 晚 | … | 11 | 8 |
| 2 | 李四 | 休 | 早 | … | 10 | 8 |

解析约定：

| 场景 | 处理方式 |
| --- | --- |
| 表头定位 | 自动寻找含「姓名」的行；上一行取日号，表头取周一~周日 |
| 日期列 | 只认表头是星期的列，天然排除「晚班/休息」这类统计列 |
| 年月推断 | 用「日号 + 星期」反推年月（如 2 号是周一只可能是某年某月），不依赖标题文字；识别不出会标黄提示手动改 |
| 人员 | 按姓名匹配已有人员，匹配不到则新建；颜色自动分配 |
| 班次 | 单元格文字（早/晚/休…）映射到班次类型，映射关系在预览页可改，也可选「不导入」 |
| 表尾 | 「早/晚/休」小计行、备注区自动跳过 |
| 幂等 | 同人同天同班次跳过，不同班次覆盖 |
| 兼容 | 只支持 `.xlsx` / `.xlsm`，旧版 `.xls` 请先用 Excel 另存 |

## 手机端

窄屏（≤720px）自动切换布局：

- 顶栏分行，月份切换按钮加大到 40px 以上
- 排班表优先展示，横向滚动 + 人员列冻结，侧栏人员/班次列表移到页面下方
- 点格子后班次选择变成底部弹层（带安全区留白），避免浮层被屏幕裁掉
- 导入向导的映射表格可横向滚动，弹窗全屏显示

## 部署（Linux + Docker）

```bash
cp .env.example .env      # 修改 ICS_ROSTER_TEAM_TOKEN 和 ICS_ROSTER_ADMIN_PASSWORD
docker compose up -d --build
docker compose logs ics-roster | grep 初始密码   # 没设密码时在这里找
```

- 访问 `http://<host>:8000`
- 数据持久化在 `./data/ics-roster.db`（容器内 `/data`）
- 备份只需拷贝该 SQLite 文件

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ICS_ROSTER_DB` | `backend/data/ics-roster.db` | SQLite 文件路径 |
| `ICS_ROSTER_DB_URL` | `sqlite:///<above>` | 完整数据库 URL，可换成 MySQL / PostgreSQL |
| `ICS_ROSTER_TEAM_TOKEN` | `change-me-team-token` | 团队订阅 token，**务必修改** |
| `ICS_ROSTER_CORS` | `http://localhost:5173` | 允许的前端源，逗号分隔 |
| `ICS_ROSTER_DIST` | `backend/static` | 前端构建产物目录，存在时由后端托管 |
| `ICS_ROSTER_ADMIN_USER` | `admin` | 首次启动创建的管理员用户名 |
| `ICS_ROSTER_ADMIN_PASSWORD` | 空 | 管理员初始密码，留空则随机生成并打印到日志 |
| `ICS_ROSTER_SESSION_DAYS` | `7` | 登录状态有效天数 |
| `ICS_ROSTER_SECRET` | 空 | 会话签名密钥，留空自动生成到 `data/secret.key` |

## 许可证

[MIT](LICENSE)
