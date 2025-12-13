import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.schemas.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    SuggestionResponse,
    WebSocketConversationsRequest,
    DeleteSessionResponse,
)
from app.graph.workflow import get_graph_app
from app.graph.state import get_initial_state
from app.graph.nodes import profile_analyzer
from langgraph.graph.state import CompiledStateGraph

from app.services.session_store import SessionStore
from app.config import OPENAI_API_KEY, AUTO_DELETE_SESSION_ON_DISCONNECT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """新規セッションを作成し、初期分析を実行.
    SNSデータに基づいた共通点抽出や初期話題の生成を行う.
    speaker目線での提案を生成する.

    Args:
        request (CreateSessionRequest): speaker/listenerとSNSデータを含むリクエストボディ.

    Returns:
        CreateSessionResponse: 発行されたセッションID、初期ステータス、および初期提案を含むレスポンス.
    """

    session_id = str(uuid.uuid4())

    # 1. Nodeに入力するための「仮のState」を作成
    # speaker/listenerを state["profiles"] (Nodeの入力形式) に変換
    initial_profiles = {}
    
    # speakerの情報を追加
    speaker = request.speaker
    speaker_likes = speaker.sns_data.likes if speaker.sns_data else []
    speaker_posts = speaker.sns_data.posts if speaker.sns_data else []
    initial_profiles[speaker.user_id] = {
        "user_id": speaker.user_id,
        "interest_clusters": [],
        "sns_data": {"likes": speaker_likes, "posts": speaker_posts},
    }
    
    # listenerの情報を追加
    listener = request.listener
    listener_likes = listener.sns_data.likes if listener.sns_data else []
    listener_posts = listener.sns_data.posts if listener.sns_data else []
    initial_profiles[listener.user_id] = {
        "user_id": listener.user_id,
        "interest_clusters": [],
        "sns_data": {"likes": listener_likes, "posts": listener_posts},
    }

    # Nodeが期待するState構造を構築
    temp_state = {
        "profiles": initial_profiles,
        "latest_text": "",  # 初期状態なのでテキストなし
        "speaker": speaker.user_id,  # speaker目線での提案
        "listener": listener.user_id,
    }

    try:
        analysis_result = await profile_analyzer(temp_state)

    except Exception as e:
        logger.error(f"Profile analysis node failed: {e}")
        raise HTTPException(status_code=500, detail="Profile analysis failed")


    # Nodeの戻り値: 
    # {"profiles": {user_id: {clusters, sns_data}}, "analyzed_meta": {...}, "initial_suggestions": [...]}
    enriched_profiles = analysis_result.get("profiles", {})
    analyzed_profiles_meta = analysis_result.get("analyzed_meta", {})
    suggestions_data = analysis_result.get("initial_suggestions", [])

    # クラスタから共通の興味を抽出
    display_interests = []
    clusters = analyzed_profiles_meta.get("clusters", [])
    for cluster in clusters:
        if isinstance(cluster, dict):
            # clusterに "category" や "topics" が含まれる想定
            if "category" in cluster:
                display_interests.append(cluster["category"])
            topics = cluster.get("topics", [])
            display_interests.extend(topics[:2])  # 上位2つのトピックを追加
        elif isinstance(cluster, str):
            display_interests.append(cluster)

    # 重複除去して最大5件に制限
    display_interests = list(set(display_interests))[:5]

    # 3. Redisに保存するデータを作成
    # Nodeの結果を永続化（enriched_profilesにはクラスタとベクトルが含まれる）
    initial_data = {
        "profiles": enriched_profiles,  # 個々人のクラスタとベクトルを含むプロファイル
        "analyzed_meta": analyzed_profiles_meta,  # クラスタ情報を別で保存
        "common_interests": display_interests,
        "visited_topics": [],  # 初期状態は空
        "current_topic_vector": [],  # 初期状態は空
        "conversation_history": [],  # 会話履歴を永続化
        "summary": "",  # 要約の初期値
        "speaker": speaker.user_id,  # speaker目線での提案
        "listener": listener.user_id,
    }

    await SessionStore.save_session(session_id, initial_data)

    # 4. レスポンス生成
    # Nodeが生成した suggestions を APIレスポンス形式に変換（speaker/listenerなし）
    response_suggestions = []
    for idx, sug in enumerate(suggestions_data):
        response_suggestions.append(
            SuggestionResponse(
                id=idx + 1,
                text=sug.get("text", ""),
                type=sug.get("type", "topic_shift"),
                score=sug.get("score"),  # Noneを許容
            )
        )

    return CreateSessionResponse(
        session_id=session_id,
        status="initialized",
        common_interests=display_interests,
        initial_suggestions=response_suggestions,
    )


