#!/bin/bash
set -e

echo "Starting Wadaily API..."

# Cloud RunのPORT環境変数を使用（デフォルトは8080）
PORT=${PORT:-8080}

# Gunicornでアプリケーションを起動
# - gunicorn: プロセスマネージャー
# - uvicorn.workers.UvicornWorker: ASGIワーカー（非同期処理）
# - app.main:app: アプリケーションのパス
# - --workers 1: Cloud Runではワーカー数は1が推奨（1コンテナ=1リクエスト処理）
# - --worker-class: ワーカークラス
# - --bind: バインドするアドレス（Cloud RunのPORT環境変数を使用）
# - --access-logfile: アクセスログの出力先
# - --error-logfile: エラーログの出力先

exec gunicorn app.main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --access-logfile - \
    --error-logfile - \
    --log-level info
