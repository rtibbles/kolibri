<template>

  <div
    v-if="messages.length && !messagesDismissed"
    class="search-messages"
    :style="{
      backgroundColor: $themeTokens.surface,
      borderColor: $themeTokens.primary,
    }"
  >
    <div class="search-messages-header">
      <KIconButton
        icon="close"
        size="small"
        class="dismiss-button"
        :ariaLabel="$tr('dismissMessages')"
        @click="dismissMessages"
      />
    </div>
    <div
      v-for="(message, i) in messages"
      :key="i"
      class="search-message"
      :style="{
        backgroundColor: $themeTokens.surfaceVariant,
        borderColor: $themeTokens.secondary,
        color: $themeTokens.text,
      }"
    >
      <p class="search-message-text">
        {{ message }}
      </p>
    </div>
  </div>

</template>


<script>

  import { ref, watch } from 'vue';
  import { injectBaseSearch } from '../composables/useBaseSearch';

  export default {
    name: 'SearchMessages',
    setup() {
      const { messages } = injectBaseSearch();
      const messagesDismissed = ref(false);
      watch(messages, () => {
        // Reset dismissal state when new messages arrive
        messagesDismissed.value = false;
      });
      function dismissMessages() {
        messagesDismissed.value = true;
      }
      return { messages, messagesDismissed, dismissMessages };
    },
    $trs: {
      dismissMessages: {
        message: 'Dismiss messages',
        context: 'Label for a button used to dismiss search context messages.',
      },
    },
  };

</script>


<style scoped>

  .search-messages {
    position: relative;
    padding: 16px;
    margin-bottom: 24px;
    border: 2px solid;
    border-radius: 8px;
  }

  .search-messages-header {
    position: absolute;
    top: 8px;
    right: 8px;
  }

  .dismiss-button {
    opacity: 0.7;

    &:hover {
      opacity: 1;
    }
  }

  .search-message {
    display: block;
    width: fit-content;
    max-width: calc(100% - 48px);
    padding: 12px 16px;
    margin-right: 25px;
    margin-bottom: 16px;
    border: 2px solid;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

    &:last-child {
      margin-bottom: 0;
    }
  }

  .search-message-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.4;
  }

</style>
