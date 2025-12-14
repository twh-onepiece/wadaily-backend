import logging
import traceback
import numpy as np
import asyncio
import random

from typing import Dict, Any, List
from functools import lru_cache
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import SAKURANOAI_API_BASE_URL, SAKURANOAI_API_KEY, OPENAI_MODEL_ID, OPENAI_EMBEDDING_MODEL_ID
from app.graph.utils import (
    safe_float,
    sanitize_text,
    determine_speaker_listener,
    calculate_cosine_similarity,
)
from app.graph.state import ConversationState, Suggestion, EMBEDDING_DIM
from app.schemas.analysis import UserProfileAnalysis, TopicLabel, SuggestionList, IndividualProfileAnalysis
from app.utils.prompts import (
    PROFILE_ANALYZER_SYSTEM_PROMPT,
    TOPIC_TRACKER_SYSTEM_PROMPT,
    TOPIC_SHIFT_SYSTEM_PROMPT,
    DEEP_DIVE_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    SILENCE_HANDLER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# --- Constants ---
# トピックベクトルの更新係数 (0.0 < alpha <= 1.0)
# 値が大きいほど「最新の発話」の影響が強くなり、小さいほど「過去の文脈」を維持する
EMA_ALPHA = 0.5
TIMEOUT_EMBEDDING = 5
TIMEOUT_LLM = 15
HISTORY_CONTEXT_WINDOW = 5

# ノイズ除去: これ以下の類似度は 0.0 とみなす
SCORE_SIM_THRESHOLD = 0.3

# Deep Dive の重み:
# 質問文は文脈との類似度が低く出がちなので、Context Simを補正(ブースト)する係数
DEEP_DIVE_CONTEXT_BOOST = 2.0
# 興味(Profile) 6 : 文脈(Context) 4
WEIGHT_DD_PROFILE = 0.6
WEIGHT_DD_CONTEXT = 0.4

# Topic Shift の重み: 興味(Profile) 7 : 文脈距離(Distance) 3
# ※ 興味がない話題への転換は避けたいため、Profileを重視
WEIGHT_TS_PROFILE = 0.7
WEIGHT_TS_DISTANCE = 0.3

# 最終スコアのブレンド率: アルゴリズム計算値 9 : LLM初期値 1
# LLMのスコア(0.5等)はあまり当てにならないため、計算値を優先
WEIGHT_FINAL_ALGO = 0.9
WEIGHT_FINAL_BASE = 0.1

HISTORY_KEEP_LAST = 2  # 要約後も文脈維持のために残す直近ターン数


@lru_cache(maxsize=1)
def get_embeddings_model() -> OpenAIEmbeddings:
    """
    OpenAIEmbeddingsのインスタンスをキャッシュして返す。
    シングルトンとして振る舞い、再利用時のオーバーヘッドを削減する。
    """
    return OpenAIEmbeddings(
        model=OPENAI_EMBEDDING_MODEL_ID,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_EMBEDDING,
    )


@lru_cache(maxsize=1)
def get_silence_chain():
    llm = ChatOpenAI(
        model=OPENAI_MODEL_ID,
        temperature=0.5,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_LLM,
    )
    structured_llm = llm.with_structured_output(SuggestionList)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SILENCE_HANDLER_SYSTEM_PROMPT),
            (
                "human",
                "【現在の状況】\n"
                "話者 (Speaker): {speaker}\n"
                "聞き手 (Listener): {listener}\n\n"
                "【共通の興味】\n{common_interests}\n\n"
                "【既出トピック】\n{visited}",
            ),
        ]
    )
    return prompt | structured_llm


@lru_cache(maxsize=1)
def get_summarizer_chain():
    llm = ChatOpenAI(
        model=OPENAI_MODEL_ID,
        temperature=0.3,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_LLM,
    )
    return llm


@lru_cache(maxsize=1)
def get_topic_extractor_chain():
    """
    トピック抽出用のLLMチェーンをキャッシュして返す。
    """
    llm = ChatOpenAI(
        model=OPENAI_MODEL_ID,
        temperature=0.0,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_LLM,
    )
    structured_llm = llm.with_structured_output(TopicLabel)

    # プロンプトも不変なのでここで定義してチェーン化しておく
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                TOPIC_TRACKER_SYSTEM_PROMPT,
            ),
            ("human", "{text}"),
        ]
    )

    return prompt | structured_llm


@lru_cache(maxsize=1)
def get_deep_dive_chain():
    llm = ChatOpenAI(
        model=OPENAI_MODEL_ID,
        temperature=0.7,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_LLM,
    )
    structured_llm = llm.with_structured_output(SuggestionList)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", DEEP_DIVE_SYSTEM_PROMPT),
            (
                "human",
                "【会話要約】\n{summary}\n\n【直近の会話履歴】\n{history}\n\n【直前の発言】\n{latest_text}\n\n【発話者情報】\nSpeaker: {speaker}\nListener: {listener}",
            ),
        ]
    )
    return prompt | structured_llm


