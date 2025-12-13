# WadailyAPI

wadailyのbackendリポジトリ。会話データとsnsから適切な話題を提案する

## 技術スタック

- **Python**: 3.11
- **Webフレームワーク**: FastAPI
- **パッケージ管理**: Poetry
- **コンテナ**: Docker / Docker Compose
- **データバリデーション**: Pydantic
- **Webサーバー**: Uvicorn + Gunicorn

## プロジェクト構成

```
WadailyAPI/
├── app/
│   └── main.py          # FastAPIアプリケーションのエントリーポイント
├── compose.yml          # Docker Compose設定
├── Dockerfile.local     # ローカル開発用Dockerfile
├── entrypoint.sh        # コンテナ起動スクリプト
├── pyproject.toml       # Poetry依存関係管理
└── README.md            # このファイル
```

## クイックスタート

### Makefileを使う方法 (推奨)

```bash
# ヘルプを表示
make help

# Dockerで起動
make up

# Dockerをバックグラウンドで起動
make up-d
```

## セットアップ

### Poetryを使った開発環境のセットアップ

1. **Poetryのインストール** (未インストールの場合)
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **依存関係のインストール**
   ```bash
   poetry install
   ```

3. **仮想環境の有効化**
   ```bash
   poetry shell
   ```

4. **アプリケーションの起動**
   ```bash
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Poetryの主な使い方

- **パッケージの追加**
  ```bash
  poetry add パッケージ名
  ```

- **開発用パッケージの追加**
  ```bash
  poetry add --group dev パッケージ名
  ```

- **パッケージの削除**
  ```bash
  poetry remove パッケージ名
  ```

- **依存関係の更新**
  ```bash
  poetry update
  ```

- **仮想環境内でコマンド実行**
  ```bash
  poetry run コマンド
  ```

## Dockerでの起動方法

### 1. コンテナのビルドと起動

```bash
docker compose up --build
```

### 2. バックグラウンドで起動

```bash
docker compose up -d
```

### 3. コンテナの停止

```bash
docker compose down
```

### 4. ログの確認

```bash
docker compose logs -f api
```

### 5. コンテナ内でコマンド実行

```bash
docker compose exec api bash
```

### コードフォーマット・リント

```bash
# フォーマット
poetry run black .

# リント
poetry run ruff check .
```

## Makefileコマンド一覧

| コマンド | 説明 |
|---------|------|
| `make help` | 利用可能なコマンドを表示 |
| `make install` | Poetry依存関係をインストール |
| `make up` | Dockerコンテナをビルドして起動 |
| `make up-d` | Dockerコンテナをバックグラウンドで起動 |
| `make down` | Dockerコンテナを停止 |
| `make logs` | Dockerログを表示 |
| `make exec` | Dockerコンテナ内に入る |
| `make test` | テストを実行 |
| `make clean` | キャッシュファイルを削除 |*APIドキュメント (ReDoc)**: http://localhost:8000/redoc

## 開発

### API エンドポイント

#### セッション管理

1. **POST /sessions/** - セッション作成
   - speaker/listenerのSNSデータを基に新しいセッションを作成
   - 共通の興味と初期提案を返す

2. **WebSocket /sessions/{session_id}/topics** - リアルタイム会話更新
   - 会話データを送信し、提案をリアルタイムで受信
   - 接続を切断するまで継続的に会話を更新可能

3. **DELETE /sessions/{session_id}** - セッション削除
   - セッションを終了し、Redisから関連データを削除
   - 使用例:
     ```bash
     curl -X DELETE http://localhost:8000/sessions/{session_id}
     ```

#### セッション自動削除設定

WebSocket切断時の自動削除は環境変数で制御可能:
```bash
# .envファイルまたは環境変数で設定
AUTO_DELETE_SESSION_ON_DISCONNECT=true  # WebSocket切断時に自動削除（デフォルト: false）
```

### テストの実行

```bash
poetry run pytest
```

### コードフォーマット・リント

```bash
# フォーマット
poetry run black .

# リント
poetry run ruff check .
```
