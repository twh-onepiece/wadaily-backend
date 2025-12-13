# WebSocket話題提案機能

## 概要

既存のHTTP APIと同じ内部処理（profile_analyzer + LangGraph）を使用し、結果をWebSocketでリアルタイムにストリーミング配信する機能です。

## 主な特徴

- **既存APIとの互換性**: profile_analyzerとLangGraphの処理ロジックをそのまま使用
- **リアルタイムストリーミング**: 処理の進捗と最終結果をリアルタイムに受信
- **双方向通信**: 会話データの送信と提案の受信を同じ接続で実行
- **セッション永続化**: Redisへの保存も既存APIと同様に実行

## エンドポイント

```
ws://localhost:8000/sessions/{session_id}/topics
```

## 使用フロー

1. **セッション作成**: `POST /sessions/` でセッションを作成（既存API）
2. **WebSocket接続**: `ws://localhost:8000/sessions/{session_id}/topics` に接続
3. **会話送信**: conversationsフォーマットで送信
4. **リアルタイム受信**: 提案結果を受信
5. **セッション終了**: 
   - 明示的終了: `{"action": "close_session"}` を送信
   - 自動終了: WebSocket接続を閉じる（設定により自動削除）

## メッセージフォーマット

### クライアント → サーバー（会話送信）

```json
{
  "conversations": [
    {
      "user_id": "A",
      "text": "こんにちは！",
      "timestamp": 1702454400000
    },
    {
      "user_id": "B",
      "text": "元気？",
      "timestamp": 1702454405000
    }
  ]
}
```

### クライアント → サーバー（セッション終了）

```json
{
  "action": "close_session"
}
```

**説明**: セッションを明示的に終了し、Redisからデータを削除します。正常に終了すると、セッションは完全に削除されます。

**フィールド説明**:
- `user_id` (string): 発話者のユーザーID
- `text` (string): 発話内容
- `timestamp` (int): Unix timestamp（ミリ秒）

### サーバー → クライアント（提案結果）

```json
{
  "status": "active",
  "current_topic": "アウトドア",
  "suggestions": [
    {
      "id": 1,
      "text": "最近キャンプに行かれましたか？",
      "type": "topic_shift",
      "score": 0.85
    },
    {
      "id": 2,
      "text": "登山の魅力について詳しく聞かせてください",
      "type": "deep_dive",
      "score": 0.78
    }
  ]
}
```

**フィールド説明**:
- `status` (string): セッションステータス（"active"）
- `current_topic` (string): 現在のトピック
- `suggestions` (array): 提案リスト
  - `id` (int): 提案ID
  - `text` (string): 提案内容
  - `type` (string): 提案タイプ（"deep_dive" | "topic_shift" | "silence_break"）
  - `score` (float): スコア
```

### エラーレスポンス

```json
{
  "type": "error",
  "error": "Session not found",
  "session_id": "invalid-session-id"
}
```

### セッション終了レスポンス

```json
{
  "type": "session_closed",
  "session_id": "uuid-of-session",
  "message": "Session successfully closed and deleted"
}
```

**説明**: `close_session`アクションが成功すると、このレスポンスが返され、その後WebSocket接続が正常に閉じられます。

## クライアント実装例

### JavaScript/TypeScript

```typescript
class RealTimeTopicSuggestionClient {
  private ws: WebSocket;
  
  async createSession(users) {
    // セッション作成（既存APIと同じ）
    const response = await fetch('http://localhost:8000/sessions/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ users }),
    });
    const data = await response.json();
    
    // WebSocket接続
    this.ws = new WebSocket(`ws://localhost:8000/sessions/${data.session_id}/topics`);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.onReceivedSuggestions(data);
    };
  }
  
  sendConversations(conversations: ConversationMessage[]) {
    // conversations形式で送信
    this.ws.send(JSON.stringify({
      conversations: conversations
    }));
  }
  
  onReceivedSuggestions(data) {
    console.log('Current topic:', data.current_topic);
    console.log('Suggestions:', data.suggestions);
    // UIに提案を表示
  }
  
  closeSession() {
    this.ws.close();
  }
}

// 使用例
const client = new RealTimeTopicSuggestionClient();
await client.createSession([...]);

client.sendConversations([
  { user_id: 'A', text: 'こんにちは', timestamp: Date.now() },
  { user_id: 'B', text: '元気？', timestamp: Date.now() + 1000 },
]);
```

### Python

```python
import asyncio
import json
import websockets

async def realtime_topic_client(session_id):
    uri = f"ws://localhost:8000/sessions/{session_id}/topics"
    
    async with websockets.connect(uri) as websocket:
        # 会話を送信
        message = {
            "conversations": [
                {"user_id": "A", "text": "こんにちは", "timestamp": 1702454400000},
                {"user_id": "B", "text": "元気？", "timestamp": 1702454405000},
            ]
        }
        await websocket.send(json.dumps(message))
        
        # 結果を受信
        response = await websocket.recv()
        data = json.loads(response)
        print("Suggestions:", data["suggestions"])