@lru_cache(maxsize=1)
def get_topic_shift_chain():
    llm = ChatOpenAI(
        model=OPENAI_MODEL_ID,
        temperature=0.8,
        api_key=SAKURANOAI_API_KEY,
        base_url=SAKURANOAI_API_BASE_URL,
        timeout=TIMEOUT_LLM,
    )
    structured_llm = llm.with_structured_output(SuggestionList)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", TOPIC_SHIFT_SYSTEM_PROMPT),
            (
                "human",
                "【未探索トピック (Unexplored Topics)】\n{candidates}\n\n【発話者情報】\nSpeaker: {speaker}\nListener: {listener}",
            ),
        ]
    )
    return prompt | structured_llm


async def profile_analyzer(state: ConversationState) -> Dict[str, Any]:
    """
    profile_analyzer using the enhanced prompt that enforces speaker/listener fields.
    個々人のプロファイルをOpenAI APIで分析してクラスタとベクトルを抽出.
    Returns: {"profiles": {...}, "initial_suggestions": [...]}
    Speaker目線でlistenerに対する提案を生成.
    """
    logger.info("--- Node: ProfileAnalyzer (analyzing individual clusters with OpenAI) ---")

    profiles = state.get("profiles", {})
    user_ids = list(profiles.keys())

    # stateからspeaker/listenerを取得
    speaker = state.get("speaker", "")
    listener = state.get("listener", "")

    combined_input = ""

    if not profiles:
        combined_input = state.get("latest_text", "") or ""

    else:
        for uid, user_data in profiles.items():
            # user_data は Dict (UserProfile TypedDict) なので ["key"] でアクセス
            # sns_data も Dict になっている
            sns = user_data.get("sns_data", {})
            posts_list = sns.get("posts", [])
            likes_list = sns.get("likes", [])

            posts_str = "\n".join(f"- {p}" for p in posts_list)
            likes_str = ", ".join(likes_list)

            combined_input += (
                f"\n[User: {uid}]\nPosts:\n{posts_str}\nLikes: {likes_str}\n"
            )

    if not combined_input.strip():
        logger.warning("No SNS data found for analysis.")

        if not user_ids or not speaker or not listener:
            logger.warning("No users or speaker/listener not set in state. Returning empty suggestions.")
            return {"profiles": {}, "initial_suggestions": []}

        # speaker目線でlistenerへの提案を生成
        fillers = [
            {
                "text": "普段どんなことに興味を持っていますか？よければ教えてください。",
                "type": "topic_shift",
                "speaker": speaker,
                "listener": listener,
                "score": 0.6,
            },
            {
                "text": "最近気になっていることはありますか？もしあれば教えてください。",
                "type": "topic_shift",
                "speaker": speaker,
                "listener": listener,
                "score": 0.55,
            },
            {
                "text": "週末はどのように過ごすことが多いですか？",
                "type": "topic_shift",
                "speaker": speaker,
                "listener": listener,
                "score": 0.5,
            },
        ]
        return {"profiles": {}, "initial_suggestions": fillers}

    # === 個々人のクラスタ抽出（並列実行） ===
    embeddings_model = get_embeddings_model()
    individual_llm = ChatOpenAI(model=OPENAI_MODEL_ID, temperature=0.3, api_key=SAKURANOAI_API_KEY, base_url=SAKURANOAI_API_BASE_URL)
    structured_individual_llm = individual_llm.with_structured_output(IndividualProfileAnalysis)

    individual_prompt = ChatPromptTemplate.from_messages([
        ("system", "あなたはユーザープロファイル分析の専門家です。SNSデータからユーザーの興味関心をクラスタとして抽出してください。"),
        ("human", "以下のユーザーのSNSデータを分析し、興味関心のクラスタを抽出してください:\n\n{user_data}")
    ])
    individual_chain = individual_prompt | structured_individual_llm

    # 各ユーザーの分析を並列実行するための内部関数
    async def process_single_user(uid: str, user_data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """単一ユーザーのプロファイル分析を実行"""
        sns = user_data.get("sns_data", {})
        posts = sns.get("posts", [])
        likes = sns.get("likes", [])
        user_input = f"Posts:\n" + "\n".join(f"- {p}" for p in posts) + f"\n\nLikes: {', '.join(likes)}"

        try:
            # LLM分析
            individual_result: IndividualProfileAnalysis = await individual_chain.ainvoke(
                {"user_data": user_input},
                config={"timeout": TIMEOUT_LLM}
            )

            # 各クラスタにベクトルを付与
            clusters_with_vectors = []
            for cluster in individual_result.clusters:
                cluster_text = f"{cluster.category}: {', '.join(cluster.topics[:3])}"

                try:
                    cluster_vector = await asyncio.wait_for(
                        embeddings_model.aembed_query(cluster_text),
                        timeout=TIMEOUT_EMBEDDING
                    )
                    vector = cluster_vector
                except Exception as e:
                    logger.warning(f"Failed to embed cluster for {uid}: {e}")
                    vector = []

                clusters_with_vectors.append({
                    "category": cluster.category,
                    "topics": cluster.topics,
                    "keywords": cluster.keywords,
                    "vector": vector,
                    "reasoning": cluster.reasoning
                })

            logger.info(f"Extracted {len(clusters_with_vectors)} clusters for user {uid}")

            return uid, {
                "user_id": uid,
                "sns_data": sns,
                "interest_clusters": clusters_with_vectors
            }
        except Exception as e:
            logger.error(f"Failed to analyze profile for {uid}: {e}")
            return uid, {
                "user_id": uid,
                "sns_data": sns,
                "interest_clusters": []
            }

    # ★ 並列実行
    tasks = [process_single_user(uid, data) for uid, data in profiles.items()]
    results = await asyncio.gather(*tasks)

    # 結果を辞書にまとめる
    enriched_profiles = {uid: profile_data for uid, profile_data in results}

    # === 全体の共通点分析とサマリ生成（既存のUserProfileAnalysis使用） ===
    system_prompt = PROFILE_ANALYZER_SYSTEM_PROMPT

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "以下のユーザーデータを分析してください:\n\n{text}"),
        ]
    )

    llm = ChatOpenAI(model=OPENAI_MODEL_ID, temperature=0.5, api_key=SAKURANOAI_API_KEY, base_url=SAKURANOAI_API_BASE_URL)
    structured_llm = llm.with_structured_output(UserProfileAnalysis)
    chain = prompt | structured_llm

    try:
        result: UserProfileAnalysis = await chain.ainvoke(
            {"text": combined_input}, config={"timeout": TIMEOUT_LLM}
        )
        analysis_data = result.model_dump()

        # 全体の共通クラスタ情報（APIレスポンス用）
        profiles_meta = {
            "clusters": analysis_data.get("clusters", []),
            "summary": analysis_data.get("summary", ""),
        }

        # candidate topicsを個々人のクラスタから抽出
        candidate_topics: List[str] = []
        for uid, prof in enriched_profiles.items():
            for cluster in prof.get("interest_clusters", []):
                candidate_topics.extend(cluster.get("topics", [])[:2])

        # 全体分析からも追加
        clusters_raw = analysis_data.get("clusters", [])
        for c in clusters_raw:
            if isinstance(c, str):
                candidate_topics.append(c)
            elif isinstance(c, dict):
                candidate_topics.extend(c.get("topics", []) or [])
        if not candidate_topics:
            candidate_topics = ["旅行", "グルメ", "休日の過ごし方", "最近の興味"]

        # normalize incoming suggestions (LLM -> new schema)
        raw_sugs = analysis_data.get("initial_suggestions", [])
        normalized: List[Dict[str, Any]] = []
        for s in raw_sugs:
            text = (s.get("text") or s.get("content") or s.get("message") or "").strip()
            typ = s.get("type") or "topic_shift"
            speaker = s.get("speaker") or s.get("target") or None
            listener = s.get("listener") or s.get("to") or None
            raw_score = s.get("score", 0.5)
            score = safe_float(raw_score, default=0.5)

            if typ not in ("topic_shift", "deep_dive"):
                typ = "topic_shift"
            normalized.append(
                {
                    "text": text,
                    "type": typ,
                    "speaker": speaker,
                    "listener": listener,
                    "score": max(0.0, min(1.0, score)),
                }
            )

        # speaker目線の提案リストを準備
        speaker_suggestions: List[Dict[str, Any]] = []
        seen_texts = set()

        # speaker目線の提案のみを収集
        for s in normalized:
            text = s["text"]
            sp = s["speaker"]
            li = s["listener"]
            score = s["score"]
            typ = s["type"]

            # speaker/listenerをstateの値で上書き
            sp = speaker
            li = listener

            if text and text not in seen_texts:
                speaker_suggestions.append(
                    {
                        "text": text,
                        "type": typ,
                        "speaker": sp,
                        "listener": li,
                        "score": score,
                    }
                )
                seen_texts.add(text)

        # filler generator
        def gen_prompt(
            speaker_uid: str, listener_uid: str, topic: str, kind: str
        ) -> str:
            if kind == "shared":
                return f"共通して{topic}に興味があるようですね。普段どのように楽しんでいますか？"
            elif kind == "cross":
                return f"{topic}に興味があると拝見しましたが、特にどのあたりに魅力を感じますか？"
            else:
                return "最近どのように気分転換していますか？よければ教えてください。"

        retry_suffixes = [
            " 詳しく教えていただけますか？",
            " いかがでしょうか？",
            " 具体的にはどのような感じですか？",
            " もしよろしければお聞かせください。",
            " 興味があります。",
            " とても気になります。",
            " 差し支えなければ教えてください。",
            " どんなふうに楽しんでいますか？",
            " きっかけは何でしたか？",
            " ぜひ知りたいです。",
        ]

        topic_cycle = candidate_topics.copy()
        if not topic_cycle:
            topic_cycle = ["最近の趣味", "週末の過ごし方", "おすすめ"]

        # speaker向けの提案が3件になるまで補完
        while len(speaker_suggestions) < 3:
            cur = len(speaker_suggestions)
            kind = "shared" if cur == 0 else ("cross" if cur == 1 else "general")
            if not topic_cycle:
                topic_cycle = candidate_topics.copy()
            topic = topic_cycle.pop(0)
            text = gen_prompt(speaker, listener, topic, kind)

            # テキストが重複しなくなるまで接尾辞を追加して試行する
            base_text = text
            retry_count = 0
            while text in seen_texts:
                retry_count += 1
                # リストの範囲内であればサフィックスを使用
                if retry_count <= len(retry_suffixes):
                    suffix = retry_suffixes[retry_count - 1]
                    text = f"{base_text}{suffix}"
                else:
                    # 範囲を超えた場合は無限ループ防止のため、数値で一意にしてブレーク
                    text = f"{base_text} ({retry_count})"
                    break

            seen_texts.add(text)
            speaker_suggestions.append(
                {
                    "text": text,
                    "type": "topic_shift",
                    "speaker": speaker,
                    "listener": listener,
                    "score": 0.55,
                }
            )

        # スコア順にソートして上位3件を選択
        if len(speaker_suggestions) > 3:
            speaker_suggestions.sort(key=lambda x: x["score"], reverse=True)
            speaker_suggestions = speaker_suggestions[:3]

        final_suggestions = speaker_suggestions

        # final sanity check - speaker向けの提案が3件あることを確認
        safe_topics = (
            candidate_topics
            if candidate_topics
            else ["旅行", "グルメ", "休日の過ごし方", "最近の興味"]
        )

        while len(final_suggestions) < 3:
            # トピック選択（循環）
            topic_idx = len(final_suggestions) % len(safe_topics)
            topic = safe_topics[topic_idx]
            text = gen_prompt(speaker, listener, topic, "general")

            # 重複回避ロジック（再利用）
            base_text = text
            retry_count = 0
            while text in seen_texts:
                retry_count += 1
                if retry_count <= len(retry_suffixes):
                    suffix = retry_suffixes[retry_count - 1]
                    text = f"{base_text}{suffix}"
                else:
                    text = f"{base_text} ({retry_count})"
                    break

            seen_texts.add(text)
            new_sug = {
                "text": text,
                "type": "topic_shift",
                "speaker": speaker,
                "listener": listener,
                "score": 0.5,  # 補完分なので基本スコア
            }
            final_suggestions.append(new_sug)
            logger.warning(
                f"Sanity check filled missing suggestion for speaker {speaker}: {text[:20]}..."
            )

        logger.info(
            f"Profile analysis completed. Generated {len(final_suggestions)} suggestions for speaker {speaker}."
        )

        # enriched_profilesを返す（個々人のクラスタとベクトルを含む）
        return {
            "profiles": enriched_profiles,  # 個々人のクラスタ情報
            "analyzed_meta": profiles_meta,  # 全体の共通クラスタ情報（APIレスポンス用）
            "initial_suggestions": final_suggestions
        }

    except Exception:
        # 1. スタックトレース文字列を手動で取得
        tb_str = traceback.format_exc()

        # 2. メッセージとトレースバック全体をサニタイズ (API Keyマスク)
        safe_tb_str = sanitize_text(tb_str)

        # 3. exc_info=False (デフォルト) で安全なログを出力
        logger.error(f"Error in ProfileAnalyzer:\n{safe_tb_str}")

        # エラー時もstate内のspeaker/listenerを使用
        fallback_speaker = speaker if speaker else "unknown_user"
        fallback_listener = listener if listener else "unknown_user"

        fallback = [
            {
                "text": "少し回線の調子が悪いようです。もう一度話しかけてみてください。",
                "type": "topic_shift",
                "speaker": fallback_speaker,
                "listener": fallback_listener,
                "score": 0.1,
            }
        ]
        return {"initial_suggestions": fallback}


