import asyncio
import os
import sys
import logging
import numpy as np

# プロジェクトルートへのパス設定
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.graph.nodes import generator_deep_dive, generator_topic_shift
from app.graph.state import get_initial_state

# ログ設定: 内部動作が見えるように調整
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("app.graph.nodes").setLevel(logging.INFO)
# 無関係なログを抑制
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


# --- Helper: ベクトル生成 ---
def normalize(v):
    norm = np.linalg.norm(v)
    if norm == 0:
        return v
    return (v / norm).tolist()


def create_vector(seed: int) -> list[float]:
    """完全にランダムなベクトル（互いに直交に近い＝距離が遠い）"""
    np.random.seed(seed)
    v = np.random.rand(1536) - 0.5
    return normalize(v)


def mix_vectors(v1: list[float], v2: list[float], ratio: float) -> list[float]:
    """v1にv2を混ぜて「似ているが少し違う」ベクトルを作る（距離が近い）"""
    vec = np.array(v1) * (1 - ratio) + np.array(v2) * ratio
    return normalize(vec)


async def main():
    print("\n==================================================")
    print("   Generators 総合実戦テスト")
    print("   Scenario: 多面的な趣味を持つAliceとBob")
    print("   Current Context: ガジェット（キーボード）の話")
    print("==================================================\n")

    state = get_initial_state()
    user_alice = "Alice"
    user_bob = "Bob"

    # --- 1. ベクトルとプロファイルの準備 ---
    # 基準ベクトル (Tech)
    vec_tech = create_vector(seed=100)

    # Techと遠いベクトル (Food, Nature)
    vec_food = create_vector(seed=200)
    vec_nature = create_vector(seed=300)

    # Techに近いベクトル (Gaming) -> Tech成分70%
    vec_gaming = mix_vectors(vec_tech, create_vector(seed=400), ratio=0.3)

    state["profiles"] = {
        user_alice: {
            "user_id": user_alice,
            "sns_data": {"likes": ["Gadget", "Spicy Food"], "posts": []},
            "interest_clusters": [
                {
                    "category": "テクノロジー",
                    "keywords": ["HHKB", "自作キーボード", "デスク環境"],
                    "vector": vec_tech,
                },
                {
                    "category": "グルメ",
                    "keywords": ["激辛ラーメン", "蒙古タンメン", "ハバネロ"],
                    "vector": vec_food,  # ★ Techと遠い (Shift候補)
                },
            ],
        },
        user_bob: {
            "user_id": user_bob,
            "sns_data": {"likes": ["Camping", "Retro Games"], "posts": []},
            "interest_clusters": [
                {
                    "category": "アウトドア",
                    "keywords": ["ソロキャンプ", "焚き火", "コーヒー"],
                    "vector": vec_nature,  # ★ Techと遠い (Shift候補)
                },
                {
                    "category": "ゲーム",
                    "keywords": ["レトロゲーム", "RPG", "ドット絵"],
                    "vector": vec_gaming,  # ★ Techに近い (除外対象)
                },
            ],
        },
    }

    # --- 2. コンテキスト設定 ---
    # Aliceが新しいキーボードについて熱弁している状況
    state["history_window"] = [
        {
            "speaker": user_bob,
            "text": "Aliceのデスク、また雰囲気変わった？",
            "timestamp": 1000,
        },
        {
            "speaker": user_alice,
            "text": "気づいた？ついにHHKBの雪モデルを買っちゃったんだ。",
            "timestamp": 2000,
        },
        {
            "speaker": user_bob,
            "text": "真っ白なやつだよね。汚れ目立たない？",
            "timestamp": 3000,
        },
        {
            "speaker": user_alice,
            "text": "今のところ大丈夫。それより打鍵感が最高で、無限に仕事できそうなくらい。",
            "timestamp": 4000,
        },
    ]
    state["latest_text"] = state["history_window"][-1]["text"]
    state["summary"] = (
        "Aliceは新しいHHKB（キーボード）を購入し、その打鍵感やデザインに非常に満足している。"
    )

    # 現在のトピックベクトル = Tech
    state["current_topic_vector"] = vec_tech

    print(f"Summary: {state['summary']}")
    print(f"Latest:  {state['latest_text']}")
    print("-" * 60)

    # --------------------------------------------------
    # 3. Deep Dive テスト (Gap Analysis)
    # --------------------------------------------------
    print("\n🔍 [Testing Generator: Deep Dive]")
    print("   期待: 「背景(Why)」「体験(Exp)」「未来(Future)」の3視点で生成されること")

    dd_result = await generator_deep_dive(state)
    dd_cands = dd_result.get("candidates", [])

    if dd_cands:
        for i, c in enumerate(dd_cands):
            print(f"\n   [Candidate #{i+1}]")
            print(f"   Text : {c['text']}")
            print(f"   Score: {c['score']}")

            # 簡易チェック
            txt = c["text"]
            if "きっかけ" in txt or "なぜ" in txt or "決め手" in txt:
                print("   👉 Type: 背景・きっかけ (Why)")
            elif "違い" in txt or "実際" in txt or "感触" in txt:
                print("   👉 Type: 具体的な体験・比較 (Exp)")
            elif "次" in txt or "今後" in txt or "仕事" in txt:
                print("   👉 Type: 展開・影響 (Future)")
    else:
        print("   ❌ No candidates generated.")

    # --------------------------------------------------
    # 4. Topic Shift テスト (Vector Distance)
    # --------------------------------------------------
    print("\n\n🔀 [Testing Generator: Topic Shift]")
    print(
        "   期待: Techに近い「ゲーム」ではなく、遠い「激辛グルメ」や「キャンプ」が選ばれること"
    )

    ts_result = await generator_topic_shift(state)
    ts_cands = ts_result.get("candidates", [])

    if ts_cands:
        print(f"\n   Generated {len(ts_cands)} suggestions based on vector distance:")
        for i, c in enumerate(ts_cands):
            print(f"\n   [Candidate #{i+1}]")
            print(f"   Text : {c['text']}")

            # 成功判定
            txt = c["text"]
            if any(
                w in txt
                for w in ["辛", "ラーメン", "食べ", "キャンプ", "山", "コーヒー"]
            ):
                print("   ✅ OK: 遠い話題（グルメ/アウトドア）への転換です。")
            elif any(w in txt for w in ["ゲーム", "RPG"]):
                print(
                    "   ⚠️ Warning: 近い話題（ゲーム）が選ばれました（ベクトル計算の確認推奨）。"
                )
            else:
                print("   ❓ Other topic.")
    else:
        print("   ❌ No candidates generated.")

    print("\n==================================================")
    print("   テスト完了")


if __name__ == "__main__":
    asyncio.run(main())
