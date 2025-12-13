from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
import time

from app.config import (
    AGORA_APP_ID,
    AGORA_APP_CERTIFICATE,
    TOKEN_EXPIRATION_IN_SECONDS,
    PRIVILEGE_EXPIRATION_IN_SECONDS,
)

# Agoraのロール定数を直接定義
Role_Publisher = 1
Role_Subscriber = 2

from agora_token_builder import RtcTokenBuilder

router = APIRouter(prefix="/agora", tags=["agora"])


@router.get("/debug/config")
async def debug_config():
    """デバッグ用: 設定値を確認（本番確認後は削除推奨）"""
    return {
        "app_id_exists": bool(AGORA_APP_ID),
        "certificate_exists": bool(AGORA_APP_CERTIFICATE),
        "app_id_length": len(AGORA_APP_ID) if AGORA_APP_ID else 0,
        "certificate_length": (
            len(AGORA_APP_CERTIFICATE) if AGORA_APP_CERTIFICATE else 0
        ),
        "app_id_first_chars": AGORA_APP_ID[:8] + "..." if AGORA_APP_ID else "EMPTY",
        "certificate_first_chars": (
            AGORA_APP_CERTIFICATE[:8] + "..." if AGORA_APP_CERTIFICATE else "EMPTY"
        ),
    }


class TokenResponse(BaseModel):
    """トークンレスポンスモデル"""

    token: str = Field(..., description="生成されたAgoraトークン")
    channel_name: str = Field(..., description="チャンネル名")
    uid: int = Field(..., description="ユーザーID")
    role: str = Field(..., description="ロール")
    expires_in: int = Field(..., description="トークン有効期限（秒）")


@router.get("/token", response_model=TokenResponse)
async def generate_token(
    channel_name: str = Query(..., description="チャンネル名"),
    uid: int = Query(..., description="ユーザーID（0の場合はランダムUID）"),
    role: str = Query(
        default="subscriber", description="ロール（publisher または subscriber）"
    ),
    token_expiration_in_seconds: Optional[int] = Query(
        None, description="トークン有効期限（秒）"
    ),
    privilege_expiration_in_seconds: Optional[int] = Query(
        None, description="権限有効期限（秒）"
    ),
):
    """
    Agoraのアクセストークンを生成する

    クエリパラメータ:
    - **channel_name**: 参加するチャンネル名
    - **uid**: ユーザーID（0の場合はワイルドカード）
    - **role**: ユーザーロール（publisher または subscriber）
    - **token_expiration_in_seconds**: トークンの有効期限（省略時はデフォルト値）
    - **privilege_expiration_in_seconds**: 権限の有効期限（省略時はデフォルト値）
    """

    # 環境変数のチェック
    if not AGORA_APP_ID or not AGORA_APP_CERTIFICATE:
        raise HTTPException(
            status_code=500,
            detail="Agora App IDまたはApp Certificateが設定されていません。環境変数AGORA_APP_IDとAGORA_APP_CERTIFICATEを設定してください。",
        )

    # ロールの設定
    if role.lower() == "publisher":
        agora_role = Role_Publisher
    elif role.lower() == "subscriber":
        agora_role = Role_Subscriber
    else:
        raise HTTPException(
            status_code=400,
            detail="ロールは'publisher'または'subscriber'である必要があります",
        )

    # 有効期限の設定（Unixタイムスタンプ）
    current_timestamp = int(time.time())
    privilege_expire_timestamp = current_timestamp + (
        privilege_expiration_in_seconds or PRIVILEGE_EXPIRATION_IN_SECONDS
    )

    try:
        # トークンの生成
        token = RtcTokenBuilder.buildTokenWithUid(
            AGORA_APP_ID,
            AGORA_APP_CERTIFICATE,
            channel_name,
            uid,
            agora_role,
            privilege_expire_timestamp,
        )

        token_expiration = token_expiration_in_seconds or TOKEN_EXPIRATION_IN_SECONDS

        return TokenResponse(
            token=token,
            channel_name=channel_name,
            uid=uid,
            role=role,
            expires_in=token_expiration,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"トークンの生成に失敗しました: {str(e)}"
        )
