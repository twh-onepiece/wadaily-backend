#!/usr/bin/env python3
"""
WebSocket close_session機能のテストスクリプト

WebSocketを通じてセッションを明示的に終了する機能をテストします。

使い方:
1. サーバーを起動: poetry run uvicorn app.main:app --reload
2. 別のターミナルで実行: poetry run python scripts/test_websocket_close.py
"""

import asyncio
import json
import httpx
import websockets
from datetime import datetime


async def test_websocket_close_session():
    """WebSocket経由でセッションを終了するテスト"""
    
    print("=" * 60)
    print("WebSocket close_session機能テスト")
    print("=" * 60)
    print()
    
    # 1. セッションを作成
    print("Step 1: セッションを作成")
    print("-" * 60)
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=120.0) as client:
        response = await client.post(
            "/sessions/",
            json={
                "speaker": {
                    "user_id": "user_A",
                    "sns_data": {
                        "posts": ["キャンプ楽しかった"],
                        "likes": ["アウトドア"],
                    },
                },
                "listener": {
                    "user_id": "user_B",
                    "sns_data": {
                        "posts": ["登山行ってきた"],
                        "likes": ["山"],
                    },
                },
            },
        )
        
        if response.status_code != 200:
            print(f"❌ セッション作成失敗: {response.status_code}")
            print(response.text)
            return
        
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"✅ セッション作成成功: {session_id}")
        print()
    
    # 2. WebSocket接続
    print("Step 2: WebSocket接続")
    print("-" * 60)
    
    websocket_url = f"ws://localhost:8000/sessions/{session_id}/topics"
    
    async with websockets.connect(websocket_url) as websocket:
        print(f"✅ WebSocket接続成功: {websocket_url}")
        print()
        
        # 3. 会話を送信
        print("Step 3: 会話を送信")
        print("-" * 60)
        
        conversations_message = {
            "conversations": [
                {
                    "user_id": "user_A",
                    "text": "こんにちは！",
                    "timestamp": int(datetime.now().timestamp() * 1000)
                },
            ]
        }
        
        await websocket.send(json.dumps(conversations_message))
        print("✅ 会話メッセージ送信完了")
        
        # レスポンスを受信
        response = await websocket.recv()
        response_data = json.loads(response)
        print(f"✅ 提案受信: {len(response_data.get('suggestions', []))}件")
        print()
        
        # 4. セッションを終了
        print("Step 4: セッションを終了（close_session）")
        print("-" * 60)
        
        close_message = {
            "action": "close_session"
        }
        
        await websocket.send(json.dumps(close_message))
        print("✅ close_sessionリクエスト送信完了")
        
        # 終了レスポンスを受信
        close_response = await websocket.recv()
        close_data = json.loads(close_response)
        
        print(f"受信レスポンス:")
        print(json.dumps(close_data, indent=2, ensure_ascii=False))
        
        if close_data.get("type") == "session_closed":
            print("✅ セッションが正常に終了しました")
        else:
            print("❌ セッション終了に失敗しました")
        print()
    
    # 5. セッションが削除されたことを確認（削除後は404が返るはず）
    print("Step 5: セッションが削除されたことを確認")
    print("-" * 60)
    
    # 再度WebSocket接続を試みる（失敗するはず）
    try:
        async with websockets.connect(websocket_url) as ws:
            await ws.recv()
            print("❌ セッションがまだ存在しています（削除されていません）")
    except Exception as e:
        print(f"✅ セッションは削除されています（接続エラー: {type(e).__name__}）")
    
    print()
    print("=" * 60)
    print("テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_websocket_close_session())
