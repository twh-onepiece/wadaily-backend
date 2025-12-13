from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import agora, sessions

app = FastAPI(title="Wadaily", description="Wadaily API Service", version="0.1.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切に設定してください
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーターの登録
app.include_router(agora.router)
app.include_router(sessions.router)


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "Welcome to Wadaily API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """ヘルスチェック用エンドポイント"""
    return {"status": "healthy", "service": "wadaily-api"}
