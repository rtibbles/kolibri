<template>

  <div
    v-if="questions && questions.length"
    class="suggested-questions"
  >
    <KButton
      v-for="(question, index) in questions"
      :key="index"
      data-test="question-chip"
      :text="question"
      appearance="flat-button"
      :appearanceOverrides="chipStyles"
      iconAfter="chevronRight"
      @click="$emit('selectQuestion', question)"
    />
  </div>

</template>


<script>

  export default {
    name: 'SuggestedQuestionChips',
    props: {
      questions: {
        type: Array,
        default: () => [],
      },
    },
    computed: {
      chipStyles() {
        return {
          backgroundColor: this.$themeBrand.primary.v_100,
          color: this.$themeTokens.primary,
          borderRadius: '20px',
          padding: '6px 12px',
          fontSize: '14px',
          fontWeight: 'normal',
          textTransform: 'none',
          whiteSpace: 'nowrap',
        };
      },
    },
  };

</script>


<style lang="scss" scoped>

  .suggested-questions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0;
  }

</style>
