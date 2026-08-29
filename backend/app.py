"""Backend API dịch vụ AI Tech News phục vụ ứng dụng frontend và kiểm tra sức khỏe hệ thống."""

import os

import psycopg
from fastapi import FastAPI, HTTPException


app = FastAPI(title="AI Tech News Backend", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    """Endpoint gốc trả về thông tin trạng thái hoạt động của backend service."""
    return {
        "service": "backend",
        "message": "Dịch vụ AI Tech News API đang hoạt động bình thường",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Endpoint kiểm tra tình trạng sức khỏe của ứng dụng (Liveness / Readiness Probe)."""
    return {"status": "ok"}


@app.get("/db-check")
def database_check() -> dict[str, str]:
    """Endpoint kiểm tra kết nối tới cơ sở dữ liệu PostgreSQL."""
    database_url = os.environ["DATABASE_URL"]

    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except psycopg.Error as error:
        raise HTTPException(
            status_code=503, detail="Không thể kết nối đến cơ sở dữ liệu PostgreSQL"
        ) from error

