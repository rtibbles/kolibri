<template>

  <div
    v-if="messages.length && !messagesDismissed"
    class="search-messages tex2jax_ignore"
    :style="{
      backgroundColor: $themePalette.grey.v_100,
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
        backgroundColor: $themeTokens.surface,
        borderColor: $themeBrand.primary.v_100,
        color: $themeTokens.text,
      }"
    >
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="search-message-text" v-html="renderMessage(message)">
      </div>
    </div>
  </div>

</template>


<script>

  import { ref, watch } from 'vue';
  import katex from 'katex';
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
    methods: {
      renderKatex(latex) {
        try {
          return katex.renderToString(latex, { throwOnError: false });
        } catch (e) {
          return null;
        }
      },
      renderMath(text) {
        // Escape HTML, then parse for math delimiters.
        // Supports \(...\) and $...$ with tight-delimiter rules:
        //   - opening $ must be followed by a non-space character
        //   - closing $ must be preceded by a non-space character
        // This prevents currency like "$3 per gallon" from being
        // matched as math. Inside $...$, \$ is kept as-is for KaTeX
        // (renders as literal $). Outside math, \$ becomes plain $.
        const s = text
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
        let result = '';
        let i = 0;
        while (i < s.length) {
          // \(...\) delimiters
          if (s[i] === '\\' && s[i + 1] === '(') {
            const end = s.indexOf('\\)', i + 2);
            if (end !== -1) {
              const html = this.renderKatex(s.substring(i + 2, end));
              if (html) { result += html; i = end + 2; continue; }
            }
          }
          // $...$ delimiters (tight: non-space after open, non-space before close)
          if (s[i] === '$' && i + 1 < s.length && s[i + 1] !== ' ' && s[i + 1] !== '$') {
            let j = i + 1;
            let math = '';
            let found = false;
            while (j < s.length) {
              if (s[j] === '\\' && s[j + 1] === '$') {
                math += '\\$'; j += 2;
              } else if (s[j] === '$') {
                if (s[j - 1] !== ' ') { found = true; }
                break;
              } else {
                math += s[j]; j++;
              }
            }
            if (found) {
              const html = this.renderKatex(math);
              if (html) { result += html; i = j + 1; continue; }
            }
          }
          // \$ outside math becomes plain $
          if (s[i] === '\\' && s[i + 1] === '$') {
            result += '$'; i += 2; continue;
          }
          result += s[i]; i++;
        }
        return result;
      },
      renderMessage(text) {
        return this.renderMarkdown(this.renderMath(text));
      },
      renderMarkdown(html) {
        // Bold: **text** → <strong>text</strong>
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Italic: *text* → <em>text</em> (multi-char content)
        html = html.replace(/(?<!\*)\*([^\s*][^*]*?[^\s*])\*(?!\*)/g, '<em>$1</em>');
        // Italic: *x* → <em>x</em> (single char content)
        html = html.replace(/(?<!\*)\*([^\s*])\*(?!\*)/g, '<em>$1</em>');

        const lines = html.split('\n');
        let result = '';
        let inOl = false;
        let inUl = false;

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed === '') {
            if (inOl) { result += '</ol>'; inOl = false; }
            if (inUl) { result += '</ul>'; inUl = false; }
            result += '<br>';
            continue;
          }
          const olMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
          const ulMatch = trimmed.match(/^[-*]\s+(.*)/);

          if (olMatch) {
            if (inUl) { result += '</ul>'; inUl = false; }
            if (!inOl) { result += '<ol>'; inOl = true; }
            result += '<li>' + olMatch[2] + '</li>';
          } else if (ulMatch) {
            if (inOl) { result += '</ol>'; inOl = false; }
            if (!inUl) { result += '<ul>'; inUl = true; }
            result += '<li>' + ulMatch[1] + '</li>';
          } else {
            if (inOl) { result += '</ol>'; inOl = false; }
            if (inUl) { result += '</ul>'; inUl = false; }
            result += trimmed + '<br>';
          }
        }
        if (inOl) result += '</ol>';
        if (inUl) result += '</ul>';

        return result.replace(/(<br>)+$/, '');
      },
    },
    $trs: {
      dismissMessages: {
        message: 'Dismiss messages',
        context: 'Label for a button used to dismiss search context messages.',
      },
    },
  };

</script>


<style>
  @import '~katex/dist/katex.min.css';

  .search-message-text ol,
  .search-message-text ul {
    margin: 4px 0;
    padding-left: 24px;
  }

  .search-message-text li {
    margin: 2px 0;
  }
</style>


<style scoped>

  .search-messages {
    position: relative;
    padding: 16px;
    margin-bottom: 24px;
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
