"""
sessions APIのテスト

Redisとprofile_analyzer、LangGraphをモック化しているため、
外部依存なしでテスト可能です。
"""

import pytest
import json
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app


@pytest.fixture
def mock_redis():
    """Redisクライアントをモック化"""
    storage = {}

    async def mock_set(key, value, ex=None):
        storage[key] = value
        return True

    async def mock_get(key):
        return storage.get(key)

    async def mock_delete(key):
        if key in storage:
            del storage[key]
            return 1
        return 0

    mock = MagicMock()
    mock.set = mock_set
    mock.get = mock_get
    mock.delete = mock_delete
    return mock


@pytest.fixture
def mock_profile_analyzer():
    """profile_analyzerをモック化"""

    async def mock_analyzer(state):
        # speaker/listenerの2人分のプロファイルを返す
        profiles = state.get("profiles", {})
        enriched_profiles = {}
        
        for user_id in profiles.keys():
            enriched_profiles[user_id] = {
                "user_id": user_id,
                "sns_data": profiles[user_id].get("sns_data", {"posts": [], "likes": []}),
                "interest_clusters": [
                    {
                        "category": "アウトドア",
                        "keywords": ["キャンプ", "登山"],
                        "vector": [0.1] * 1536
                    }
                ]
            }
        
        return {
            "profiles": enriched_profiles,
            "analyzed_meta": {
                "clusters": [
                    {"category": "アウトドア", "topics": ["キャンプ", "登山"]},
                    {"category": "テクノロジー", "topics": ["AI", "プログラミング"]},
                ],
            },
            "initial_suggestions": [
                {
                    "text": "最近キャンプに行かれましたか？",
                    "type": "topic_shift",
                    "speaker": "user1",
                    "listener": "user2",
                    "score": 0.8,
                },
                {
                    "text": "AIについてどう思いますか？",
                    "type": "deep_dive",
                    "speaker": "user1",
                    "listener": "user2",
                    "score": 0.75,
                },
            ],
        }

    return mock_analyzer


@pytest.fixture
def mock_graph():
    """LangGraphをモック化"""

    async def mock_invoke(state):
        return {
            "final_suggestions": [
                {
                    "text": "その話題について詳しく聞かせてください",
                    "type": "deep_dive",
                    "speaker": "user1",
                    "listener": "user2",
                    "score": 0.85,
                },
            ],
            "visited_topics": ["アウトドア", "テクノロジー"],
            "current_topic_vector": [0.1] * 1536,
            "summary": "アウトドアとテクノロジーについて話した",
        }

    mock = AsyncMock()
    mock.ainvoke = mock_invoke
    return mock


@pytest.mark.asyncio
async def test_create_session(mock_profile_analyzer, mock_redis):
    """セッション作成のテスト"""
    with patch("app.routers.sessions.profile_analyzer", mock_profile_analyzer), patch(
        "app.services.session_store.SessionStore._client", mock_redis
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/sessions/",
                json={
                    "speaker": {
                        "user_id": "user1",
                        "sns_data": {
                            "posts": ["キャンプ楽しかった", "新しいMacBook買った"],
                            "likes": ["アウトドア", "Apple"],
                        },
                    },
                    "listener": {
                        "user_id": "user2",
                        "sns_data": {
                            "posts": ["登山行ってきた", "AI勉強中"],
                            "likes": ["自然", "テクノロジー"],
                        },
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()

            # レスポンスの基本構造を確認
            assert "session_id" in data
            assert data["status"] == "initialized"
            assert "common_interests" in data
            assert "initial_suggestions" in data

            # common_interestsが抽出されていることを確認
            assert len(data["common_interests"]) > 0

            # initial_suggestionsの構造を確認
            assert len(data["initial_suggestions"]) > 0
            suggestion = data["initial_suggestions"][0]
            assert "id" in suggestion
            assert "text" in suggestion
            assert "type" in suggestion
            assert "score" in suggestion
            # speaker/listenerはsessionで決まっているため、提案には含まれない


@pytest.mark.asyncio
async def test_delete_session(mock_profile_analyzer, mock_redis):
    """セッション削除のテスト"""
    with patch("app.routers.sessions.profile_analyzer", mock_profile_analyzer), patch(
        "app.services.session_store.SessionStore._client", mock_redis
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. セッションを作成
            create_response = await client.post(
                "/sessions/",
                json={
                    "speaker": {
                        "user_id": "user1",
                        "sns_data": {
                            "posts": ["キャンプ楽しかった"],
                            "likes": ["アウトドア"],
                        },
                    },
                    "listener": {
                        "user_id": "user2",
                        "sns_data": {
                            "posts": ["登山行ってきた"],
                            "likes": ["自然"],
                        },
                    },
                },
            )
            
            assert create_response.status_code == 200
            session_id = create_response.json()["session_id"]
            
            # 2. セッションを削除
            delete_response = await client.delete(f"/sessions/{session_id}")
            
            assert delete_response.status_code == 200
            delete_data = delete_response.json()
            assert delete_data["session_id"] == session_id
            assert delete_data["deleted"] is True
            assert "successfully deleted" in delete_data["message"]


@pytest.mark.asyncio
async def test_delete_nonexistent_session(mock_redis):
    """存在しないセッションの削除テスト"""
    with patch("app.services.session_store.SessionStore._client", mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 存在しないセッションIDで削除を試みる
            delete_response = await client.delete("/sessions/nonexistent-session-id")
            
            assert delete_response.status_code == 404
            error_data = delete_response.json()
            assert "not found" in error_data["detail"]


# HTTP API用のupdate_transcriptエンドポイントは削除されたため、テストも削除
# WebSocket経由でのみ会話更新が可能
