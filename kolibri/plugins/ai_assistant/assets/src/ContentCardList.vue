<template>

  <div class="content-list">
    <KCardGrid
      layout="1-1-1"
      :layoutOverride="gridLayoutOverrides"
    >
      <AccessibleResourceCard
        v-for="content in contentList"
        :key="content.id"
        :to="contentCardLink(content)"
        :contentNode="content"
      />
    </KCardGrid>
  </div>

</template>


<script>

  import urls from 'kolibri/urls';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import AccessibleResourceCard from './AccessibleResourceCard';

  export default {
    name: 'ContentCardList',
    components: {
      AccessibleResourceCard,
    },
    mixins: [commonCoreStrings],
    props: {
      contentList: {
        type: Array,
        required: true,
      },
    },

    computed: {
      gridLayoutOverrides() {
        return [{ breakpoints: [0, 1, 2, 3, 4, 5, 6, 7], rowGap: '24px', cardsPerRow: 1 }];
      },
    },
    methods: {
      contentCardLink(content) {
        return `${urls['kolibri:core:contentpermalink']()}?node_id=${content.id}`;
      },
    },
  };

</script>


<style lang="scss" scoped>

  .content-list {
    display: block;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  .content-list-item {
    position: relative;
    display: block;
    text-align: right;
  }

</style>
