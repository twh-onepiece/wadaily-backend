#!/usr/bin/env python3
"""
WebSocket話題提案機能のテストスクリプト（既存API内部処理を使用）

既存のHTTP APIと同じ内部処理（profile_analyzer、LangGraph）を使用し、
結果をWebSocketでリアルタイムに受信する.

使い方:
1. サーバーを起動: poetry run uvicorn app.main:app --reload
2. 別のターミナルで実行: poetry run python scripts/test_websocket.py
"""

import asyncio
import json
import httpx
import websockets
from datetime import datetime


async def test_websocket_with_existing_logic():
    """既存のLangGraph処理を使ったWebSocketテスト"""
    
    # 1. セッションを作成
    print("=" * 60)
    print("Step 1: セッションを作成")
    print("=" * 60)
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=120.0) as client:
        response = await client.post(
            "/sessions/",
            json={
                "speaker": {
                    "user_id": "user_A",
                    "sns_data": {
                        "posts": ["キャンプ楽しかった", "新しいテント買った"],
                        "likes": ["アウトドア", "自然"],
                    },
                },
                "listener": {
                    "user_id": "user_B",
                    "sns_data": {
                        "posts": ["登山行ってきた", "山の写真撮影"],
                        "likes": ["山", "写真"],
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
        print(f"共通の興味: {session_data.get('common_interests', [])}")
        print(f"初期提案数: {len(session_data.get('initial_suggestions', []))}")
        print()

    # 2. WebSocket接続
    print("=" * 60)
    print("Step 2: WebSocket接続")
    print("=" * 60)
    
    ws_url = f"ws://localhost:8000/sessions/{session_id}/topics"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"✅ WebSocket接続成功: {ws_url}")
            print()
            
            # 3. 会話更新（新しいconversations形式）
            print("Step 3: 会話更新（conversations形式）")
            print("-" * 60)
            
            # 新しい形式: conversations配列
            message = {
                "conversations": [
                    {
                        "user_id": "user_A",
                        "text": "こんにちは！",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                    },
                    {
                        "user_id": "user_B",
                        "text": "おはよう！週末どうだった？",
                        "timestamp": int(datetime.now().timestamp() * 1000) + 1000,
                    },
                    {
                        "user_id": "user_A",
                        "text": "キャンプに行ってきたよ！",
                        "timestamp": int(datetime.now().timestamp() * 1000) + 2000,
                    },
                ]
            }
            
            print("送信メッセージ:")
            print(json.dumps(message, indent=2, ensure_ascii=False))
            print()
            
            await websocket.send(json.dumps(message))
            print("✅ メッセージ送信完了")
            print()
            
            # 4. レスポンスを受信
            print("Step 4: レスポンス受信")
            print("-" * 60)
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=30)
                response_data = json.loads(response)
                
                print()
                print("✅ 提案受信:")
                print(json.dumps(response_data, indent=2, ensure_ascii=False))
                print()
                print(f"現在のトピック: {response_data.get('current_topic')}")
                print(f"提案数: {len(response_data.get('suggestions', []))}")
                print()
                print("提案内容:")
                for sug in response_data.get("suggestions", []):
                    print(f"  {sug['text']}")
                    print(f"    type: {sug['type']}, score: {sug.get('score')}")
                
            except asyncio.TimeoutError:
                print("⏱️ タイムアウト")
            
            print()
            
            # 5. 追加の会話を送信
            print("=" * 60)
            print("Step 5: 追加の会話を送信")
            print("=" * 60)
            
            additional_message = {
                "conversations": [
                    {
                        "user_id": "user_B",
                        "text": "どこでキャンプしたの？",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                    },
                    {
                        "user_id": "user_A",
                        "text": "山梨の方だよ",
                        "timestamp": int(datetime.now().timestamp() * 1000) + 1000,
                    },
                    {
                        "user_id": "user_B",
                        "text": "いいね！景色良かった？",
                        "timestamp": int(datetime.now().timestamp() * 1000) + 2000,
                    },
                ]
            }
            
            await websocket.send(json.dumps(additional_message))
            print("✅ 追加メッセージ送信完了")
            print()
            
            # レスポンス受信
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=30)
                response_data = json.loads(response)
                
                print()
                print("✅ 追加の提案:")
                for sug in response_data.get("suggestions", []):
                    print(f"  {sug['text']}")
                
            except asyncio.TimeoutError:
                print("⏱️ タイムアウト")
            
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocketエラー: {e}")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("WebSocket話題提案機能テスト")
    print("既存のprofile_analyzer + LangGraphを使用")
    print("=" * 60 + "\n")
    
    asyncio.run(test_websocket_with_existing_logic())
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60 + "\n")
