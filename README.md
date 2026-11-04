# ics-roster

多人排班的 **ICS 生成 · 上传 · 可视化** 服务。

排班在网页上以「人员 × 日期」网格可视化编辑，服务端存储后直接对外提供 ICS 订阅地址，
手机 / Outlook / Google 日历订阅一次即可自动更新，无需反复导入导出文件。

## 特性

- **多人排班看板**：人员为行、日期为列的月视图，点格子选班次，颜色区分早班 / 晚班 / 夜班 / 休息
- **导入已有 ICS**：上传历史 `.ics` 排班文件，按「标题 + 时段」分组后逐组指定人员与班次，解析结果直接入库并进入可视化看板
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
│  │  ├─ db.py / models.py  # SQLite 会话与 ORM 模型
│  │  ├─ schemas.py         # 请求响应模型
│  │  ├─ routers/
│  │  │  ├─ shifts.py       # 人员、班次类型、排班 CRUD
│  │  │  ├─ calendar.py     # ICS 订阅接口
│  │  │  └─ imports.py      # ICS 导入（预览 + 落库）
│  │  ├─ services/
│  │  │  ├─ ics.py          # RFC 5545 ICS 生成（含折行、转义、VTIMEZONE）
│  │  │  └─ ics_import.py   # ICS 解析与 RRULE 展开
│  │  └─ seed.py            # 首次启动写入默认班次类型
│  └─ requirements.txt
├─ frontend/                # Vue3 排班看板
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
| GET | `/api/persons` | 人员列表（默认不含已停用） |
| POST | `/api/persons` | 新增人员 |
| PUT | `/api/persons/{id}` | 修改人员 |
| DELETE | `/api/persons/{id}` | 停用人员（软删除，保留历史排班） |
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

批量上传示例：

```bash
curl -X POST http://127.0.0.1:8210/api/shifts/bulk \
  -H 'Content-Type: application/json' \
  -d '{"items":[
        {"person_id":1,"shift_type_id":1,"work_date":"2026-11-05","note":"早班值守"},
        {"person_id":2,"shift_type_id":2,"work_date":"2026-11-05","note":""}
      ]}'
```

## ICS 订阅

- 团队：`http://<host>:8000/api/calendar/team.ics?token=<ICS_ROSTER_TEAM_TOKEN>`
- 个人：`http://<host>:8000/api/calendar/person/<person_id>/<feed_token>.ics`

> iPhone：设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅的日历。
> 订阅地址内嵌 token，泄露后可在页面上「轮换 token」立即失效。

行为约定：

- 晚班等跨天班次的 `DTEND` 自动落到次日
- `emit_to_calendar=false` 的班次（如休息）不写入日历
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
| 班次识别 | 标题含班次名优先，其次按起止时间精确匹配班次类型；全天事件默认落到「不写入日历」的类型（如休息） |
| 重复规则 | `RRULE` 的 `FREQ=DAILY/WEEKLY/MONTHLY`，支持 `INTERVAL` / `COUNT` / `UNTIL` / `BYDAY` |
| 时间写法 | `;TZID=`、`;VALUE=DATE`（全天）、`Z` 结尾的 UTC，统一换算到 `Asia/Shanghai` |
| 幂等 | 同人同天已存在且班次相同则跳过；班次不同则覆盖 |
| 安全 | 单文件 ≤ 8MB；单次展开上限 2000 条事件，防止畸形 RRULE |

## 部署（Linux + Docker）

```bash
cp .env.example .env      # 修改 ICS_ROSTER_TEAM_TOKEN
docker compose up -d --build
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

## 许可证

[MIT](LICENSE)
