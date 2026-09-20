<template>

  <!-- eslint-disable vue/no-bare-strings-in-template -->
  <div class="sandbox-page">
    <h1>Composed thumbnail sandbox</h1>
    <p :style="{ color: $themeTokens.annotation }">
      Development-only page for iterating on composed placeholder thumbnails.
    </p>

    <KCardGrid layout="1-2-3">
      <ResourceCard
        v-for="node in mockNodes"
        :key="node.id"
        :contentNode="node"
        :to="selfLink"
      />
    </KCardGrid>
  </div>

</template>


<script>

  import ResourceCard from '../views/cards/ResourceCard';
  import mockNodes from './mockNodes';

  export default {
    name: 'ThumbnailSandboxPage',
    components: {
      ResourceCard,
    },
    setup() {
      return {
        mockNodes,
        selfLink: { name: 'THUMBNAIL_SANDBOX' },
      };
    },
  };

</script>


<style lang="scss" scoped>

  .sandbox-page {
    padding: 24px;
  }

</style>
