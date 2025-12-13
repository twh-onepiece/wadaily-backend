import asyncio
import os
import sys
import json

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.graph.nodes import profile_analyzer
from app.schemas.session import User, SnsData
from app.graph.state import get_initial_state


def create_dummy_state():
    """
    APIの /sessions エンドポイントで行われる初期化処理を模倣し、
    State['profiles'] に辞書形式でデータをセットアップする。
    """

    # 1. 入力データ（Pydanticモデル）の作成
    user_a = User(
        user_id="user_tech",
        sns_data=SnsData(
            posts=[
                "昨日は深夜までPythonの非同期処理のデバッグをしてた。asyncio難しいけど面白い。",
                "新しいMacBook ProのM3チップ、ビルド速度が爆速で感動してる。",
                "週末はハッカソンに参加予定。生成AIを使ったアプリを作るつもり。",
            ],
            likes=["GitHub", "TechCrunch", "Gadget", "Coffee"],
        ),
    )

    user_b = User(
        user_id="user_camp",
        sns_data=SnsData(
            posts=[
                "週末のキャンプ場の予約取れた！焚き火台を新調したので使うのが楽しみ。",
                "富士山の麓で飲むコーヒーは最高においしい。",
                "最近はソロキャンプ動画ばかり見てる気がする。",
            ],
            likes=["SnowPeak", "GoPro", "Travel", "Nature"],
        ),
    )

    # 2. Stateの初期化（デフォルト値）
    state = get_initial_state()

    # 3. State['profiles'] へのデータ変換と格納
    # APIサーバーが受け取ったリクエストを処理するのと同様に、
    # Pydanticモデルを dict に変換(model_dump)して格納します。
    state["profiles"] = {
        user_a.user_id: {
            "user_id": user_a.user_id,
            "sns_data": user_a.sns_data.model_dump(),  # ここ重要: オブジェクトではなく辞書にする
            "interest_clusters": [],
        },
        user_b.user_id: {
            "user_id": user_b.user_id,
            "sns_data": user_b.sns_data.model_dump(),
            "interest_clusters": [],
        },
    }

    return state


async def main():
    print("--- テスト開始: Profile Analyzer ---")

    # 1. ダミーデータの準備
    state = create_dummy_state()
    print(f"Input State Keys: {list(state.keys())}")
    print(f"Target Users: {list(state['profiles'].keys())}")

    # 2. ノード関数の実行
    try:
        # profile_analyzer は state["profiles"] を読み取り、分析結果を返します
        result = await profile_analyzer(state)

        print("\n--- 実行結果 (Diff) ---")
        # 結果を見やすく整形して表示
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 3. 検証ロジック
        suggestions = result.get("initial_suggestions", [])

        if not suggestions:
            print("\n❌ テスト失敗: 提案が生成されませんでした。")
            return

        # チェック: 提案数が正しいか（ユーザー数 x 3 = 6）
        expected_count = 3 * len(state["profiles"])
        if len(suggestions) == expected_count:
            print(f"\n✅ 提案数チェックOK: {len(suggestions)}件 (各ユーザー3件)")
        else:
            print(f"\n⚠️ 提案数警告: {len(suggestions)}件 (期待値: {expected_count})")

        # チェック: SpeakerとListenerが正しく設定されているか
        for i, s in enumerate(suggestions):
            if s["speaker"] == s["listener"]:
                print(
                    f"❌ エラー: 提案#{i} でSpeakerとListenerが同じです ({s['speaker']})"
                )

        print("\n✅ テスト完了")

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