# async def silence_handler(state: ConversationState) -> Dict[str, Any]:
#     """沈黙検知時に即座に介入を行うノード（Fast Path）.
#
#     分析処理（TopicTracker等）をスキップし、ルールベースまたは軽量LLMを用いて
#     場をつなぐための汎用的な話題を即座に生成.
#
#     Args:
#         state (ConversationState): 沈黙が検知された時点の状態.
#
#     Returns:
#         Dict[str, Any]: 更新された状態の差分.
#             - final_suggestions: 沈黙打破のための提案リスト.
#     """
#     logger.info("--- Node: SilenceHandler ---")
#
#     profiles = state.get("profiles", {})
#     visited = state.get("visited_topics", [])
#     user_ids = list(profiles.keys())
#
#     if len(user_ids) < 2:
#         return {"final_suggestions": []}
#
#     # 共通興味の抽出 (簡易ロジック: キーワードの共通集合をとる)
#     # 本来はベクトル計算などが精密だが、ここは高速性重視でキーワードマッチさせる
#     all_keywords = []
#     user_keywords = {}
#
#     for uid, prof in profiles.items():
#         kws = set()
#         for c in prof.get("interest_clusters", []):
#             kws.update(c.get("keywords", []))
#         # SNSデータも加味
#         kws.update(prof.get("sns_data", {}).get("likes", []))
#         user_keywords[uid] = kws
#         all_keywords.extend(list(kws))
#
#     # 共通キーワードを探す
#     common_interests = set()
#     uids = list(user_keywords.keys())
#     if len(uids) >= 2:
#         common_interests = user_keywords[uids[0]].intersection(user_keywords[uids[1]])
#
#     # 共通がなければ全員の興味をプールする
#     target_interests = list(common_interests) if common_interests else all_keywords
#
#     interests_str = ", ".join(target_interests[:10])
#     visited_str = ", ".join(visited)
#
#     speaker = random.choice(user_ids)
#     others = [u for u in user_ids if u != speaker]
#     listener = others[0] if others else speaker
#
#     try:
#         chain = get_silence_chain()
#
#         result: SuggestionList = await chain.ainvoke(
#             {
#                 "common_interests": interests_str,
#                 "visited": visited_str,
#                 "speaker": speaker,
#                 "listener": listener,
#             },
#             config={"timeout": TIMEOUT_LLM},
#         )
#
#         final_suggestions = []
#         for item in result.suggestions:
#             final_suggestions.append(
#                 {
#                     "text": item.text,
#                     "type": "silence_break",
#                     "score": item.score,
#                     "speaker": speaker,  # 明確にこのユーザーの発言とする
#                     "listener": listener,
#                 }
#             )
#
#         return {"final_suggestions": final_suggestions}
#
#     except Exception:
#         error_msg = sanitize_text(traceback.format_exc())
#         logger.error(f"Error in SilenceHandler:\n{error_msg}")
#
#         fallback = [
#             {
#                 "text": "そういえば、最近面白い映画とか観ました？",
#                 "type": "silence_break",
#                 "score": 0.5,
#                 "speaker": speaker,
#                 "listener": listener,
#             }
#         ]
#         return {"final_suggestions": fallback}


