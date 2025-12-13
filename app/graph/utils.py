import math
import re
import numpy as np
from typing import List
from typing import Any
from app.graph.state import ConversationState


def safe_float(value: Any, default: float = 0.5) -> float:
    """
    値を安全にfloatに変換する。
    変換失敗、NaN、Inf の場合は default 値を返す。
    """
    try:
        val = float(value)
        if not math.isfinite(val):
            return default
        return val
    except (ValueError, TypeError):
        return default


def sanitize_text(text: str) -> str:
    """
    テキスト内の機密情報（APIキーなど）をマスクする。
    エラーメッセージだけでなく、スタックトレース全体にも適用可能。
    """
    if not text:
        return ""
    # OpenAI API Key (sk-...) のパターンを検出してマスク
    # 誤検知を防ぐため、20文字以上の長さに限定 (sk-proj-... 等の長いキーにも対応)
    text = re.sub(r"sk-[a-zA-Z0-9\-_]{20,100}", "sk-***", text)
    return text


def determine_speaker_listener(state: ConversationState) -> tuple[str, str]:
    """
    次の発話者(speaker)と聞き手(listener)を決定する。
    """
    history = state.get("history_window", [])
    profiles = state.get("profiles", {})
    all_users = list(profiles.keys())

    if not all_users:
        return "unknown", "unknown"

    # デフォルト
    speaker = all_users[0]
    listener = all_users[1] if len(all_users) > 1 else all_users[0]

    # 履歴がある場合、直前の発言者以外をSpeakerにする
    if history:
        last_turn = history[-1]
        last_speaker = last_turn.get("speaker")

        candidates = [u for u in all_users if u != last_speaker]
        if candidates:
            speaker = candidates[0]
            listener = last_speaker

    return speaker, listener


def calculate_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    2つのベクトルのコサイン類似度を計算する。
    ゼロベクトルが含まれる場合は 0.0 を返す。
    """
    if not vec_a or not vec_b:
        return 0.0

    if len(vec_a) != len(vec_b):
        return 0.0

    a = np.array(vec_a)
    b = np.array(vec_b)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))
