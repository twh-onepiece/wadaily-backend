from typing import TypedDict, List, Dict, Literal, Annotated
import operator

# --- Constants ---
# OpenAI text-embedding-3-small のデフォルト次元数
# すべてのベクトル演算（興味クラスタ、トピック追跡）はこの次元数で統一する必要がある
# EMBEDDING_DIM = 1536
EMBEDDING_DIM = 1024


class ConversationTurn(TypedDict):
    """会話の1ターン（発話単位）を表すデータ構造.

    Attributes:
        speaker (str): 発話者のID、またはシステム発話の場合は "assistant".
        text (str): 発話内容のテキスト.
        timestamp (int): 発話時刻のUnix timestamp (ミリ秒).
    """

    speaker: str
    text: str
    timestamp: int


# 事前定義カテゴリリスト (共通興味の判定に使用)
CATEGORIES = [
    "スポーツ",
    "アウトドア",
    "音楽",
    "映画",
    "ゲーム",
    "テクノロジー",
    "料理",
    "旅行",
    "ファッション",
    "健康",
    "ビジネス",
    "アート",
    "読書",
    "ペット",
    "その他",
]


class SnsDataDict(TypedDict):
    """SnsDataのTypedDict表現（State保存用）"""

    posts: List[str]
    likes: List[str]


class InterestCluster(TypedDict):
    """ユーザーの特定の興味関心領域を表すクラスタ.

    SNSデータ等の分析により生成され、話題の提案に使用される.

    Attributes:
        category (str): CATEGORIES 定数に含まれるカテゴリ名.
        vector (List[float]): この興味領域の重心ベクトル (Dim: 1536).
        keywords (List[str]): このクラスタを構成する代表的なキーワード群.
    """

    category: str
    vector: List[float]
    keywords: List[str]


class UserProfile(TypedDict):
    """ユーザーごとのプロファイル情報.

    Attributes:
        user_id (str): ユーザーID.
        interest_clusters (List[InterestCluster]): ユーザーが持つ複数の興味クラスタ.
    """

    user_id: str
    sns_data: SnsDataDict
    interest_clusters: List[InterestCluster]


class Suggestion(TypedDict):
    """LLMまたはルールベースで生成された会話介入の候補.

    Attributes:
        text (str): 提案する発話内容や質問テキスト.
        type (Literal["deep_dive", "topic_shift", "silence_break"]): 提案の種類.
        score (float): 提案の適切さを示すスコア（0.0〜1.0）.
        speaker: この発話を行うユーザーID
        listener: この発話を受け取るユーザーID
    """

    text: str
    type: Literal["deep_dive", "topic_shift", "silence_break"]
    score: float
    speaker: str
    listener: str


class ConversationState(TypedDict):
    """LangGraph全体で共有・更新される会話の状態（State）.

    各ノードはこの状態を受け取り、更新分（差分）を返す.

    Attributes:
        input_type (Literal["text"]): 今回の実行トリガーとなった入力の種類（常にtext）.
        latest_text (str): 最新のユーザー発話テキスト.
        history_window (List[ConversationTurn]): 直近Nターンの会話履歴（生データ）.
        summary (str): 過去の会話の要約.コンテキスト圧縮により生成される.
        profiles (Dict[str, UserProfile]): 参加ユーザーのプロファイルマップ（Key: user_id）.
        speaker (str): 提案を受けて発話する側のユーザーID.
        listener (str): 提案を聞く側のユーザーID.
        current_topic_vector (List[float]): 現在の会話内容の埋め込みベクトル (Dim: 1536).
            初期値は空リストで、最初の会話発生時に計算される.
        visited_topics (List[str]): 今回のセッションで既に話題に上がったカテゴリ名のリスト.
        is_terminated (bool): セッション終了フラグ.
        candidates (List[Suggestion]): 各並列ノードが生成した提案候補のリスト.
            Annotatedとoperator.addにより、各ノードの出力はリストに追記（append）される.
        final_suggestions (List[Suggestion]): スコアリングを経て選定された、最終的な提案リスト.
    """

    # --- Input Signal ---
    input_type: Literal["text"]
    latest_text: str

    # --- Context Management ---
    history_window: List[ConversationTurn]
    summary: str

    # --- Profile Data ---
    profiles: Dict[str, UserProfile]
    speaker: str
    listener: str

    # --- Topic Tracking ---
    current_topic_vector: List[float]
    visited_topics: List[str]

    # --- Control Flags ---
    is_terminated: bool

    # --- Output Candidates ---
    candidates: Annotated[List[Suggestion], operator.add]
    final_suggestions: List[Suggestion]


def get_initial_state() -> ConversationState:
    """LangGraphの初期状態（デフォルト値）を生成するファクトリ関数.

    ステートマシンの開始時に呼び出され、安全なデフォルト値を持つ辞書を返す.
    特にベクトルの空リスト初期化や、リスト型の初期化漏れを防ぐために使用する.

    Returns:
        ConversationState: 初期化された状態辞書.
            Note: current_topic_vector は空リスト[]で初期化される.
    """
    return {
        "input_type": "text",
        "latest_text": "",
        "history_window": [],
        "summary": "",
        "profiles": {},
        "speaker": "",
        "listener": "",
        # ベクトルは初期状態では空リストとし、最初の計算時に設定する仕様とする
        "current_topic_vector": [],
        "visited_topics": [],
        "is_terminated": False,
        "candidates": [],
        "final_suggestions": [],
    }