# 沈黙対応が不要になったため、silence_handlerをコメントアウト


async def summarizer(state: ConversationState) -> Dict[str, Any]:
    """会話履歴が長くなった場合に要約を行うノード（Maintenance Path）.

    コンテキストウィンドウのトークン節約のため、古い会話履歴を要約し、summaryフィールドを更新した上で生データを削除.

    Args:
        state (ConversationState): 履歴が閾値を超えた状態.

    Returns:
        Dict[str, Any]: 更新された状態の差分.
            - summary: 更新された要約テキスト.
            - history_window: 空リスト（または圧縮後のリスト）.
    """
    logger.info("--- Node: Summarizer ---")

    history = state.get("history_window", [])
    current_summary = state.get("summary", "")

    if len(history) <= HISTORY_KEEP_LAST:
        logger.info(
            f"Skipping summarizer: History length ({len(history)}) "
            f"is not greater than keep_last ({HISTORY_KEEP_LAST})."
        )
        return {}

    # 要約対象: 直近N件を除く古い履歴
    to_summarize = history[:-HISTORY_KEEP_LAST]
    # 次のサイクルに残す履歴
    to_keep = history[-HISTORY_KEEP_LAST:]

    if not to_summarize:
        return {}

    lines = "\n".join([f"{h['speaker']}: {h['text']}" for h in to_summarize])

    llm = get_summarizer_chain()

    try:
        messages = [
            SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
            HumanMessage(
                content=f"【現在の要約】\n{current_summary}\n\n【新しい会話履歴】\n{lines}"
            ),
        ]

        response = await llm.ainvoke(messages)
        new_summary = response.content

        logger.info(
            f"Summary updated. Length: {len(current_summary)} -> {len(new_summary)}"
        )

        # State更新: summaryを更新し、history_windowを短縮したものに置き換える
        return {"summary": new_summary, "history_window": to_keep}

    except Exception:
        error_msg = sanitize_text(traceback.format_exc())
        logger.error(f"Error in Summarizer:\n{error_msg}")

        # エラー時は何もせず（履歴は長いまま）次に進む
        return {}


