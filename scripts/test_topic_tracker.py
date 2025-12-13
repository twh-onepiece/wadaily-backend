import asyncio
import os
import sys
import logging
import numpy as np

# プロジェクトルートへのパス設定
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.graph.nodes import topic_tracker
from app.graph.state import get_initial_state

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
# 不要なライブラリのログを抑制
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


async def main():
    print("--- シナリオテスト開始: 自然な会話フローによるトピック追跡 ---")

    state = get_initial_state()

    # 凝った会話シナリオ
    # ストーリー: 仕事の疲れ -> 癒やしの音楽 -> フェス(旅行) -> キャンプ用品(ガジェット) -> 待ち時間のゲーム
    scenario_texts = [
        # 1. 仕事・ストレス
        "やっと金曜日だね。今週はプロジェクトの納期が重なってて、正直かなりしんどかったよ。",
        # 2. 音楽 (癒やし)
        "家に帰ってからは、ずっとLo-Fi Hip Hopのプレイリスト流して頭を空っぽにしてる。こういうチルい音楽がないとやってられない。",
        # 3. 音楽 -> イベント (話題の転換点)
        "そういえば、来年のフジロックの第一弾アーティスト発表されたの見た？ ヘッドライナーが激アツで絶対行きたいんだよね。",
        # 4. イベント -> 旅行/アウトドア (具体的な計画)
        "会場の苗場まで行くなら、ホテル取るよりキャンプサイトでテント泊したいな。朝の山の中の空気って最高だし。",
        # 5. アウトドア -> ガジェット/技術 (道具の話へ)
        "キャンプといえば、最近Ankerが出した新しいポータブル電源を買ったんだ。MacBookも充電できるし、小型冷蔵庫も動かせるスペックのやつ。",
        # 6. ガジェット -> ゲーム (使い道の話へ)
        "その電源があれば、夜にテントの中でプロジェクター繋いでゲーム大会もできるね。Switchのドックも余裕で動くでしょ。",
        # 7. ゲーム (コンテンツの話へ)
        "新しいゼルダの伝説、まだクリアしてないからやり込みたいんだよね。あの広大なマップを探索してるだけで時間が溶ける。",
        # 8. まとめの感想
        "自然の中でゲームとか贅沢すぎる休日だね。よし、来月あたり計画立てようか。",
    ]

    print(
        f"{'Turn':<4} | {'Input Text (Snippet)':<30} | {'Topic':<12} | {'Sim (vs Prev)'}"
    )
    print("-" * 85)

    previous_vector = None

    for i, text in enumerate(scenario_texts):
        state["latest_text"] = text

        try:
            # ノード実行
            updates = await topic_tracker(state)

            # 結果取得
            current_vector = updates.get("current_topic_vector", [])
            visited = updates.get("visited_topics", [])
            latest_topic = visited[-1] if visited else "None"

            # ベクトル変化の確認 (コサイン類似度)
            similarity_str = "---"
            if previous_vector and current_vector:
                v1 = np.array(previous_vector)
                v2 = np.array(current_vector)
                sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                # 変化が見やすいようにフォーマット
                similarity_str = f"{sim:.4f}"

            # 表示用にテキストをトリミング
            snippet = (text[:28] + "..") if len(text) > 30 else text

            print(f"{i+1:<4} | {snippet:<30} | {latest_topic:<12} | {similarity_str}")

            # State更新 (文脈を引き継ぐ)
            state.update(updates)
            previous_vector = current_vector

        except Exception as e:
            print(f"Error at turn {i+1}: {e}")
            import traceback

            traceback.print_exc()
            break

    print("-" * 85)
    print("【抽出されたトピックの変遷】")
    print(" -> ".join(state["visited_topics"]))
    print("\n✅ テスト完了")


if __name__ == "__main__":
    asyncio.run(main())
