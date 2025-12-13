# app/schemas/session.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional


# --- Shared Components ---
class SnsData(BaseModel):
    """SNSから取得したユーザーデータモデル.

    分析フェーズで使用される投稿内容やいいね履歴を保持.
    Cold Start（データなし）に対応するため、空リストを許容.

    Attributes:
        posts (List[str]): 興味分析の対象となる、ユーザーの直近の投稿テキスト群.
            (例: ["キャンプ楽しかった", "新しいMacBook Pro買った"])
            データがない場合は空リストとして扱われ、汎用的な話題（天気・ニュース等）が優先される.
        likes (List[str]): ユーザーが「いいね」した対象のキーワードやカテゴリ名.
            (例: ["アウトドア", "Apple", "映画"])
            共通点探しのヒントとして使用される.データがない場合は空リスト.
    """

    posts: List[str] = Field(
        default_factory=list,
        description="ユーザーの投稿内容.データがない場合は空リスト可（汎用的な話題を提案）.",
    )
    likes: List[str] = Field(
        default_factory=list,
        description="ユーザーのいいね履歴.データがない場合は空リスト可.",
    )


class User(BaseModel):
    """セッションに参加するユーザー情報モデル.

    Attributes:
        user_id (str): ユーザーを一意に識別するID.
        sns_data (SnsData): ユーザーに関連付けられたSNSデータ.
    """

    user_id: str
    sns_data: SnsData


class SuggestionResponse(BaseModel):
    """AIによって生成された会話提案モデル.

    WebSocketとHTTP APIの両方で使用される統一モデル.
    speaker/listenerはstate（セッション作成時）で決定されているため、
    提案レスポンスには含めない.

    Attributes:
        id (int): 提案の一意なID.
        text (str): 提案される具体的な発話内容や質問.
        type (Literal["deep_dive", "topic_shift", "silence_break"]): 提案の種類.
        score (Optional[float]): 提案の自信度や適切さを示すスコア.
    """

    id: int
    text: str
    type: Literal["deep_dive", "topic_shift", "silence_break"]
    score: Optional[float] = None


# --- POST /sessions (Init) ---
class CreateSessionRequest(BaseModel):
    """セッション作成APIのリクエストボディ定義.

    Attributes:
        speaker (User): 提案を受けて発話する側のユーザー（主役）.
        listener (User): 提案を聞く側のユーザー.
    """
    speaker: User
    listener: User


class CreateSessionResponse(BaseModel):
    """セッション作成APIのレスポンス定義.

    初期分析の結果と、最初の話題提案を含む.

    Attributes:
        session_id (str): 発行されたセッションID.
        status (str): セッションの状態（例: "initialized"）.
        common_interests (List[str]): 参加者間で共通する興味カテゴリ.
        initial_suggestions (List[SuggestionResponse]): 会話開始のための初期提案リスト.
    """

    session_id: str
    status: str
    common_interests: List[str]
    initial_suggestions: List[SuggestionResponse]


# --- WebSocket ---
class ConversationMessage(BaseModel):
    """WebSocketで送信される会話メッセージ.

    Attributes:
        user_id (str): 発話者のユーザーID.
        text (str): 発話内容.
        timestamp (int): 発話時刻（Unix timestamp ミリ秒）.
    """

    user_id: str
    text: str
    timestamp: int


class WebSocketConversationsRequest(BaseModel):
    """WebSocketで送信される会話リクエスト.

    Attributes:
        conversations (List[ConversationMessage]): 会話メッセージのリスト.
    """

    conversations: List[ConversationMessage]


# --- DELETE /sessions/{session_id} ---
class DeleteSessionResponse(BaseModel):
    """セッション削除APIのレスポンス定義.

    Attributes:
        session_id (str): 削除されたセッションID.
        deleted (bool): 削除が成功したかどうか.
        message (str): 削除結果のメッセージ.
    """

    session_id: str
    deleted: bool
    message: str