async def topic_tracker(state: ConversationState) -> Dict[str, Any]:
    """会話のベクトル化とトピック追跡を行うノード.

    最新の発話をEmbedding APIでベクトル化し、現在の会話トピックベクトル(current_topic_vector) を更新.

    Args:
        state (ConversationState): 最新の発話が含まれる状態.

    Returns:
        Dict[str, Any]: 更新された状態の差分.
            - current_topic_vector: 更新後のトピックベクトル.
            - visited_topics: 探索済みトピックの履歴更新.
    """
    logger.info("--- Node: TopicTracker ---")

    latest_text = state.get("latest_text", "").strip()

    # テキストがない場合（沈黙や初期状態）は更新しない
    if not latest_text:
        return {}

    try:
        embeddings_model = get_embeddings_model()

        try:
            new_vector = await asyncio.wait_for(
                embeddings_model.aembed_query(latest_text), timeout=TIMEOUT_EMBEDDING
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Embedding API timed out after {TIMEOUT_EMBEDDING} seconds."
            )
            return {}

        if len(new_vector) != EMBEDDING_DIM:
            logger.warning(
                f"Embedding dimension mismatch. Expected {EMBEDDING_DIM}, got {len(new_vector)}"
            )
            return {}

        # ベクトルの合成 (指数移動平均: EMA)
        prev_vector_list = state.get("current_topic_vector", [])

        updated_vector_list: List[float] = []

        if not prev_vector_list:
            # 初回は最新のベクトルをそのまま使用
            updated_vector_list = new_vector
        else:
            v_prev = np.array(prev_vector_list, dtype=float)
            v_new = np.array(new_vector, dtype=float)

            # EMA計算: Current = α * New + (1 - α) * Prev
            v_updated = (EMA_ALPHA * v_new) + ((1.0 - EMA_ALPHA) * v_prev)

            # ノルムが1になるように正規化（コサイン類似度計算のため）
            norm = np.linalg.norm(v_updated)
            if norm > 1e-9:  # ゼロ除算回避のため、微小値より大きいか確認
                v_updated = v_updated / norm
                updated_vector_list = v_updated.tolist()
            else:
                # 計算結果がゼロベクトルの場合、更新を諦めて前回の値を使う
                logger.warning(
                    "Computed topic vector norm is zero. Keeping previous vector."
                )
                updated_vector_list = prev_vector_list

        # トピック抽出
        chain = get_topic_extractor_chain()

        try:
            topic_result: TopicLabel = await chain.ainvoke(
                {"text": latest_text}, config={"timeout": TIMEOUT_LLM}
            )
        except Exception as e:
            # LLMだけ失敗した場合は、ベクトル更新だけ返してトピック更新はスキップする手もあるが、
            # 今回は安全のため全体をスキップ、またはエラーログを出して終了とする
            logger.warning(f"Topic extraction failed or timed out: {e}")
            return {}
        new_topic_name = topic_result.topic

        # visited_topics の更新 (連続重複の排除)
        current_visited = state.get("visited_topics", [])
        updated_visited = list(current_visited)  # コピーを作成

        if not updated_visited or updated_visited[-1] != new_topic_name:
            updated_visited.append(new_topic_name)
            logger.info(f"Topic updated: {new_topic_name}")
        else:
            logger.info(f"Topic remains: {new_topic_name} (skipped append)")

        return {
            "current_topic_vector": updated_vector_list,
            "visited_topics": updated_visited,
        }

    except Exception:
        tb_str = traceback.format_exc()
        safe_tb_str = sanitize_text(tb_str)
        logger.error(f"Error in TopicTracker:\n{safe_tb_str}")
        return {}


