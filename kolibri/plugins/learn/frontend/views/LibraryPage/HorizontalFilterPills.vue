<template>

  <div class="filter-pills">
    <!-- Learning activity pills -->
    <div
      v-if="activityEntries.length"
      class="pill-row"
    >
      <KButton
        v-for="(activity, index) in activityEntries"
        :key="'activity-' + index"
        data-testid="activity-pill"
        :text="coreString(activity.key)"
        appearance="flat-button"
        :icon="activityIconMap[activity.key] || null"
        :appearanceOverrides="
          isActivityActive(activity.value) ? { ...pillStyles, ...activePillStyles } : pillStyles
        "
        :disabled="loading"
        @click="handleActivityClick(activity)"
      />
    </div>

    <!-- Category pills -->
    <div
      v-if="categoryEntries.length"
      class="pill-row"
    >
      <KButton
        v-for="(category, index) in categoryEntries"
        :key="'category-' + index"
        data-testid="category-pill"
        :text="category.label"
        appearance="flat-button"
        :icon="getCategoryIcon(category.key)"
        :appearanceOverrides="
          isCategoryActive(category.value) ? { ...pillStyles, ...activePillStyles } : pillStyles
        "
        :disabled="loading"
        @click="handleCategoryClick(category)"
      />
    </div>
  </div>

</template>


<script>

  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import { injectBaseSearch } from 'kolibri-common/composables/useBaseSearch';
  import { getCategoryIcon } from 'kolibri-common/utils/categoryIcon';

  // Map learning activity keys to KDS icon names
  const activityIconMap = {
    CREATE: 'createShaded',
    EXPLORE: 'interactShaded',
    LISTEN: 'listenShaded',
    PRACTICE: 'practiceShaded',
    READ: 'readShaded',
    REFLECT: 'reflectShaded',
    WATCH: 'watchShaded',
  };

  export default {
    name: 'HorizontalFilterPills',
    mixins: [commonCoreStrings],
    setup() {
      const {
        availableLearningActivities,
        availableLibraryCategories,
        activeSearchTerms,
        searchLoading,
      } = injectBaseSearch();
      return {
        availableLearningActivities,
        availableLibraryCategories,
        activeSearchTerms,
        loading: searchLoading,
      };
    },
    data() {
      return {
        activityIconMap,
      };
    },
    computed: {
      activityEntries() {
        const activities = this.availableLearningActivities;
        if (!activities) return [];
        return Object.entries(activities).map(([key, value]) => ({
          key,
          value,
        }));
      },
      categoryEntries() {
        const categories = this.availableLibraryCategories;
        if (!categories) return [];
        return Object.entries(categories).map(([key, info]) => ({
          key,
          label: this.coreString(key),
          value: info.value,
        }));
      },
      pillStyles() {
        return {
          borderRadius: '20px',
          padding: '6px 14px',
          fontSize: '14px',
          fontWeight: 'normal',
          textTransform: 'none',
          border: `1px solid ${this.$themePalette.grey.v_300}`,
          whiteSpace: 'nowrap',
          color: this.$themeTokens.text,
        };
      },
      activePillStyles() {
        return {
          backgroundColor: this.$themeBrand.primary.v_100,
          borderColor: this.$themeTokens.primary,
          color: this.$themeTokens.primary,
          fontWeight: 'bold',
        };
      },
    },
    methods: {
      isActivityActive(value) {
        const terms = this.activeSearchTerms;
        return terms && terms.learning_activities && terms.learning_activities[value];
      },
      isCategoryActive(value) {
        const terms = this.activeSearchTerms;
        return terms && terms.categories && terms.categories[value];
      },
      getCategoryIcon,
      handleActivityClick(activity) {
        this.$emit('toggleFilter', {
          key: 'learning_activities',
          value: activity.value,
          label: activity.key,
        });
      },
      handleCategoryClick(category) {
        this.$emit('toggleFilter', {
          key: 'categories',
          value: category.value,
          label: category.label,
        });
      },
    },
  };

</script>


<style lang="scss" scoped>

  .filter-pills {
    margin: 8px 0;
  }

  .pill-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }

</style>
