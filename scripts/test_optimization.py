import asyncio
import os
import sys
import logging

# プロジェクトルートへのパス設定
# (実行環境に合わせて適宜調整してください)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# 実際のモジュール構成に合わせてimportしてください
# エラーが出る場合はダミー等の調整が必要です
try:
    from app.graph.workflow import route_signal
    from app.graph.nodes import summarizer, silence_handler
    from app.graph.state import get_initial_state
except ImportError:
    # ローカルでテスト実行するために、importできない場合のダミー定義を入れることも可能です
    # ここではユーザー様の環境が整っている前提で進めます
    pass

# ログ設定: 内部動作が見えるように調整
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("app.graph.nodes").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


async def main():
    print("\n==================================================")
    print("   Optimization Logic Test")
    print("   Target: Router, Summarizer, SilenceHandler")
    print("==================================================\n")

    state = get_initial_state()
    user_alice = "Alice"
    user_bob = "Bob"

    # プロファイル設定（共通点：映画、旅行）
    state["profiles"] = {
        user_alice: {
            "user_id": user_alice,
            "interest_clusters": [{"keywords": ["Movie", "Action", "Travel"]}],
            "sns_data": {"likes": ["Cinema", "Kyoto"]},
        },
        user_bob: {
            "user_id": user_bob,
            "interest_clusters": [{"keywords": ["Movie", "Popcorn", "Hot Spring"]}],
            "sns_data": {"likes": ["Netflix", "Travel"]},
        },
    }

    # --------------------------------------------------
    # Case 1: Summarizer Test (履歴圧縮)
    # --------------------------------------------------
    print("🧪 [Test Case 1] Summarizer (Maintenance Path)")
    print("   Condition: History length >= Threshold (8)")

    # ★変更点: forループではなく、文脈のある具体的な会話データをセットします
    # 閾値(8)を超えるように10件用意
    dummy_history = [
        {
            "speaker": user_alice,
            "text": "ねえ、最近何か面白い映画観た？",
            "timestamp": 1000,
        },
        {
            "speaker": user_bob,
            "text": "ああ、先週公開されたアクション映画、すごく良かったよ！",
            "timestamp": 1001,
        },
        {
            "speaker": user_alice,
            "text": "へえ、アクション好きなんだ。私もたまに観るよ。",
            "timestamp": 1002,
        },
        {
            "speaker": user_bob,
            "text": "映画館で食べるポップコーンが最高なんだよね。",
            "timestamp": 1003,
        },
        {
            "speaker": user_alice,
            "text": "わかる！映画館の雰囲気いいよね。そういえば旅行は？",
            "timestamp": 1004,
        },
        {
            "speaker": user_bob,
            "text": "最近行けてないなあ。温泉とか行きたい。",
            "timestamp": 1005,
        },
        {
            "speaker": user_alice,
            "text": "京都の温泉とかどう？これからの季節いいかも。",
            "timestamp": 1006,
        },
        {
            "speaker": user_bob,
            "text": "いいねえ、京都。Netflixで京都が舞台の映画観て行きたくなってたんだ。",
            "timestamp": 1007,
        },
        {
            "speaker": user_alice,
            "text": "あ、それ私も観たかも！景色綺麗だったよね。",
            "timestamp": 1008,
        },
        {
            "speaker": user_bob,
            "text": "そうそう。やっぱり実際に現地に行きたいなあ。",
            "timestamp": 1009,
        },
    ]

    state["history_window"] = dummy_history
    state["summary"] = "会話開始。"  # 初期サマリー
    state["input_type"] = "text"  # 通常入力モード

    # 1. Router Check
    print("   [Check 1] Router Decision")
    next_node = route_signal(state)
    print(f"   -> Result: {next_node}")

    if next_node == "summarizer":
        print("   ✅ OK: Correctly directed to Summarizer.")
    else:
        print(f"   ❌ Failed: Expected 'summarizer', got '{next_node}'.")

    # 2. Summarizer Execution
    print("\n   [Check 2] Summarizer Execution")
    # ここでSummarizerが走り、要約生成と履歴の圧縮が行われます
    updates = await summarizer(state)

    new_history = updates.get("history_window", [])
    new_summary = updates.get("summary", "")

    print(f"   Old History Len: {len(dummy_history)}")
    print(f"   New History Len: {len(new_history)} (Expected: 2)")
    print(f"   New Summary    : {new_summary}")

    # 判定ロジック
    if len(new_history) == 2 and len(new_summary) > 10:
        print("   ✅ OK: History compressed and summary updated.")
    else:
        print("   ❌ Failed: History not compressed correctly.")

    # --------------------------------------------------
    # Case 2: Silence Handler Test (高速パス)
    # --------------------------------------------------
    print("\n--------------------------------------------------")
    print("🧪 [Test Case 2] SilenceHandler (Fast Path)")
    print("   Condition: input_type == 'silence'")

    # 入力を「沈黙」に設定
    state["input_type"] = "silence"

    # 1. Router Check
    print("   [Check 1] Router Decision")
    next_node = route_signal(state)
    print(f"   -> Result: {next_node}")

    if next_node == "silence_handler":
        print("   ✅ OK: Correctly directed to SilenceHandler.")
    else:
        print(f"   ❌ Failed: Expected 'silence_handler', got '{next_node}'.")

    # 2. SilenceHandler Execution
    print("\n   [Check 2] SilenceHandler Execution")

    # 直前の履歴やプロファイルに基づいて話題を提供するかテスト
    updates = await silence_handler(state)
    final_sugs = updates.get("final_suggestions", [])

    if final_sugs:
        sug = final_sugs[0]
        print(f"   Generated Text: {sug['text']}")
        print(f"   Speaker       : {sug['speaker']} (Should be Alice or Bob)")
        print(f"   Type          : {sug['type']}")

        # 簡易評価: キーワードが含まれているか
        text = sug["text"]
        keywords = [
            "映画",
            "Movie",
            "旅行",
            "Travel",
            "温泉",
            "京都",
            "アクション",
            "Netflix",
        ]
        if any(w in text for w in keywords):
            print("   ✅ OK: Topic generated based on common interests/context.")
        else:
            print("   ⚠️ Check Content manually (might be generic).")

        # AIっぽさのチェック
        if "お二人は" in text or "話題を変えましょう" in text:
            print("   ❌ Failed: Sounding too robotic/AI-like.")
        else:
            print("   ✅ OK: Natural phrasing.")

    else:
        print("   ❌ Failed: No suggestions generated.")

    print("\n==================================================")
    print("   Tests Completed")


if __name__ == "__main__":
    asyncio.run(main())
