import logging
from functools import lru_cache
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from app.graph.state import ConversationState
from app.graph.nodes import (
    # silence_handler,  # 沈黙対応不要のためコメントアウト
    summarizer,
    topic_tracker,
    generator_deep_dive,
    generator_topic_shift,
    adaptive_scorer,
)

logger = logging.getLogger(__name__)

HISTORY_THRESHOLD = 8


def route_signal(state: ConversationState) -> str:
    """入力シグナルと状態に基づいて、次の遷移先ノードを決定するルーティング関数.

    以下の優先順位で条件分岐を行う：
    1. Maintenance Path: 会話履歴が閾値を超えた場合 -> summarizer
    2. Normal Path: 上記以外（通常のテキスト入力） -> topic_tracker

    Args:
        state (ConversationState): 現在の会話状態.

    Returns:
        str: 次に実行すべきノード名（"summarizer" または "topic_tracker"）.
    """
    history = state.get("history_window", [])

    logger.info(f"--- Router: history_len={len(history)} ---")

    # 1. メンテナンスパス (履歴圧縮)
    if len(history) > HISTORY_THRESHOLD:
        return "summarizer"

    # 2. 通常パス
    return "topic_tracker"


def build_graph():
    """LangGraphのステートマシン（グラフ）を構築・コンパイル.

    architecture.md の設計に基づき、ノードとエッジを定義.
    主な特徴：
    - Routerによる動的なパス分岐（履歴圧縮のみ）
    - TopicTrackerからの分岐による Generators（DeepDive, TopicShift）の並列実行
    - AdaptiveScorerへの合流（Fan-in）と候補のマージ
    - speaker目線での提案生成

    Returns:
        CompiledStateGraph: invoke可能なコンパイル済みグラフアプリケーション.
    """

    workflow = StateGraph(ConversationState)

    # silence_handlerは削除（沈黙対応不要）
    workflow.add_node("summarizer", summarizer)
    workflow.add_node("topic_tracker", topic_tracker)
    workflow.add_node("generator_deep_dive", generator_deep_dive)
    workflow.add_node("generator_topic_shift", generator_topic_shift)
    workflow.add_node("adaptive_scorer", adaptive_scorer)

    # START -> Router (条件分岐)
    workflow.add_conditional_edges(
        START,
        route_signal,
        {
            "summarizer": "summarizer",
            "topic_tracker": "topic_tracker",
        },
    )

    # Maintenance Path
    workflow.add_edge("summarizer", "topic_tracker")

    # Normal Path (Parallel Execution)
    # TopicTracker -> DeepDive & TopicShift
    workflow.add_edge("topic_tracker", "generator_deep_dive")
    workflow.add_edge("topic_tracker", "generator_topic_shift")

    # Generators -> Scorer (Fan-in)
    workflow.add_edge("generator_deep_dive", "adaptive_scorer")
    workflow.add_edge("generator_topic_shift", "adaptive_scorer")

    # Scorer -> END
    workflow.add_edge("adaptive_scorer", END)

    return workflow.compile()


# Lazy Loading
@lru_cache
def get_graph_app() -> CompiledStateGraph:
    """コンパイル済みグラフインスタンスを提供するDependency Injection用関数。

    lru_cacheによりシングルトンとして振る舞う.
    初回呼び出し時のみ build_graph() が実行され、以降はキャッシュされたインスタンスを返す.
    テスト時には app.dependency_overrides で容易にモックへ差し替え可能.
    """
    return build_graph()
