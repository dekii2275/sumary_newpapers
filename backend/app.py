import os

import psycopg
from fastapi import FastAPI, HTTPException


app = FastAPI(title="AI Tech News Backend", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "backend",
        "message": "AI Tech News API is running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/db-check")
def database_check() -> dict[str, str]:
    database_url = os.environ["DATABASE_URL"]

    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