@router.websocket("/{session_id}/topics")
async def websocket_topic_suggestions(
    websocket: WebSocket,
    session_id: str,
):
    """WebSocketで会話を受信し、既存のLangGraphを使ってリアルタイムに提案を生成.

    既存のHTTP APIと同じ内部処理（profile_analyzer、LangGraph）を使用し、
    結果をWebSocketでストリーミング配信する.

    Args:
        websocket (WebSocket): WebSocket接続.
        session_id (str): セッションID.

    WebSocketメッセージフォーマット:
        受信:
        {
            "conversations": [
                {"user_id": "A", "text": "AAA", "timestamp": 1702454400000},
                {"user_id": "B", "text": "BBB", "timestamp": 1702454405000},
                ...
            ]
        }
        送信（完了）:
        {
            "type": "suggestions",
            "status": "active",
            "current_topic": "アウトドア",
            "suggestions": [...]
        }
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    try:
        # セッションの存在確認
        session_data = await SessionStore.load_session(session_id)
        if not session_data:
            await websocket.send_json({
                "type": "error",
                "error": "Session not found",
                "session_id": session_id
            })
            await websocket.close(code=1008)  # Policy Violation
            return

        # LangGraphを取得（既存のHTTP APIと同じ）
        graph = get_graph_app()

        while True:
            # クライアントからメッセージを受信
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket data: {data}")
            logger.info(f"Received message from session {session_id}: {len(data.get('conversations', []))} conversations")

            try:
                # リクエストをバリデーション
                request = WebSocketConversationsRequest(**data)

                # conversationsをTranscriptItem形式に変換
                input_type = "text"
                latest_text = ""
                new_turns = []
                
                for conv in request.conversations:
                    new_turns.append({
                        "speaker": conv.user_id,
                        "text": conv.text,
                        "timestamp": conv.timestamp
                    })
                
                if new_turns:
                    latest_text = new_turns[-1]["text"]

                # 永続化された会話履歴を取得
                persisted_history = session_data.get("conversation_history", [])
                
                # 新しい会話を履歴に追加
                existing_timestamps = {turn["timestamp"] for turn in persisted_history}
                for turn in new_turns:
                    if turn["timestamp"] not in existing_timestamps:
                        persisted_history.append(turn)
                
                history_window = persisted_history[-5:] if persisted_history else []

                # LangGraphを実行（既存のHTTP APIと同じ）
                initial_state = get_initial_state()
                initial_state.update({
                    "input_type": input_type,
                    "latest_text": latest_text,
                    "history_window": history_window,
                    "summary": session_data.get("summary", ""),
                    "profiles": session_data.get("profiles", {}),
                    "visited_topics": session_data.get("visited_topics", []),
                    "current_topic_vector": session_data.get("current_topic_vector", []),
                    "speaker": session_data.get("speaker", ""),
                    "listener": session_data.get("listener", ""),
                })

                # ストリーミング実行
                final_result = None
                async for chunk in graph.astream(initial_state):
                    final_result = chunk

                # 最終結果を取得
                if final_result:
                    result_key = list(final_result.keys())[0]
                    result = final_result[result_key]
                else:
                    result = {}

                final_suggestions = result.get("final_suggestions", [])
                visited_topics = result.get("visited_topics", [])
                current_topic = visited_topics[-1] if visited_topics else "一般"

                # Redisに保存
                session_data["visited_topics"] = visited_topics
                session_data["current_topic_vector"] = result.get("current_topic_vector", [])
                session_data["summary"] = result.get("summary", session_data.get("summary", ""))
                session_data["conversation_history"] = persisted_history
                await SessionStore.save_session(session_id, session_data)

                # レスポンス形式に変換（WebSocket用: speaker/listenerなし）
                response_suggestions = []
                for idx, sug in enumerate(final_suggestions):
                    response_suggestions.append(
                        SuggestionResponse(
                            id=idx + 1,
                            text=sug.get("text", ""),
                            type=sug.get("type", "topic_shift"),
                            score=sug.get("score"),  # Noneを許容
                        ).model_dump()
                    )

                # 最終結果を送信（TranscriptUpdateResponseと同じ構造）
                response_data = {
                    "status": "active",
                    "current_topic": current_topic,
                    "suggestions": response_suggestions,
                }
                logger.info(f"Sending WebSocket response: {response_data}")
                await websocket.send_json(response_data)

                logger.info(f"Sent {len(response_suggestions)} suggestions to session {session_id}")

            except Exception as e:
                logger.error(f"Error processing message for session {session_id}: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "error": str(e),
                    "session_id": session_id
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
        
        # 設定により自動削除を実行
        if AUTO_DELETE_SESSION_ON_DISCONNECT:
            logger.info(f"Auto-deleting session {session_id} on disconnect")
            await SessionStore.delete_session(session_id)
            
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
        try:
            await websocket.close(code=1011)  # Internal Error
        except:
            pass


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str):
    """セッションを終了し、Redisから関連データを削除する.
    
    Args:
        session_id (str): 削除するセッションID.
        
    Returns:
        DeleteSessionResponse: 削除結果を含むレスポンス.
        
    Raises:
        HTTPException: セッションが見つからない場合は404エラー.
    """
    logger.info(f"Attempting to delete session {session_id}")
    
    # セッションの存在確認
    session_data = await SessionStore.load_session(session_id)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    # セッションを削除
    deleted = await SessionStore.delete_session(session_id)
    
    if deleted:
        return DeleteSessionResponse(
            session_id=session_id,
            deleted=True,
            message="Session successfully deleted"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session"
        )
