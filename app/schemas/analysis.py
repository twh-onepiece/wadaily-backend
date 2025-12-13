from pydantic import BaseModel, Field
from typing import List, Literal


class InterestCluster(BaseModel):
    """一つの興味分野を表すデータモデル."""

    category: str = Field(
        ..., description="興味の大分類 (例: 技術, アニメ, アウトドア)"
    )
    topics: List[str] = Field(
        ..., description="具体的なトピック (例: Python, キャンプ道具)"
    )
    keywords: List[str] = Field(..., description="重要なキーワード")
    reasoning: str = Field(..., description="推定理由")


class InitialSuggestion(BaseModel):
    """初期提案用のデータモデル."""

    text: str = Field(..., description="提案する具体的な発話内容（質問など）")
    type: Literal["topic_shift", "deep_dive"] = Field(
        "topic_shift", description="初期提案なので基本は話題転換(topic_shift)扱いでOK"
    )
    speaker: str = Field(..., description="この発話を行うユーザーID")
    listener: str = Field(..., description="この発話を受け取るユーザーID")
    score: float = Field(0.8, ge=0.0, le=1.0, description="自信度 (0.0-1.0)")


class UserProfileAnalysis(BaseModel):
    """SNS分析結果と初期提案をまとめるコンテナモデル."""

    clusters: List[InterestCluster] = Field(..., description="抽出された興味クラスタ")
    summary: str = Field(..., description="ユーザーの人物像要約")
    initial_suggestions: List[InitialSuggestion] = Field(
        ..., description="分析に基づく会話のきっかけ提案(3つ程度)"
    )


class TopicLabel(BaseModel):
    """トピック分類の結果構造体"""

    topic: str = Field(
        ...,
        description="会話の内容を表す具体的かつ短いトピック名（例: '映画', 'Pythonの非同期処理', '週末のキャンプ'）",
    )


class SuggestionOutput(BaseModel):
    """LLMが出力する提案の1単位"""

    text: str = Field(..., description="具体的な発話内容や質問")
    type: str = Field(..., description="提案タイプ ('topic_shift' or 'deep_dive')")
    speaker: str = Field(..., description="発話者ID")
    listener: str = Field(..., description="対象者ID")
    score: float = Field(..., ge=0.0, le=1.0, description="推奨度スコア (0.0-1.0)")


class SuggestionList(BaseModel):
    suggestions: List[SuggestionOutput] = Field(
        ..., description="生成された提案のリスト"
    )


class IndividualProfileAnalysis(BaseModel):
    """個人のプロファイル分析結果（クラスタ抽出用）"""

    clusters: List[InterestCluster] = Field(
        ..., description="このユーザーの興味クラスタ（複数可）"
    )
    summary: str = Field(..., description="このユーザーの人物像の要約")
