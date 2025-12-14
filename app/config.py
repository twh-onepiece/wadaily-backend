import os
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# Agora設定
AGORA_APP_ID = os.getenv("AGORA_APP_ID")
AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE")

# トークン有効期限（秒）
TOKEN_EXPIRATION_IN_SECONDS = 3600
PRIVILEGE_EXPIRATION_IN_SECONDS = 3600

# OPENAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE_URL = "https://api.openai.com/v1"
# OPENAI_MODEL_ID= "gpt-4o-mini"
# OPENAI_EMBEDDING_MODEL_ID = "text-embedding-3-small"
OPENAI_MODEL_ID= "Qwen3-Coder-480B-A35B-Instruct-FP8"
OPENAI_EMBEDDING_MODEL_ID = "multilingual-e5-large"
SAKURANOAI_API_KEY = os.getenv("SAKURANOAI_API_KEY")
SAKURANOAI_API_BASE_URL = "https://api.ai.sakura.ad.jp/v1"

# システム設定
LOG_LEVEL = "INFO"

# セッション管理設定
# WebSocket切断時に自動的にセッションを削除するかどうか（デフォルトはTrue: 削除する）
AUTO_DELETE_SESSION_ON_DISCONNECT = True
