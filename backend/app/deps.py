"""公共依赖：当前登录用户。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import SESSION_COOKIE
from .db import get_db
from .models import User
from .services.auth import parse_session


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = parse_session(request.cookies.get(SESSION_COOKIE))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Cookie"},
        )
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user
