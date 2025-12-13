import json
import os
import logging
from typing import Dict, Any, Optional
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# 環境変数からRedisのURLを取得（デフォルトはローカル）
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class SessionStore:
    """
    セッションデータ（プロファイルや会話履歴）をRedisに保存・取得するクラス
    """

    # Redisクライアントの初期化
    _client = redis.from_url(REDIS_URL, decode_responses=True)

    # データの有効期限（例: 24時間 = 86400秒）
    EXPIRATION_SECONDS = 86400

    @classmethod
    async def save_session(cls, session_id: str, data: Dict[str, Any]):
        """
        セッションIDをキーにして、データをJSON形式でRedisに保存する
        """
        try:
            # 辞書(dict)をJSON文字列に変換
            json_str = json.dumps(data, ensure_ascii=False)

            # Redisに保存 (ex=有効期限)
            await cls._client.set(session_id, json_str, ex=cls.EXPIRATION_SECONDS)
            logger.info(f"Session {session_id} saved to Redis.")

        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            raise e

    @classmethod
    async def load_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Redisからデータを取得し、辞書に戻して返す
        """
        try:
            json_str = await cls._client.get(session_id)
            if not json_str:
                return None

            # JSON文字列を辞書(dict)に戻す
            return json.loads(json_str)

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    @classmethod
    async def delete_session(cls, session_id: str) -> bool:
        """
        Redisからセッションデータを削除する
        
        Args:
            session_id: 削除するセッションID
            
        Returns:
            bool: 削除に成功した場合True、失敗した場合False
        """
        try:
            result = await cls._client.delete(session_id)
            if result > 0:
                logger.info(f"Session {session_id} deleted from Redis.")
                return True
            else:
                logger.warning(f"Session {session_id} not found in Redis.")
                return False

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
