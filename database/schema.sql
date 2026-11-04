-- 参考 DDL（SQLite）
-- 实际建表由 backend/app/db.py 的 Base.metadata.create_all 完成，
-- 本文件用于人工查阅表结构或迁移到 MySQL / PostgreSQL。

CREATE TABLE IF NOT EXISTS person (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       VARCHAR(64)  NOT NULL,
    color      VARCHAR(16)  NOT NULL DEFAULT '#4f8cff',
    group_name VARCHAR(64)  NOT NULL DEFAULT '',
    active     BOOLEAN      NOT NULL DEFAULT 1,
    feed_token VARCHAR(64)  NOT NULL UNIQUE,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_person_name ON person (name);

CREATE TABLE IF NOT EXISTS shift_type (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             VARCHAR(32) NOT NULL UNIQUE,
    name             VARCHAR(32) NOT NULL,
    start_time       VARCHAR(5)  NOT NULL DEFAULT '',
    end_time         VARCHAR(5)  NOT NULL DEFAULT '',
    ends_next_day    BOOLEAN     NOT NULL DEFAULT 0,
    emit_to_calendar BOOLEAN     NOT NULL DEFAULT 1,
    color            VARCHAR(16) NOT NULL DEFAULT '#4f8cff'
);

CREATE TABLE IF NOT EXISTS shift (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER NOT NULL REFERENCES person (id) ON DELETE CASCADE,
    shift_type_id INTEGER NOT NULL REFERENCES shift_type (id),
    work_date     DATE    NOT NULL,
    note          VARCHAR(255) NOT NULL DEFAULT '',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_shift_person_date UNIQUE (person_id, work_date)
);
CREATE INDEX IF NOT EXISTS ix_shift_person_id ON shift (person_id);
CREATE INDEX IF NOT EXISTS ix_shift_work_date ON shift (work_date);

-- 默认班次类型（与 backend/app/seed.py 保持一致）
INSERT OR IGNORE INTO shift_type (code, name, start_time, end_time, ends_next_day, emit_to_calendar, color)
VALUES
    ('morning', '早班', '09:00', '17:00', 0, 1, '#f5a524'),
    ('evening', '晚班', '17:00', '00:00', 1, 1, '#7c5cff'),
    ('rest',    '休息', '',      '',      0, 0, '#94a3b8');

CREATE TABLE IF NOT EXISTS user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(64) NOT NULL DEFAULT '',
    role          VARCHAR(16) NOT NULL DEFAULT 'admin',
    active        BOOLEAN     NOT NULL DEFAULT 1,
    created_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME
);
CREATE INDEX IF NOT EXISTS ix_user_username ON user (username);