asyncio.run(realtime_topic_client("your-session-id"))
```

## テスト方法

### 1. サーバー起動

```bash
poetry run uvicorn app.main:app --reload
```

### 2. Pythonテストスクリプト実行

```bash
poetry run python scripts/test_websocket.py
```

### 3. 手動テスト（wscat使用）

```bash
# インストール
npm install -g wscat

# セッション作成
SESSION_ID=$(curl -X POST http://localhost:8000/sessions/ \
  -H "Content-Type: application/json" \
  -d '{"users": [{"user_id": "A", "sns_data": {"posts": [], "likes": []}}]}' \
  | jq -r '.session_id')

# WebSocket接続
wscat -c ws://localhost:8000/sessions/$SESSION_ID/topics

# メッセージ送信（接続後に入力）
{"conversations": [{"user_id": "A", "text": "こんにちは", "timestamp": "2025-12-13T10:00:00Z"}, {"user_id": "B", "text": "元気？", "timestamp": "2025-12-13T10:00:05Z"}, {"user_id": "A", "text": "元気だよ", "timestamp": "2025-12-13T10:00:10Z"}, {"user_id": "B", "text": "よかった", "timestamp": "2025-12-13T10:00:15Z"}, {"user_id": "A", "text": "週末どうだった？", "timestamp": "2025-12-13T10:00:20Z"}]}
```

## 技術仕様

- **プロトコル**: WebSocket (RFC 6455)
- **内部処理**: 
  - profile_analyzer（初回セッション作成時）
  - LangGraph workflow（会話更新時）
  - Redis永続化（session_store）
- **AI モデル**: 
  - GPT-4o-mini（profile_analyzer、LangGraph内）
  - text-embedding-3-small（ベクトル化）
- **ストリーミング**: `graph.astream()` による中間結果配信
- **タイムアウト**: LLM呼び出しは30秒（デフォルト）
- **エラーハンドリング**: 既存APIと同じフォールバック

## HTTP APIとの比較

| 項目 | HTTP API | WebSocket API |
|------|----------|---------------|
| エンドポイント | `POST /sessions/{id}/transcript` | `ws://*/sessions/{id}/topics` |
| リクエスト形式 | 同じ（TranscriptUpdateRequest） | 同じ |
| レスポンス形式 | 同じ（TranscriptUpdateResponse） | 同じ + 進捗通知 |
| 内部処理 | profile_analyzer + LangGraph | 同じ |
| Redis保存 | あり | あり |
| リアルタイム性 | なし（完了待ち） | あり（ストリーミング） |
| 接続維持 | なし | あり |

## メリット

1. **既存ロジックの再利用**: HTTP APIと完全に同じ処理を使用
2. **リアルタイム体験**: 処理の進捗をリアルタイムで確認可能
3. **接続効率**: 1つの接続で複数回のやりとりが可能
4. **段階的移行**: HTTP APIとWebSocket APIを並行運用可能

## セキュリティ

- セッションIDの検証
- 無効なセッションは接続拒否（WebSocket close code 1008）
- JSON パースエラーのハンドリング
- 話題数の制限（最大3つ）

## パフォーマンス

- 非同期処理による高速レスポンス
- LangGraphのストリーミング実行（`astream()`）
- 進捗の可視化によるUX向上
- WebSocket接続の維持でオーバーヘッド削減

## 実装の内部詳細

### 処理フロー

1. **WebSocket接続確立**
   - セッションIDの検証
   - Redis からセッションデータ読み込み

2. **メッセージ受信**
   - TranscriptUpdateRequest形式でパース
   - 会話履歴を永続化（conversation_history）
   - 直近5件をhistory_windowとして使用

3. **LangGraph実行**
   - `get_initial_state()` で初期状態を構築
   - `graph.astream()` でストリーミング実行
   - 各ノードの処理結果を進捗として送信

4. **結果送信**
   - final_suggestionsを抽出
   - TranscriptUpdateResponse形式で送信
   - Redisに状態を保存

5. **エラーハンドリング**
   - TimeoutError: タイムアウトエラーを返す
   - Exception: 内部エラーを返す
   - WebSocketDisconnect: ログ記録のみ

### 使用している既存コンポーネント

- `SessionStore`: Redis永続化
- `profile_analyzer`: プロファイル分析（セッション作成時）
- `get_graph_app()`: LangGraphインスタンス取得
- `get_initial_state()`: 初期状態構築
- `REQUEST_TYPE_MAP`: リクエストタイプマッピング

## 今後の拡張予定

- [ ] 認証・認可機能の追加
- [ ] 複数セッションの同時接続管理
- [ ] メッセージキューイング（接続断時のバッファリング）
- [ ] レート制限の実装
- [ ] メトリクス収集（処理時間、成功率など）
