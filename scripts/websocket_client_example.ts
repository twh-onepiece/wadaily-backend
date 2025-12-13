/**
 * WebSocket話題提案クライアントのサンプル実装
 * 既存のHTTP APIと同じ内部処理（profile_analyzer + LangGraph）を使用
 *
 * 使い方:
 * 1. セッションを作成
 * 2. WebSocket接続を確立
 * 3. 会話データを送信（conversations形式）
 * 4. 進捗とsuggestions提案をリアルタイム受信
 * 5. 通話終了時にcloseSession()を呼ぶ
 */

interface ConversationMessage {
  user_id: string;
  text: string;
  timestamp: number;  // Unix timestamp in milliseconds
}

interface SuggestionResponse {
  id: number;
  text: string;
  type: string;
  speaker: string;
  listener: string;
  score: number;
}

interface ProgressMessage {
  type: 'progress';
  message: string;
  node?: string;
}

interface SuggestionsMessage {
  type: 'suggestions';
  status: string;
  current_topic: string;
  suggestions: SuggestionResponse[];
  timestamp: string;
}

interface ErrorMessage {
  type: 'error';
  error: string;
  session_id: string;
}

type WebSocketMessage = ProgressMessage|SuggestionsMessage|ErrorMessage;

class RealTimeTopicSuggestionClient {
  private ws: WebSocket|null = null;
  private sessionId: string = '';

  /**
   * セッションを作成してWebSocket接続を確立
   */
  async createSession(users: Array<{user_id: string, sns_data: any}>):
      Promise<string> {
    // 1. HTTPでセッション作成（既存APIと同じ）
    const response = await fetch('http://localhost:8000/sessions/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({users}),
    });

    if (!response.ok) {
      throw new Error(`Failed to create session: ${response.statusText}`);
    }

    const data = await response.json();
    this.sessionId = data.session_id;

    console.log('✅ Session created:', this.sessionId);
    console.log('Common interests:', data.common_interests);
    console.log('Initial suggestions:', data.initial_suggestions?.length);

    // 2. WebSocket接続を確立
    await this.connectWebSocket();

    return this.sessionId;
  }

  /**
   * WebSocket接続を確立
   */
  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = `ws://localhost:8000/sessions/${this.sessionId}/topics`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('✅ WebSocket connected');
        resolve();
      };

      this.ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        reject(error);
      };

      this.ws.onmessage = (event) => {
        const data: WebSocketMessage = JSON.parse(event.data);

        if (data.type === 'progress') {
          // 進捗を表示
          this.onProgress(data.message, data.node);
        } else if (data.type === 'suggestions') {
          // 提案を受信
          this.onReceivedSuggestions(data);
        } else if (data.type === 'error') {
          console.error('❌ Server error:', data.error);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket closed');
      };
    });
  }

  /**
   * 会話を送信（conversations形式）
   */
  sendConversations(conversations: ConversationMessage[]): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('❌ WebSocket is not connected');
      return;
    }

    const message = {conversations: conversations};

    console.log('📤 Sending conversations:', conversations.length, 'items');
    this.ws.send(JSON.stringify(message));
  }

  /**
   * 進捗通知のコールバック
   */
  onProgress(message: string, node?: string): void {
    console.log('📊 Progress:', message, node ? `(${node})` : '');
    // UIに進捗を表示
    // updateProgressUI(message);
  }

  /**
   * 提案を受信したときのコールバック
   * アプリケーション側でこのメソッドをオーバーライドする
   */
  onReceivedSuggestions(data: SuggestionsMessage): void {
    console.log('📨 Received suggestions:');
    console.log('  Current topic:', data.current_topic);
    console.log('  Suggestions:');
    data.suggestions.forEach((sug, index) => {
      console.log(
          `    ${index + 1}. [${sug.speaker} → ${sug.listener}] ${sug.text}`);
      console.log(`       type: ${sug.type}, score: ${sug.score}`);
    });

    // ここでUIを更新
    // displaySuggestionsInUI(data.suggestions);
  }

  /**
   * セッションを終了
   */
  closeSession(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    console.log('✅ Session closed');
  }
}

// ===== 使用例 =====

async function example() {
  const client = new RealTimeTopicSuggestionClient();

  // カスタムコールバックを設定
  client.onProgress = (message: string, node?: string) => {
    console.log(`🔄 ${message}`, node ? `[${node}]` : '');
    // showProgressInUI(message);
  };

  client.onReceivedSuggestions = (data: SuggestionsMessage) => {
    console.log('🎯 提案を受信:');
    console.log('   トピック:', data.current_topic);
    data.suggestions.forEach((sug, i) => {
      console.log(`   ${i + 1}. ${sug.text}`);
    });
    // displaySuggestionsInUI(data.suggestions, data.current_topic);
  };

  try {
    // 1. セッション作成
    const sessionId = await client.createSession([
      {
        user_id: 'user_A',
        sns_data: {
          posts: ['キャンプ楽しかった', '新しいテント買った'],
          likes: ['アウトドア', '自然'],
        },
      },
      {
        user_id: 'user_B',
        sns_data: {
          posts: ['登山行ってきた', '山の写真撮影'],
          likes: ['山', '写真'],
        },
      },
    ]);

    console.log(`✅ Session ready: ${sessionId}`);

    // 2. 会話を送信（conversations形式）
    await new Promise(resolve => setTimeout(resolve, 1000));

    client.sendConversations([
      {
        user_id: 'user_A',
        text: 'こんにちは！',
        timestamp: Date.now(),
      },
      {
        user_id: 'user_B',
        text: '元気？週末どうだった？',
        timestamp: Date.now() + 1000,
      },
      {
        user_id: 'user_A',
        text: 'キャンプに行ってきたよ！',
        timestamp: Date.now() + 2000,
      },
    ]);

    // 3. さらに会話を送信
    await new Promise(resolve => setTimeout(resolve, 5000));

    client.sendConversations([
      {
        user_id: 'user_B',
        text: 'どこでキャンプしたの？',
        timestamp: Date.now(),
      },
      {
        user_id: 'user_A',
        text: '山梨の方だよ',
        timestamp: Date.now() + 1000,
      },
      {
        user_id: 'user_B',
        text: 'いいね！景色良かった？',
        timestamp: Date.now() + 2000,
      },
    ]);

    // 4. 通話終了
    await new Promise(resolve => setTimeout(resolve, 5000));
    client.closeSession();
  } catch (error) {
    console.error('❌ Error:', error);
  }
}

// Node.js環境で実行する場合
if (typeof window === 'undefined') {
  const WebSocket = require('ws');
  (global as any).WebSocket = WebSocket;

  example().catch(console.error);
}

export {RealTimeTopicSuggestionClient, ConversationMessage, SuggestionResponse};
