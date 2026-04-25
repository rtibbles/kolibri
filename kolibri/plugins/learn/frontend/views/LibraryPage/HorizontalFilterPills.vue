<template>

  <div class="filter-pills">
    <KButton
      v-for="(entry, index) in entries"
      :key="`${entry.type}-${index}`"
      :data-testid="`${entry.type}-pill`"
      :text="entry.label"
      appearance="flat-button"
      :icon="entry.icon"
      :iconAfter="iconAfterFor(entry)"
      :appearanceOverrides="
        isFilterActive(entry.termKey, entry.value)
          ? { ...pillStyles, ...activePillStyles }
          : pillStyles
      "
      :disabled="loading"
      @click="toggleFilter({ key: entry.termKey, value: entry.value })"
    />
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
        appliedFilters,
        isFilterActive,
        isLabelAvailable,
        toggleFilter,
        searchLoading,
      } = injectBaseSearch();
      return {
        availableLearningActivities,
        availableLibraryCategories,
        appliedFilters,
        isFilterActive,
        isLabelAvailable,
        toggleFilter,
        loading: searchLoading,
      };
    },
    computed: {
      // Lookup tables for the activity / category catalogs so a value stored
      // in `searchTerms` can be resolved back to its translation key + icon.
      activityKeyByValue() {
        return Object.fromEntries(
          Object.entries(this.availableLearningActivities || {}).map(([k, v]) => [v, k]),
        );
      },
      categoryKeyByValue() {
        return Object.fromEntries(
          Object.entries(this.availableLibraryCategories || {}).map(([k, info]) => [info.value, k]),
        );
      },
      // Applied filters render first (in the order the composable returns
      // them), followed by still-yieldable refinement options from the
      // activity and category catalogs. Dedup keeps an actively-selected
      // catalog item from rendering twice.
      entries() {
        const out = [];
        const seen = new Set();
        const push = entry => {
          const id = `${entry.termKey}:${entry.value}`;
          if (seen.has(id)) return;
          seen.add(id);
          out.push(entry);
        };

        for (const { key, value } of this.appliedFilters()) {
          push(this.entryFor(key, value));
        }
        for (const value of Object.values(this.availableLearningActivities || {})) {
          if (this.isLabelAvailable('learning_activities', value)) {
            push(this.entryFor('learning_activities', value));
          }
        }
        for (const info of Object.values(this.availableLibraryCategories || {})) {
          if (this.isLabelAvailable('categories', info.value)) {
            push(this.entryFor('categories', info.value));
          }
        }
        return out;
      },
      pillStyles() {
        return {
          display: 'inline-flex',
          alignItems: 'center',
          minHeight: '0',
          height: 'auto',
          lineHeight: '1',
          borderRadius: '20px',
          padding: '5px 10px',
          fontSize: '13px',
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
      // Decorate a {termKey, value} pair with the label and icon needed to
      // render a pill. Activity/category dimensions get specific icons; other
      // dimensions render a value-as-i18n-key label with no leading icon.
      entryFor(termKey, value) {
        if (termKey === 'keywords') {
          return { type: 'keyword', termKey, value, label: value, icon: null };
        }
        if (termKey === 'learning_activities') {
          const key = this.activityKeyByValue[value];
          return {
            type: 'activity',
            termKey,
            value,
            label: key ? this.coreString(key) : value,
            icon: key ? activityIconMap[key] : null,
          };
        }
        if (termKey === 'categories') {
          const key = this.categoryKeyByValue[value];
          return {
            type: 'category',
            termKey,
            value,
            label: key ? this.coreString(key) : value,
            icon: key ? getCategoryIcon(key) : null,
          };
        }
        return {
          type: termKey,
          termKey,
          value,
          label: this.coreString(value),
          icon: null,
        };
      },
      iconAfterFor(entry) {
        if (this.isFilterActive(entry.termKey, entry.value)) {
          return 'close';
        }
        return entry.type === 'category' ? 'chevronRight' : null;
      },
    },
  };

</script>


<style lang="scss" scoped>

  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  // KButton renders an empty `.icon-container` span as the first child even
  // when no key shortcut is bound. Inside our flex pill, that empty span still
  // counts as a flex item and offsets the icon — hide it.
  .filter-pills /deep/ .icon-container {
    display: none;
  }

  // KButton applies `position: relative; top: 4px` to its prop icons to nudge
  // them inside the default 36px-tall button. With our slim pill, this 4px
  // offset pushes the icon below the text centre — undo it.
  .filter-pills /deep/ svg.prop-icon {
    top: 0;
  }

</style>
