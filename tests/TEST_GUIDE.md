# テスト方法

このドキュメントでは、`create_session` と `update_transcript` API のテスト方法を説明します。

## 前提条件

### 1. Redisの起動

```bash
# Redisコンテナを起動
docker run --name my-redis -p 6379:6379 -d redis

# 既に起動している場合
docker start my-redis

# 確認
docker ps | grep redis
```

### 2. 環境変数の設定

```bash
# .envファイルを作成（プロジェクトルートに）
cat > .env << EOF
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL_ID=gpt-4o-mini
OPENAI_EMBEDDING_MODEL_ID=text-embedding-3-small
REDIS_HOST=localhost
REDIS_PORT=6379
EOF
```

## テスト方法

### 方法1: ユニットテスト（推奨）

モックを使用するため、OpenAI APIキーは不要です。

```bash
# 依存関係をインストール
poetry install

# テストを実行
poetry run pytest tests/test_sessions_api.py -v

# または Makefileを使用
make test
```

**出力例:**
```
tests/test_sessions_api.py::test_create_session PASSED
tests/test_sessions_api.py::test_update_transcript PASSED
tests/test_sessions_api.py::test_update_transcript_session_not_found PASSED
```

### 方法2: 手動テスト（実際のAPIを叩く）

実際のOpenAI APIを呼び出します（APIキー必須）。

#### 2-1. アプリケーションを起動

**ターミナル1:**
```bash
# Poetry環境で起動
poetry run uvicorn app.main:app --reload --port 8000

# または Dockerで起動
make up
```

**起動確認:**
```bash
curl http://localhost:8000/
# {"message":"Wadaily API"} が返ればOK
```

#### 2-2. テストスクリプトを実行

**ターミナル2:**
```bash
# 手動テストスクリプトを実行
bash scripts/test_api_manual.sh
```

**出力例:**
```
=== WadailyAPI Manual Test ===
Base URL: http://localhost:8000

[1/3] セッションを作成中...
{
  "session_id": "abc123...",
  "status": "initialized",
  "common_interests": ["アウトドア", "キャンプ", "登山", "テクノロジー", "AI"],
  "initial_suggestions": [...]
}
✓ セッション作成成功: abc123...

[2/3] 会話を更新中（テキスト入力）...
{
  "status": "active",
  "current_topic": "アウトドア",
  "suggestions": [...]
}
✓ 会話更新成功（テキスト）

[3/3] 会話を更新中（沈黙検知）...
✓ 会話更新成功（沈黙）

=== すべてのテスト完了 ===
```

### 方法3: curlで個別にテスト

#### セッション作成
```bash
curl -X POST http://localhost:8000/sessions/ \
  -H "Content-Type: application/json" \
  -d '{
    "users": [
      {
        "user_id": "user1",
        "sns_data": {
          "posts": ["キャンプ楽しかった"],
          "likes": ["アウトドア"]
        }
      },
      {
        "user_id": "user2",
        "sns_data": {
          "posts": ["登山行ってきた"],
          "likes": ["自然"]
        }
      }
    ]
  }' | jq '.'
```

#### 会話更新
```bash
# セッションIDを環境変数にセット
SESSION_ID="取得したセッションID"

# 現在時刻をミリ秒単位のUnix timestampに変換
TIMESTAMP=$(python3 -c "import time; print(int(time.time() * 1000))")

curl -X POST "http://localhost:8000/sessions/${SESSION_ID}/transcript" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"transcript_update\",
    \"payload\": {
      \"input_type\": \"text\",
      \"transcript\": [
        {
          \"speaker\": \"user1\",
          \"text\": \"こんにちは！\",
          \"timestamp\": $TIMESTAMP
        }
      ]
    }
  }" | python3 -m json.tool
```

### 方法4: Swagger UI（インタラクティブ）

ブラウザで http://localhost:8000/docs にアクセスして、GUIからテストできます。

1. `/sessions/` の "Try it out" をクリック
2. リクエストボディを編集
3. "Execute" をクリック
4. レスポンスを確認

## デバッグ方法

### Redisのデータを確認

```bash
# Redisコンテナに接続
docker exec -it my-redis redis-cli

# セッション一覧を確認（プレフィックスなし）
KEYS *

# 特定のセッションを確認
GET 3b95ffa5-1143-4651-9613-97c813e0ab94

# すべてのセッションを削除（リセット）
FLUSHDB
```

**注意**: セッションIDは `session:` プレフィックスなしで保存されています。

### ログを確認

```bash
# Dockerの場合
docker compose logs -f api

# Poetryの場合（ターミナルに直接出力される）
# uvicornの起動ログを確認
```

### エラーが出た場合

1. **404 Session not found**
   - セッションIDが正しいか確認
   - Redisが起動しているか確認: `docker ps | grep redis`

2. **500 Profile analysis failed**
   - OpenAI APIキーが設定されているか確認
   - APIキーが有効か確認

3. **Connection refused (Redis)**
   - Redisが起動しているか確認: `docker start my-redis`
   - ポートが正しいか確認（デフォルト: 6379）

## テストデータ例

### 最小限のリクエスト
```json
{
  "users": [
    {
      "user_id": "user1",
      "sns_data": {
        "posts": [],
        "likes": []
      }
    }
  ]
}
```

### 豊富なデータ
```json
{
  "users": [
    {
      "user_id": "alice",
      "sns_data": {
        "posts": [
          "週末は富士山に登ってきました",
          "新しいテントを買った",
          "キャンプ料理にハマってます"
        ],
        "likes": ["アウトドア", "登山", "キャンプ", "自然"]
      }
    },
    {
      "user_id": "bob",
      "sns_data": {
        "posts": [
          "Rustで書いたコードが動いた",
          "LLMアプリ開発中",
          "ChatGPT API使ってみた"
        ],
        "likes": ["プログラミング", "AI", "機械学習", "Rust"]
      }
    }
  ]
}
```

## CI/CD環境でのテスト

GitHub Actionsなどで自動テストする場合:

```yaml
# .github/workflows/test.yml の例
- name: Start Redis
  run: docker run --name redis -d -p 6379:6379 redis

- name: Run tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: poetry run pytest -v
```

## 次のステップ

- [ ] e2eテストの追加（複数ラウンドの会話）
- [ ] パフォーマンステスト（負荷テスト）
- [ ] LLM応答のバリデーションテスト
- [ ] エラーハンドリングのテスト強化
