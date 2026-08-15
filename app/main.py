from fastapi import FastAPI

from app.db import get_connection

app = FastAPI(
    title="LexFlow API",
    version="0.1.0",
    description="API for LexFlow, a workflow management system.",
) 

@app.get("/")
def root():
    return {
        "name": "LexFlow",
        "status": "running"
    }

@app.get("/health")
def health(): 
    try: 
        with get_connection() as conn: 
            with conn.cursor() as cur: 
                cur.execute("SELECT 1")
                cur.fetchone()

        return {"status": "healthy", "database": "connected"}
    except Exception: 
        return {
            "status": "degraded",
            "database": "disconnected",
        }