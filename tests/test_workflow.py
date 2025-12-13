from app.graph.workflow import get_graph_app
from app.graph.state import get_initial_state
import pytest


@pytest.mark.asyncio
async def test_normal_path_text_input():
    """通常パス（テキスト入力）のテスト: Tracker -> Generators -> Scorer と進むか"""
    # 1. 初期状態の用意
    state = get_initial_state()
    state["input_type"] = "text"
    state["latest_text"] = "こんにちは"
    state["speaker"] = "user_A"
    state["listener"] = "user_B"
    state["profiles"] = {
        "user_A": {
            "user_id": "user_A",
            "sns_data": {"posts": [], "likes": []},
            "interest_clusters": []
        },
        "user_B": {
            "user_id": "user_B",
            "sns_data": {"posts": [], "likes": []},
            "interest_clusters": []
        }
    }

    # 2. グラフ実行（非同期）
    graph_app = get_graph_app()
    result = await graph_app.ainvoke(state)

    # 3. 検証 (Assert)
    # 最終的な提案が含まれているか
    assert "final_suggestions" in result
    suggestions = result["final_suggestions"]
    assert len(suggestions) > 0

    # ダミー実装で入れた値が返ってきているか確認 (DeepDive or TopicShift)
    types = [s["type"] for s in suggestions]
    assert "deep_dive" in types or "topic_shift" in types


# 沈黙対応は削除されたのでテストも削除
# def test_fast_path_silence():
#     """高速パス（沈黙）のテスト: Router -> SilenceHandler -> END と進むか"""
#     # 1. 初期状態
#     state = get_initial_state()
#     state["input_type"] = "silence"
#     # 2. グラフ実行
#     result = graph_app.invoke(state)
#     # 3. 検証
#     assert "final_suggestions" in result
#     suggestions = result["final_suggestions"]
#     assert len(suggestions) > 0
#     # SilenceHandlerが返すダミーデータの確認
#     assert suggestions[0]["type"] == "silence_break"
#     assert "（沈黙）" in suggestions[0]["text"]


@pytest.mark.asyncio
async def test_maintenance_path_summary():
    """メンテナンスパス（履歴過多）のテスト: Summarizerを経由するか"""
    state = get_initial_state()
    state["input_type"] = "text"
    state["speaker"] = "user_A"
    state["listener"] = "user_B"
    state["profiles"] = {
        "user_A": {
            "user_id": "user_A",
            "sns_data": {"posts": [], "likes": []},
            "interest_clusters": []
        },
        "user_B": {
            "user_id": "user_B",
            "sns_data": {"posts": [], "likes": []},
            "interest_clusters": []
        }
    }
    # 履歴をわざと多くして閾値(8)を超えるようにする
    # ※ ConversationTurnの型定義に合わせてダミーデータを作成
    dummy_turn = {"speaker": "user_A", "text": "a", "timestamp": 1000}
    state["history_window"] = [dummy_turn] * 11

    graph_app = get_graph_app()
    result = await graph_app.ainvoke(state)

    # 履歴が圧縮されていることを確認
    # Summarizerは直近2件を残すので、履歴は減少しているはず
    assert len(result["history_window"]) < 11
