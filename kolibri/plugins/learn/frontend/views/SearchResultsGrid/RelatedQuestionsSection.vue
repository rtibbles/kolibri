<template>

  <div
    v-if="questions.length"
    data-test="related-questions-section"
    class="related-questions-section"
  >
    <h3 class="section-header">
      {{ $tr('relatedQuestions') }}
    </h3>
    <div class="questions-list">
      <KButton
        v-for="(question, idx) in questions"
        :key="'q-' + idx"
        data-test="related-question-chip"
        :text="question"
        appearance="flat-button"
        :appearanceOverrides="chipStyles"
        @click="$emit('selectQuestion', question)"
      />
    </div>
  </div>

</template>


<script>

  export default {
    name: 'RelatedQuestionsSection',
    props: {
      questions: {
        type: Array,
        default: () => [],
      },
    },
    computed: {
      chipStyles() {
        return {
          borderRadius: '20px',
          padding: '8px 16px',
          fontSize: '14px',
          fontWeight: 'normal',
          textTransform: 'none',
          backgroundColor: this.$themeBrand.primary.v_100,
          color: this.$themeTokens.primary,
          border: `1px solid ${this.$themeTokens.primary}`,
          textAlign: 'left',
          whiteSpace: 'normal',
        };
      },
    },
    $trs: {
      relatedQuestions: {
        message: 'Related questions',
        context: 'Section header for AI-generated related search questions',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .related-questions-section {
    padding: 16px 0;
  }

  .section-header {
    margin: 0 0 12px;
    font-size: 16px;
    font-weight: 600;
  }

  .questions-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

</style>
