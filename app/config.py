import os
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# Agora設定
AGORA_APP_ID = os.getenv("AGORA_APP_ID")
AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE")

# トークン有効期限（秒）
TOKEN_EXPIRATION_IN_SECONDS = int(os.getenv("TOKEN_EXPIRATION_IN_SECONDS", "3600"))
PRIVILEGE_EXPIRATION_IN_SECONDS = int(
    os.getenv("PRIVILEGE_EXPIRATION_IN_SECONDS", "3600")
)

# OPENAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL_ID = os.getenv("OPENAI_EMBEDDING_MODEL_ID", "text-embedding-3-small")

# システム設定
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# セッション管理設定
# WebSocket切断時に自動的にセッションを削除するかどうか（デフォルトはTrue: 削除する）
AUTO_DELETE_SESSION_ON_DISCONNECT = os.getenv("AUTO_DELETE_SESSION_ON_DISCONNECT", "true").lower() == "true"