async def generator_deep_dive(state: ConversationState) -> Dict[str, Any]:
    """現在の話題を深掘りする提案を生成するノード.

    speaker目線でlistenerに対する質問を生成する.

    Args:
        state (ConversationState): トピック追跡後の状態.

    Returns:
        Dict[str, Any]: 更新された状態の差分.
            - candidates: 生成されたDeepDiveタイプの提案リスト.
              (State定義により既存リストに追加される)
    """
    logger.info("--- Node: Generator DeepDive ---")

    summary = state.get("summary", "")
    history = state.get("history_window", [])
    latest_text = state.get("latest_text", "")

    # stateからspeaker/listenerを取得
    speaker = state.get("speaker", "")
    listener = state.get("listener", "")

    if not speaker or not listener:
        logger.warning("Speaker or listener not set in state. Cannot generate deep dive suggestions.")
        return {"candidates": []}

    # 履歴のフォーマット
    history_str = "\n".join(
        [f"{h['speaker']}: {h['text']}" for h in history[-HISTORY_CONTEXT_WINDOW:]]
    )

    try:
        chain = get_deep_dive_chain()

        result: SuggestionList = await chain.ainvoke(
            {
                "summary": summary,
                "history": history_str,
                "latest_text": latest_text,
                "speaker": speaker,
                "listener": listener,
            },
            config={"timeout": TIMEOUT_LLM},
        )

        new_candidates: List[Suggestion] = []
        for item in result.suggestions:
            new_candidates.append(
                {
                    "text": item.text,
                    "type": "deep_dive",
                    "score": item.score,
                    "speaker": item.speaker,
                    "listener": item.listener,
                }
            )

        logger.info(f"DeepDive generated {len(new_candidates)} suggestions.")
        return {"candidates": new_candidates}

    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Error in Generator DeepDive:\n{sanitize_text(tb)}")
        return {"candidates": []}


