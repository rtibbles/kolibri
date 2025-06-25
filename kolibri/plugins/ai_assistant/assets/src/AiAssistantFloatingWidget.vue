<template>

  <div class="ai-assistant-widget">
    <!-- Floating Icon -->
    <div
      v-if="!isExpanded"
      class="floating-icon"
      @click="toggleExpanded"
    >
      <KLogo :altText="$tr('assistantName')"/>
    </div>

    <!-- Expanded Chat Window -->
    <div
      v-if="isExpanded"
      class="chat-window"
    >
      <div class="chat-header" :style="{ background: $themeTokens.primary }">
        <h3>{{ $tr('assistantName') }}</h3>
        <button
          class="close-button"
          @click="toggleExpanded"
        >
          ×
        </button>
      </div>

      <div
        ref="messagesContainer"
        class="chat-messages"
      >
        <div
          v-for="message in messages"
          :key="message.id"
          class="message"
        >
          <div :class="['message-bubble', message.type]" :style="{ background: message.type === 'user' ? $themeTokens.primary : $themeTokens.secondary }">
            {{ message.text }}
          </div>
          <ContentCardList
            v-if="message.type === 'ai' && message.relevant_content"
            :contentList="message.relevant_content"
          />
        </div>
        <div
          v-if="isLoading"
          class="message"
        >
          <div class="ai loading message-bubble">Thinking...</div>
        </div>
      </div>

      <div class="chat-input">
        <input
          ref="messageInput"
          v-model="currentMessage"
          type="text"
          placeholder="Ask me anything..."
          :disabled="isLoading"
          @keyup.enter="sendMessage"
        >
        <KButton
          :disabled="!currentMessage.trim() || isLoading"
          class="send-button"
          :primary="true"
          @click="sendMessage"
        >
          {{ $tr('send') }}
        </KButton>
      </div>
    </div>
  </div>

</template>


<script>

  import uFuzzy from '@leeoniya/ufuzzy/dist/uFuzzy.cjs';
  import client from 'kolibri/client';
  import urls from 'kolibri/urls';
  import { LearningActivities, ContentLevels, Categories } from 'kolibri/constants';
  import { coreString } from 'kolibri/uiText/commonCoreStrings';
  import ContentCardList from './ContentCardList.vue';

  export default {
    name: 'AiAssistantFloatingWidget',
    components: {
      ContentCardList,
    },
    data() {
      return {
        isExpanded: false,
        messages: [],
        currentMessage: '',
        messageId: 0,
        isLoading: false,
        haystack: null,
      };
    },
    methods: {
      toggleExpanded() {
        this.isExpanded = !this.isExpanded;
        if (this.isExpanded) {
          this.$nextTick(() => {
            if (this.$refs.messageInput) {
              this.$refs.messageInput.focus();
            }
          });
        }
      },

      async sendMessage() {
        if (!this.currentMessage.trim() || this.isLoading) return;

        // Add user message
        this.messages.push({
          id: this.messageId++,
          text: this.currentMessage,
          type: 'user',
        });

        const userMessage = this.currentMessage;
        this.currentMessage = '';
        this.isLoading = true;

        // Scroll to bottom
        this.scrollToBottom();

        try {
          const data = await this.callAiApi(userMessage);
          
          for (const datum of data) {
            // Add AI response
            this.messages.push({
              id: this.messageId++,
              text: datum.response,
              type: 'ai',
              relevant_content: datum.relevant_content,
            });
          }
        } catch (error) {
          this.messages.push({
            id: this.messageId++,
            text: 'Sorry, I encountered an error. Please try again.',
            type: 'ai error',
          });
        } finally {
          this.isLoading = false;
          this.scrollToBottom();
        }
      },

      async callAiApi(message) {
        // Extract context parameters using fuzzy matching
        const contextParams = this.extractContextFromMessage(message);
        const response = await client({url: urls['kolibri:kolibri.plugins.ai_assistant:ai_assistant_chat'](), method: 'POST', data:{
          message,
          ...contextParams,
        }});

        return response.data;
      },

      extractContextFromMessage(message) {
        // Build haystack of translated search terms mapped to API parameters
        const haystack = this.getSearchHaystack();

        // Use fuzzy matching to find relevant context
        const uf = new uFuzzy();
        const [idxs, info, order] = uf.search(haystack.terms, message);

        const contextParams = {};


        // Take top matches above a certain threshold
        for (const idx of order) {
          const match = haystack.mappings[idxs[idx]];
          // threshold for relevance
          const field = match.field;
          const value = match.value;

          // Group values by field
          if (!contextParams[field]) {
            contextParams[field] = [];
          }
          contextParams[field].push(value);
        }

        return contextParams;
      },

      getSearchHaystack() {
        if (this.haystack) {
          return this.haystack;
        }
        const mappings = [];

        const contentKinds = {
          [this.$tr('video')]: 'video',
          [this.$tr('audio')]: 'audio',
          [this.$tr('document')]: 'document',
          [this.$tr('exercise')]: 'exercise',
          [this.$tr('html5')]: 'html5',
        };

        // Add content kind terms
        for (const [text, value] of Object.entries(contentKinds)) {
          mappings.push({ text, field: 'kind', value });
        }

        // Add learning activities
        for (const [key, value] of Object.entries(LearningActivities)) {
          const text = coreString(key);
          mappings.push({ text, field: 'learning_activities', value });
        }
        // Add content levels (grade levels)
        for (const [key, value] of Object.entries(ContentLevels)) {
          const text = coreString(key);
          mappings.push({ text, field: 'grade_levels', value });
        }

        // Add categories/subjects
        for (const [key, value] of Object.entries(Categories)) {
          const text = coreString(key);
          mappings.push({ text, field: 'categories', value });
        }

        this.haystack = { mappings, terms: mappings.map(m => m.text) };
        return this.haystack;
      },

      scrollToBottom() {
        this.$nextTick(() => {
          if (this.$refs.messagesContainer) {
            this.$refs.messagesContainer.scrollTop = this.$refs.messagesContainer.scrollHeight;
          }
        });
      },
    },
    $trs: {
      exercise: {
        message: 'Exercise',
        context: 'An exercise is an interactive formative assessment resource.',
      },
      video: {
        message: 'Video',
        context: 'A video is a type of learning resource available in Kolibri.',
      },
      audio: {
        message: 'Audio',
        context: 'Audio is a type of education material available in Kolibri.',
      },
      document: {
        message: 'Document',
        context: 'A document is a type of learning resource available in Kolibri.',
      },
      html5: {
        message: 'App',
        context: 'Apps are interactive HTML and Javascript applications.',
      },
      send: {
        message: 'Send',
        context: 'Button to send the current message in the chat.',
      },
      assistantName: {
        message: 'KolibrAI',
        context: 'The name of the AI assistant widget.',
      },
    },
  };

