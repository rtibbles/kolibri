<template>

  <div
    v-if="messages.length && !dismissed"
    data-testid="ai-response-section"
    class="ai-response-section"
    :style="{ backgroundColor: $themePalette.yellow.v_100 }"
  >
    <KIconButton
      data-testid="dismiss-button"
      icon="close"
      size="small"
      class="dismiss-button"
      :ariaLabel="$tr('dismissMessages')"
      :style="{ opacity: 0.7 }"
      @click="dismissed = true"
    />
    <div class="messages">
      <!-- eslint-disable vue/no-v-html -->
      <div
        v-for="(message, idx) in messages"
        :key="idx"
        data-testid="ai-message"
        class="message-text"
        v-html="renderMessage(message)"
      ></div>
      <!-- eslint-enable vue/no-v-html -->
    </div>
    <div
      v-if="categoryChips.length"
      class="category-chips"
    >
      <KButton
        v-for="(chip, idx) in categoryChips"
        :key="'chip-' + idx"
        data-testid="category-chip"
        :text="chip.label"
        appearance="flat-button"
        :appearanceOverrides="chipStyles"
        @click="$emit('selectCategory', chip)"
      />
    </div>
  </div>

</template>


<script>

  import katex from 'katex';

  export default {
    name: 'AIResponseSection',
    props: {
      messages: {
        type: Array,
        default: () => [],
      },
      categoryChips: {
        type: Array,
        default: () => [],
      },
    },
    data() {
      return {
        dismissed: false,
      };
    },
    computed: {
      chipStyles() {
        return {
          borderRadius: '16px',
          padding: '4px 12px',
          fontSize: '13px',
          fontWeight: 'normal',
          textTransform: 'none',
          backgroundColor: this.$themeBrand.primary.v_100,
          color: this.$themeTokens.primary,
          border: `1px solid ${this.$themeTokens.primary}`,
        };
      },
    },
    watch: {
      messages() {
        this.dismissed = false;
      },
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
        const s = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        let result = '';
        let i = 0;
        while (i < s.length) {
          if (s[i] === '\\' && s[i + 1] === '(') {
            const end = s.indexOf('\\)', i + 2);
            if (end !== -1) {
              const html = this.renderKatex(s.substring(i + 2, end));
              if (html) {
                result += html;
                i = end + 2;
                continue;
              }
            }
          }
          if (s[i] === '$' && i + 1 < s.length && s[i + 1] !== ' ' && s[i + 1] !== '$') {
            let j = i + 1;
            let math = '';
            let found = false;
            while (j < s.length) {
              if (s[j] === '\\' && s[j + 1] === '$') {
                math += '\\$';
                j += 2;
              } else if (s[j] === '$') {
                if (s[j - 1] !== ' ') {
                  found = true;
                }
                break;
              } else {
                math += s[j];
                j++;
              }
            }
            if (found) {
              const html = this.renderKatex(math);
              if (html) {
                result += html;
                i = j + 1;
                continue;
              }
            }
          }
          if (s[i] === '\\' && s[i + 1] === '$') {
            result += '$';
            i += 2;
            continue;
          }
          result += s[i];
          i++;
        }
        return result;
      },
      renderMarkdown(html) {
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/(?<!\*)\*([^\s*][^*]*?[^\s*])\*(?!\*)/g, '<em>$1</em>');
        html = html.replace(/(?<!\*)\*([^\s*])\*(?!\*)/g, '<em>$1</em>');

        const lines = html.split('\n');
        let result = '';
        let inOl = false;
        let inUl = false;

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed === '') {
            if (inOl) {
              result += '</ol>';
              inOl = false;
            }
            if (inUl) {
              result += '</ul>';
              inUl = false;
            }
            result += '<br>';
            continue;
          }
          const olMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
          const ulMatch = trimmed.match(/^[-*]\s+(.*)/);

          if (olMatch) {
            if (inUl) {
              result += '</ul>';
              inUl = false;
            }
            if (!inOl) {
              result += '<ol>';
              inOl = true;
            }
            result += '<li>' + olMatch[2] + '</li>';
          } else if (ulMatch) {
            if (inOl) {
              result += '</ol>';
              inOl = false;
            }
            if (!inUl) {
              result += '<ul>';
              inUl = true;
            }
            result += '<li>' + ulMatch[1] + '</li>';
          } else {
            if (inOl) {
              result += '</ol>';
              inOl = false;
            }
            if (inUl) {
              result += '</ul>';
              inUl = false;
            }
            result += trimmed + '<br>';
          }
        }
        if (inOl) result += '</ol>';
        if (inUl) result += '</ul>';

        return result.replace(/(<br>)+$/, '');
      },
      renderMessage(text) {
        return this.renderMarkdown(this.renderMath(text));
      },
    },
    $trs: {
      dismissMessages: {
        message: 'Dismiss AI response',
        context: 'Accessible label for the button to dismiss the AI response banner',
      },
    },
  };

</script>


<style>

  @import '~katex/dist/katex.min.css';

  .ai-response-section .message-text ol,
  .ai-response-section .message-text ul {
    padding-left: 24px;
    margin: 4px 0;
  }

  .ai-response-section .message-text li {
    margin: 2px 0;
  }

</style>


<style lang="scss" scoped>

  .ai-response-section {
    position: relative;
    padding: 16px;
    padding-inline-end: 40px;
    margin-bottom: 16px;
    border-radius: 8px;
  }

  .dismiss-button {
    position: absolute;
    inset-inline-end: 8px;
    top: 8px;
  }

  .message-text {
    margin: 0 0 8px;
    font-size: 14px;
    line-height: 1.5;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .category-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

</style>
