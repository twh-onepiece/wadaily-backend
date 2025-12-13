import asyncio
import websockets
import json
import os
import uuid
import base64
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from app.config import OPENAI_API_KEY

OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

@dataclass
class TranscriptionSession:
    """各クライアントのセッション情報"""
    session_id: str
    client_ws: WebSocket
    openai_ws: Optional[websockets.WebSocketClientProtocol] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    transcripts: list[str] = field(default_factory=list)

    def __str__(self):
        return f"Session({self.session_id[:8]})"


class SessionManager:
    """複数セッションを管理"""

    def __init__(self):
        self.sessions: dict[str, TranscriptionSession] = {}
        self._lock = asyncio.Lock()

    async def add(self, session: TranscriptionSession):
        async with self._lock:
            self.sessions[session.session_id] = session

    async def remove(self, session_id: str):
        async with self._lock:
            self.sessions.pop(session_id, None)

    def get(self, session_id: str) -> Optional[TranscriptionSession]:
        return self.sessions.get(session_id)

    def get_active_count(self) -> int:
        return len(self.sessions)

    def get_all_sessions(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat(),
                "transcript_count": len(s.transcripts),
            }
            for s in self.sessions.values()
        ]


manager = SessionManager()

router = APIRouter(prefix="/transcript", tags=["transcript"])

@router.websocket("/connect")
async def websocket_transcribe(client_ws: WebSocket):
    """
    WebSocketエンドポイント: クライアントからの音声を受け取り、文字起こし結果を返す

    クライアントは以下の形式でデータを送信:
    - バイナリ: PCM16音声データ (24kHz, mono)
    - JSON: コントロールメッセージ

    サーバーは以下の形式でデータを返信:
    - JSON: OpenAI Realtime APIからのイベント
    """
    await client_ws.accept()

    session_id = str(uuid.uuid4())
    session = TranscriptionSession(session_id=session_id, client_ws=client_ws)
    await manager.add(session)

    print(f"[{session}] Client connected. Active sessions: {manager.get_active_count()}")

    try:
        # OpenAI Realtime APIに接続
        async with websockets.connect(
            OPENAI_WS_URL,
            additional_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            ping_interval=30,
            ping_timeout=10,
        ) as openai_ws:
            session.openai_ws = openai_ws
            print(f"[{session}] OpenAI connected")

            # トランスクリプションセッションの設定
            await send_session_config(session)

            # 双方向の転送を並行実行
            await asyncio.gather(
                forward_client_to_openai(session),
                forward_openai_to_client(session),
            )

    except WebSocketDisconnect:
        print(f"[{session}] Client disconnected")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{session}] OpenAI connection closed: {e}")
    except Exception as e:
        print(f"[{session}] Error: {type(e).__name__}: {e}")
        # エラーをクライアントに通知
        try:
            await client_ws.send_json({
                "type": "error",
                "error": {"message": str(e), "type": type(e).__name__}
            })
        except:
            pass
    finally:
        session.is_active = False
        await manager.remove(session_id)
        print(f"[{session}] Session ended. Active sessions: {manager.get_active_count()}")

async def send_session_config(session: TranscriptionSession):
    """トランスクリプションセッションの設定を送信"""
    config = {
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    },
                    "noise_reduction": {
                        "type": "near_field"
                    },
                    "transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "ja",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    }
                }
            }
        }
    }
    await session.openai_ws.send(json.dumps(config))
    print(f"[{session}] Session config sent")

async def forward_client_to_openai(session: TranscriptionSession):
    """クライアントからの音声データをOpenAIに転送"""
    try:
        while session.is_active:
            try:
                # テキスト（JSON）データを受信
                message = await asyncio.wait_for(
                    session.client_ws.receive(),
                    timeout=60.0  # 60秒のタイムアウト
                )

                if message["type"] == "websocket.disconnect":
                    break

                mtype = message["type"]
                print(f"Received message.({mtype})")

                audio_b64 = ""
                if "text" in message:
                    print("received data in text")
                    audio_b64 = message["text"]
                elif "bytes" in message:
                    print("received data in bytes so convert to base64")
                    audio_b64 = base64.b64encode(message["bytes"]).decode("utf-8")
                else:
                    print("Not found data...")
                    continue

                # Base64エンコードされた音声データ
                event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64,
                }
                await session.openai_ws.send(json.dumps(event))

            except asyncio.TimeoutError:
                # タイムアウトしてもループ継続（キープアライブ）
                continue

    except Exception as e:
        print(f"[{session}] Client->OpenAI error: {e}")


async def forward_openai_to_client(session: TranscriptionSession):
    """OpenAIからのレスポンスをクライアントに転送"""
    try:
        async for message in session.openai_ws:
            if not session.is_active:
                break

            event = json.loads(message)
            event_type = event.get("type", "")
            print(f"Recieved openai event({event_type}) -> {message}")

            # ログ出力とトランスクリプト保存
            if event_type == "transcription_session.created":
                print(f"[{session}] Transcription session created")

            # elif event_type == "conversation.item.input_audio_transcription.delta":
            #     delta = event.get("delta", "")
            #     if delta:
            #         print(f"[{session}] Delta: {delta}")

            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                if transcript:
                    session.transcripts.append(transcript)
                    print(f"[{session}] Completed: {transcript}")
                    # クライアントに転送
                    await session.client_ws.send_text(transcript)

            elif event_type == "error":
                error = event.get("error", {})
                print(f"[{session}] OpenAI Error: {error}")

    except websockets.exceptions.ConnectionClosed:
        print(f"[{session}] OpenAI disconnected")
    except Exception as e:
        print(f"[{session}] OpenAI->Client error: {e}")