</script>


<style scoped>

  .ai-assistant-widget {
    position: fixed;
    right: 20px;
    bottom: 20px;
    z-index: 9999;
  }

  .floating-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 60px;
    height: 60px;
    color: white;
    background: white;
    cursor: pointer;
    border-radius: 50%;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
  }

  .floating-icon:hover {
    box-shadow: 0 6px 25px rgba(0, 0, 0, 0.2);
    transform: scale(1.1);
  }

  .chat-window {
    position: absolute;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    width: 350px;
    height: 500px;
    overflow: hidden;
    background: white;
    border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
  }

  .chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    color: white;
  }

  .chat-header h3 {
    margin: 0;
    font-size: 16px;
  }

  .close-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    padding: 0;
    font-size: 24px;
    color: white;
    cursor: pointer;
    background: none;
    border: none;
    border-radius: 50%;
    transition: background-color 0.2s ease;
  }

  .close-button:hover {
    background-color: rgba(255, 255, 255, 0.2);
  }

  .chat-messages {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    overflow-y: auto;
  }

  .message-bubble {
    max-width: 80%;
    padding: 12px 16px;
    word-wrap: break-word;
    border-radius: 18px;
  }

  .message-bubble.user {
    margin-left: auto;
    color: white;
    border-bottom-right-radius: 6px;
  }

  .message-bubble.ai {
    color: #333333;
    border-bottom-left-radius: 6px;
  }

  .message-bubble.loading {
    font-style: italic;
    background-color: #e8eaed;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .message-bubble.error {
    color: white;
    background-color: #dc3545;
    border-bottom-left-radius: 6px;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }

    50% {
      opacity: 0.6;
    }
  }

  .chat-input {
    display: flex;
    gap: 8px;
    padding: 16px;
    border-top: 1px solid #e0e0e0;
  }

  .chat-input input {
    flex: 1;
    padding: 12px;
    font-size: 14px;
    border: 1px solid #dddddd;
    border-radius: 24px;
    outline: none;
  }

  .chat-input input:focus {
    border-color: #667eea;
  }

  .send-button {
    cursor: pointer;
    transition: opacity 0.2s ease;
  }

</style>
