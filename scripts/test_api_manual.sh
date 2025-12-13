#!/bin/bash
# セッションAPIの手動テストスクリプト
# 
# 使い方:
#   1. アプリケーションを起動: make up または poetry run uvicorn app.main:app --reload
#   2. 別ターミナルでこのスクリプトを実行: bash scripts/test_api_manual.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== WadailyAPI Manual Test ==="
echo "Base URL: $BASE_URL"
echo ""

# カラー出力
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# jqの有無をチェック
if command -v jq &> /dev/null; then
    HAS_JQ=true
else
    HAS_JQ=false
    echo -e "${BLUE}Note: jq is not installed. JSON output will not be formatted.${NC}"
    echo -e "${BLUE}Install with: brew install jq (macOS) or apt install jq (Linux)${NC}"
    echo ""
fi

# JSONをフォーマット表示する関数
format_json() {
    if [ "$HAS_JQ" = true ]; then
        echo "$1" | jq '.'
    else
        echo "$1" | python3 -m json.tool 2>/dev/null || echo "$1"
    fi
}

# JSONから値を抽出する関数
extract_json_value() {
    local json="$1"
    local key="$2"
    
    if [ "$HAS_JQ" = true ]; then
        echo "$json" | jq -r ".$key"
    else
        # Python を使ってJSONをパース
        echo "$json" | python3 -c "import sys, json; print(json.load(sys.stdin).get('$key', ''))" 2>/dev/null || echo ""
    fi
}

# 1. セッション作成
echo -e "${BLUE}[1/3] セッションを作成中...${NC}"
CREATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/sessions/" \
  -H "Content-Type: application/json" \
  -d '{
    "speaker": {
      "user_id": "user1",
      "sns_data": {
        "posts": ["キャンプ楽しかった", "新しいMacBook Pro買った"],
        "likes": ["アウトドア", "Apple", "テクノロジー"]
      }
    },
    "listener": {
      "user_id": "user2",
      "sns_data": {
        "posts": ["登山行ってきた", "AI勉強中"],
        "likes": ["自然", "プログラミング"]
      }
    }
  }')

format_json "$CREATE_RESPONSE"

# セッションIDを抽出
SESSION_ID=$(extract_json_value "$CREATE_RESPONSE" "session_id")

if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
  echo -e "${RED}エラー: セッションIDを取得できませんでした${NC}"
  exit 1
fi

echo -e "${GREEN}✓ セッション作成成功: $SESSION_ID${NC}"
echo ""

# 2. 会話を更新（テキスト入力）
echo -e "${BLUE}[2/3] 会話を更新中（テキスト入力）...${NC}"

# 現在時刻をミリ秒単位のUnix timestampに変換
TIMESTAMP=$(python3 -c "import time; print(int(time.time() * 1000))")

UPDATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/sessions/${SESSION_ID}/transcript" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"transcript_update\",
    \"payload\": {
      \"input_type\": \"text\",
      \"transcript\": [
        {
          \"speaker\": \"user1\",
          \"text\": \"こんにちは！最近何してた？\",
          \"timestamp\": $TIMESTAMP
        },
        {
          \"speaker\": \"user2\",
          \"text\": \"最近キャンプに行ってきたよ\",
          \"timestamp\": $((TIMESTAMP + 30000))
        }
      ]
    }
  }")

format_json "$UPDATE_RESPONSE"
echo -e "${GREEN}✓ 会話更新成功（テキスト）${NC}"
echo ""

# 3. 会話を更新（沈黙）
echo -e "${BLUE}[3/3] 会話を更新中（沈黙検知）...${NC}"
SILENCE_RESPONSE=$(curl -s -X POST "${BASE_URL}/sessions/${SESSION_ID}/transcript" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "silence",
    "payload": {
      "input_type": "silence",
      "duration_seconds": 5.0
    }
  }')

format_json "$SILENCE_RESPONSE"
echo -e "${GREEN}✓ 会話更新成功（沈黙）${NC}"
echo ""

echo -e "${GREEN}=== すべてのテスト完了 ===${NC}"
echo ""
echo "セッションID: $SESSION_ID"
echo ""
echo "次のステップ:"
echo "  - Redisに保存されたデータを確認: docker exec -it my-redis redis-cli"
echo "  - セッションデータを取得: KEYS session:*"
echo "  - データの中身を確認: GET session:$SESSION_ID"
