<template>

  <div
    v-if="groups.length"
    data-testid="more-to-explore"
    class="more-to-explore"
  >
    <h2 class="section-header">
      {{ $tr('moreToExplore') }}
    </h2>
    <div
      v-for="(group, idx) in groups"
      :key="'group-' + idx"
      data-testid="explore-group"
      class="explore-group"
    >
      <div class="group-header">
        <span class="group-label">{{ group.label }}</span>
        <span
          class="group-count"
          :style="{ color: $themePalette.grey.v_500 }"
        >
          {{ $tr('resultCount', { count: group.count }) }}
        </span>
      </div>
      <HorizontalCardRow :items="group.items">
        <template #default="{ item }">
          <slot
            name="card"
            :item="item"
          ></slot>
        </template>
      </HorizontalCardRow>
    </div>
  </div>

</template>


<script>

  import HorizontalCardRow from 'kolibri-common/components/HorizontalCardRow';

  export default {
    name: 'MoreToExploreSection',
    components: {
      HorizontalCardRow,
    },
    props: {
      groups: {
        type: Array,
        default: () => [],
      },
    },
    $trs: {
      moreToExplore: {
        message: 'More to explore',
        context: 'Section header for additional search result categories',
      },
      resultCount: {
        message: '{count, number} {count, plural, one {result} other {results}}',
        context: 'Count of results in a category group',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .more-to-explore {
    padding: 24px 0;
  }

  .section-header {
    margin: 0 0 16px;
    font-size: 18px;
    font-weight: 600;
  }

  .explore-group {
    margin-bottom: 24px;
  }

  .group-header {
    display: flex;
    gap: 8px;
    align-items: baseline;
    margin-bottom: 12px;
  }

  .group-label {
    font-size: 16px;
    font-weight: 600;
  }

  .group-count {
    font-size: 14px;
  }

</style>
