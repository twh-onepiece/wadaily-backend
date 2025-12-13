import asyncio
import os
import sys
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.graph.nodes import adaptive_scorer
from app.graph.state import get_initial_state
from app.graph.nodes import get_embeddings_model  # Embeddingモデルを取得

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("app.graph.nodes").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


async def main():
    print("\n==================================================")
    print("   Adaptive Scorer 実戦テスト (Real Embeddings)")
    print("   目的: 文脈と興味に基づいて適切な順位付けがされるか")
    print("==================================================\n")

    state = get_initial_state()
    user_alice = "Alice"

    # Embeddingモデルの取得
    embeddings_model = get_embeddings_model()

    print("⏳ Generating profile vectors using OpenAI API...")

    # 1. ベクトル準備 (乱数ではなく本物のEmbeddingを使う)
    # Aliceの興味: テックと食事
    # 現在の話題: キーボード

    vec_tech = await embeddings_model.aembed_query(
        "最新のキーボードやガジェット、デスク環境について"
    )
    vec_food = await embeddings_model.aembed_query(
        "美味しいラーメンや激辛料理、食べ歩きについて"
    )
    vec_current_topic = await embeddings_model.aembed_query(
        "HHKBの打鍵感と静音モデルのレビュー"
    )

    # Aliceのプロファイル設定
    state["profiles"] = {
        user_alice: {
            "user_id": user_alice,
            "interest_clusters": [
                {
                    "category": "Tech",
                    "vector": vec_tech,
                    "keywords": ["キーボード", "ガジェット"],
                },
                {
                    "category": "Food",
                    "vector": vec_food,
                    "keywords": ["ラーメン", "激辛"],
                },
            ],
        }
    }

    # 現在の話題ベクトル
    state["current_topic_vector"] = vec_current_topic

    # 2. 候補データの準備
    candidates = [
        {
            "text": "キーボードの軸は何を使ってるの？",  # Tech / Deep Dive
            "type": "deep_dive",
            "score": 0.5,
            "speaker": "Bob",
            "listener": user_alice,
        },
        {
            "text": "そういえば新しいマウス出たよね。",  # Tech / Topic Shift (文脈に近い)
            "type": "topic_shift",
            "score": 0.5,
            "speaker": "Bob",
            "listener": user_alice,
        },
        {
            "text": "最近、美味しいラーメン屋見つけた？",  # Food / Topic Shift (文脈に遠い + 興味あり)
            "type": "topic_shift",
            "score": 0.5,
            "speaker": "Bob",
            "listener": user_alice,
        },
        {
            "text": "株式投資についてどう思う？",  # Finance / Topic Shift (興味なし)
            "type": "topic_shift",
            "score": 0.5,
            "speaker": "Bob",
            "listener": user_alice,
        },
    ]
    state["candidates"] = candidates

    print("【Candidates Input】")
    for i, c in enumerate(candidates):
        print(f"#{i+1}: [{c['type']}] {c['text']}")
    print("-" * 50)

    # 3. Scorer 実行
    print("\nRunning Scorer...")
    result = await adaptive_scorer(state)
    final = result.get("final_suggestions", [])

    print("\n【Final Selection (Top 3)】")
    for i, s in enumerate(final):
        print(f"Rank #{i+1}: Score {s['score']:.3f} | [{s['type']}] {s['text']}")

    # 検証ロジック
    print("\n【検証結果】")

    top_texts = [s["text"] for s in final]

    # 1. キーボード (Deep Dive): 興味あり + 文脈一致 -> 高スコア
    if any("キーボード" in t for t in top_texts[:2]):
        print("✅ OK: 文脈に沿ったDeep Diveが高評価されました。")
    else:
        print("⚠️ Warning: Deep Diveのスコアが低いです。")

    # 2. ラーメン (Topic Shift): 興味あり + 文脈不一致(距離大) -> 高スコア
    if any("ラーメン" in t for t in top_texts[:2]):
        print("✅ OK: 興味に沿ったTopic Shiftが高評価されました。")
    else:
        print("⚠️ Warning: 興味合致のTopic Shiftのスコアが低いです。")

    # 3. 株式投資 (Topic Shift): 興味なし -> 圏外または最下位
    if any("株式" in t for t in top_texts):
        print("⚠️ Warning: 興味のない話題が選ばれてしまいました。")
    else:
        print("✅ OK: 興味のない話題は除外されました（Rank外）。")

    print("\n✅ テスト完了")


if __name__ == "__main__":
    asyncio.run(main())