async def generator_topic_shift(state: ConversationState) -> Dict[str, Any]:
    """新しい話題への転換を提案するノード.

    speaker目線でlistenerに対する新しい話題を提案する.
    現在のトピックから距離が遠く、かつユーザーの興味関心が高いカテゴリを選定し、新しい話題への転換を促す質問を生成.

    Args:
        state (ConversationState): トピック追跡後の状態.

    Returns:
        Dict[str, Any]: 更新された状態の差分.
            - candidates: 生成されたTopicShiftタイプの提案リスト.
              (State定義により既存リストに追加される)
    """
    logger.info("--- Node: Generator TopicShift ---")

    profiles = state.get("profiles", {})
    current_topic_vector = state.get("current_topic_vector", [])

    # stateからspeaker/listenerを取得
    speaker = state.get("speaker", "")
    listener = state.get("listener", "")

    if not speaker or not listener:
        logger.warning("Speaker or listener not set in state. Cannot generate topic shift suggestions.")
        return {"candidates": []}

    # 候補となる興味キーワードリスト
    distant_keywords = []

    # 1. ベクトルによるフィルタリング
    if current_topic_vector and len(current_topic_vector) == EMBEDDING_DIM:
        # ベクトルがある場合: コサイン類似度を計算し、類似度が低い（距離が遠い）ものを優先
        v_current = np.array(current_topic_vector)
        norm_current = np.linalg.norm(v_current)

        candidates_with_score = []

        # speakerとlistener両方のプロファイルを確認
        for uid in [speaker, listener]:
            if uid not in profiles:
                continue
            prof = profiles[uid]
            clusters = prof.get("interest_clusters", [])
            for cluster in clusters:
                # clusterは辞書型と想定 (vector, keywords, category)
                c_vec = cluster.get("vector")
                c_keywords = cluster.get("keywords", [])

                if c_vec and len(c_vec) == EMBEDDING_DIM and norm_current > 0:
                    v_cluster = np.array(c_vec)
                    norm_cluster = np.linalg.norm(v_cluster)
                    if norm_current > 1e-9 and norm_cluster > 1e-9:
                        # Cosine Similarity
                        sim = np.dot(v_current, v_cluster) / (
                            norm_current * norm_cluster
                        )
                        sim = max(-1.0, min(1.0, sim))
                        # Topic Shiftしたいので、類似度が低い(=0に近い)ほどスコアを高くする
                        # score = 1 - sim (距離)
                        distance = 1.0 - sim
                        candidates_with_score.append((distance, c_keywords, uid))
                else:
                    # ベクトルがないクラスタは優先度低めで追加
                    candidates_with_score.append((0.5, c_keywords, uid))

        # 距離が大きい順（遠い話題順）にソート
        candidates_with_score.sort(key=lambda x: x[0], reverse=True)

        # 上位3件のクラスタからキーワードを採用
        for dist, keywords, uid in candidates_with_score[:3]:
            keywords_str = ", ".join(keywords)
            distant_keywords.append(
                f"[User: {uid}] {keywords_str} (Distance: {dist:.2f})"
            )

    else:
        # 2. ベクトルがない場合 (Cold Start): speakerとlistenerの興味データを渡す
        for uid in [speaker, listener]:
            if uid not in profiles:
                continue
            prof = profiles[uid]
            # interest_clusters からキーワード抽出
            clusters = prof.get("interest_clusters", [])
            for c in clusters:
                kws = c.get("keywords", [])
                if kws:
                    distant_keywords.append(f"[User: {uid}] {', '.join(kws)}")

            # sns_data からも補完
            sns = prof.get("sns_data", {})
            likes = sns.get("likes", [])
            if likes:
                distant_keywords.append(f"[User: {uid}] Likes: {', '.join(likes)}")

    # 候補が全くない場合のフォールバック
    if not distant_keywords:
        distant_keywords = ["最近のニュース", "週末の予定", "美味しいお店", "旅行"]

    try:
        chain = get_topic_shift_chain()

        # LLMには「遠いトピックのリスト」のみを渡す
        candidates_text = "\n".join(distant_keywords)

        result: SuggestionList = await chain.ainvoke(
            {"candidates": candidates_text, "speaker": speaker, "listener": listener},
            config={"timeout": TIMEOUT_LLM},
        )

        new_candidates: List[Suggestion] = []
        for item in result.suggestions:
            new_candidates.append(
                {
                    "text": item.text,
                    "type": "topic_shift",
                    "score": item.score,
                    "speaker": item.speaker,
                    "listener": item.listener,
                }
            )

        logger.info(f"TopicShift generated {len(new_candidates)} suggestions.")
        return {"candidates": new_candidates}

    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Error in Generator TopicShift:\n{sanitize_text(tb)}")
        return {"candidates": []}


