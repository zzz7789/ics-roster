"""运行配置：全部通过环境变量覆盖，默认值适合本地开发。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite 数据库文件，docker 部署时挂载到 /data 并设置 ICS_ROSTER_DB=/data/ics-roster.db
DB_PATH = Path(os.getenv("ICS_ROSTER_DB", BASE_DIR / "data" / "ics-roster.db"))
DATABASE_URL = os.getenv("ICS_ROSTER_DB_URL", f"sqlite:///{DB_PATH}")

# 团队整体订阅地址的固定 token，形如 /api/calendar/team.ics?token=xxx
TEAM_FEED_TOKEN = os.getenv("ICS_ROSTER_TEAM_TOKEN", "change-me-team-token")

# 前端开发服务器地址，部署时可在同一域名下留空
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ICS_ROSTER_CORS", "http://localhost:5173").split(",")
    if origin.strip()
]

# 前端构建产物目录，存在时由 FastAPI 直接托管，实现单容器部署
FRONTEND_DIST = Path(os.getenv("ICS_ROSTER_DIST", BASE_DIR / "static"))

# ----------------------------- 登录与会话 -----------------------------

# 数据目录（SQLite 文件所在目录），会话签名密钥也放在这里
DATA_DIR = DB_PATH.parent
SECRET_FILE = Path(os.getenv("ICS_ROSTER_SECRET_FILE", DATA_DIR / "secret.key"))

# 首次启动自动创建的管理员；密码留空则随机生成并打印到日志
ADMIN_USER = os.getenv("ICS_ROSTER_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ICS_ROSTER_ADMIN_PASSWORD", "")

# 会话有效期（天）
SESSION_MAX_AGE = int(os.getenv("ICS_ROSTER_SESSION_DAYS", "7")) * 86400
SESSION_COOKIE = "ics_roster_session"
