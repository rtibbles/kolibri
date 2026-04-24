<template>

  <div
    v-if="messages.length && !dismissed"
    data-test="ai-response-section"
    class="ai-response-section"
    :style="{ backgroundColor: $themePalette.yellow.v_100 }"
  >
    <KIconButton
      data-test="dismiss-button"
      icon="close"
      size="small"
      class="dismiss-button"
      :ariaLabel="$tr('dismissMessages')"
      :style="{ opacity: 0.7 }"
      @click="dismissed = true"
    />
    <div class="messages">
      <p
        v-for="(message, idx) in messages"
        :key="idx"
        data-test="ai-message"
        class="message-text"
      >
        {{ message }}
      </p>
    </div>
    <div
      v-if="categoryChips.length"
      class="category-chips"
    >
      <KButton
        v-for="(chip, idx) in categoryChips"
        :key="'chip-' + idx"
        data-test="category-chip"
        :text="chip.label"
        appearance="flat-button"
        :appearanceOverrides="chipStyles"
        @click="$emit('selectCategory', chip)"
      />
    </div>
  </div>

</template>


<script>

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
    $trs: {
      dismissMessages: {
        message: 'Dismiss AI response',
        context: 'Accessible label for the button to dismiss the AI response banner',
      },
    },
  };

</script>


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
    top: 8px;
    inset-inline-end: 8px;
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