async def adaptive_scorer(state: ConversationState) -> Dict[str, Any]:
    """候補の中から最適な提案を選出するノード。

    並列実行されたGeneratorsから集まった候補(candidates)に対し、文脈適合度や安全性スコアを計算し、上位の提案を選定.

    Args:
        state (ConversationState): 全ての候補が出揃った状態.

    Returns:
        Dict[str, Any]: 更新された状態の差分.
            - final_suggestions: クライアントに返却する最終提案リスト.
    """
    logger.info("--- Node: AdaptiveScorer ---")

    candidates = state.get("candidates", [])
    if not candidates:
        logger.warning("No candidates to score.")
        return {"final_suggestions": []}

    current_topic_vector = state.get("current_topic_vector", [])
    profiles = state.get("profiles", {})
    embeddings_model = get_embeddings_model()

    scored_suggestions = []

    try:
        # スコア計算
        for cand in candidates:
            text = cand["text"]
            cand_type = cand["type"]
            listener_id = cand["listener"]

            # 1. ベクトル化
            try:
                cand_vector = await asyncio.wait_for(
                    embeddings_model.aembed_query(text), timeout=TIMEOUT_EMBEDDING
                )
            except Exception as e:
                logger.warning(f"Failed to embed: {e}")
                continue

            # 2. Context Similarity (今の話題に近いか？)
            sim_context = calculate_cosine_similarity(cand_vector, current_topic_vector)

            # 3. Profile Similarity (興味に近いか？)
            sim_profile = 0.0
            target_profile = profiles.get(listener_id)
            if target_profile:
                clusters = target_profile.get("interest_clusters", [])
                max_sim = 0.0
                for cluster in clusters:
                    c_vec = cluster.get("vector")
                    if c_vec:
                        s = calculate_cosine_similarity(cand_vector, c_vec)
                        if s > max_sim:
                            max_sim = s
                sim_profile = max_sim

            if sim_profile < SCORE_SIM_THRESHOLD:
                sim_profile = 0.0

            # 4. 総合スコア計算
            base_score = float(cand.get("score", 0.5))
            algo_score = 0.0

            if cand_type == "deep_dive":
                # Deep Dive: 興味に近い + 今の話題に近い
                boosted_ctx_sim = min(1.0, sim_context * DEEP_DIVE_CONTEXT_BOOST)
                algo_score = (WEIGHT_DD_PROFILE * sim_profile) + (
                    WEIGHT_DD_CONTEXT * boosted_ctx_sim
                )

            elif cand_type == "topic_shift":
                # Topic Shift: 興味に近い + 今の話題から遠い
                dist_context = max(0.0, 1.0 - sim_context)

                if sim_profile == 0.0:
                    algo_score = 0.0  # 興味がないなら話題転換先として不適格
                else:
                    algo_score = (WEIGHT_TS_PROFILE * sim_profile) + (
                        WEIGHT_TS_DISTANCE * dist_context
                    )

            final_score = (algo_score * WEIGHT_FINAL_ALGO) + (
                base_score * WEIGHT_FINAL_BASE
            )

            # ログ出力
            logger.info(
                f"Scoring '{text[:15]}...': Final={final_score:.3f} "
                f"(CtxSim={sim_context:.2f}, ProfSim={sim_profile:.2f}, Type={cand_type})"
            )

            cand_copy = cand.copy()
            cand_copy["score"] = round(final_score, 3)
            scored_suggestions.append(cand_copy)

        # 5. ソートとフィルタリング
        scored_suggestions.sort(key=lambda x: x["score"], reverse=True)
        final_selection = scored_suggestions[:3]

        return {"final_suggestions": final_selection}

    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Error in AdaptiveScorer:\n{sanitize_text(tb)}")
        return {"final_suggestions": candidates[:3] if candidates else []}
