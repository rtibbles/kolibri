<template>

  <div
    v-if="show"
    data-testid="autocomplete-dropdown"
    class="autocomplete-dropdown"
    role="menu"
    :style="{ backgroundColor: $themeTokens.surface }"
  >
    <!-- Focus state: no query - show history and recent searches -->
    <template v-if="!query">
      <div
        v-if="historyItems.length"
        data-testid="history-section"
        class="section"
      >
        <h3
          class="section-header"
          :style="{ color: $themePalette.grey.v_600 }"
        >
          {{ $tr('history') }}
        </h3>
        <div
          v-for="item in historyItems"
          :key="item.id"
          data-testid="history-item"
          class="dropdown-item"
          role="menuitem"
          tabindex="-1"
          @click="$emit('selectContent', item)"
        >
          <LearningActivityIcon
            v-if="item.learning_activities && item.learning_activities.length"
            :kind="item.learning_activities"
            :shaded="true"
            class="item-icon"
            :style="{ fill: $themeTokens.primary }"
          />
          <KIcon
            v-else
            icon="interactShaded"
            class="item-icon"
            :style="{ fill: $themeTokens.primary }"
          />
          <div class="item-content">
            <span class="item-title">{{ item.title }}</span>
            <span
              v-if="item.channel_title"
              class="item-channel"
              :style="{ color: $themePalette.grey.v_500 }"
            >
              {{ item.channel_title }}
            </span>
          </div>
          <div
            v-if="item.learning_activities && item.learning_activities.length"
            class="item-tags"
          >
            <span
              v-for="activity in item.learning_activities"
              :key="activity"
              class="metadata-tag"
              :style="{
                backgroundColor: $themeBrand.primary.v_100,
                color: $themeTokens.primary,
              }"
            >
              {{ coreString(activity) }}
            </span>
          </div>
        </div>
      </div>

      <div
        v-if="recentSearches.length"
        data-testid="recent-searches-section"
        class="section"
      >
        <h3
          class="section-header"
          :style="{ color: $themePalette.grey.v_600 }"
        >
          {{ $tr('recentSearches') }}
        </h3>
        <div
          v-for="(term, idx) in recentSearches"
          :key="'search-' + idx"
          data-testid="recent-search-item"
          class="dropdown-item"
          role="menuitem"
          tabindex="-1"
          @click="$emit('selectSearch', term)"
        >
          <KIcon
            icon="search"
            class="item-icon"
            :style="{ fill: $themePalette.grey.v_500 }"
          />
          <div class="item-content">
            <span class="item-title">{{ term }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Typing state: show autocomplete suggestions -->
    <template v-else>
      <!-- Metadata filter suggestions rendered as pills -->
      <div
        v-if="filterSuggestions.length"
        class="filter-suggestions-row"
      >
        <button
          v-for="(item, idx) in filterSuggestions"
          :key="'filter-' + idx"
          data-testid="filter-suggestion-pill"
          class="filter-pill"
          :style="{
            backgroundColor: $themeBrand.primary.v_100,
            border: `1px solid ${$themeTokens.primary}`,
            color: $themeTokens.primary,
          }"
          @click="handleSuggestionClick(item)"
          @mouseenter="$emit('hoverFilter', item)"
          @mouseleave="$emit('hoverFilter', null)"
        >
          <LearningActivityIcon
            v-if="getActivityKind(item)"
            :kind="getActivityKind(item)"
            :shaded="true"
            class="pill-icon"
            :style="{ fill: $themeTokens.primary }"
          />
          <KIcon
            v-else-if="item.type === 'category' && item.key"
            :icon="getCategoryIcon(item.key)"
            class="pill-icon"
            :style="{ fill: $themeTokens.primary }"
          />
          <KIcon
            v-else
            icon="filterList"
            class="pill-icon"
            :style="{ fill: $themeTokens.primary }"
          />
          <span class="pill-label">{{ item.label }}</span>
        </button>
      </div>

      <!-- Content suggestions as regular list items -->
      <div
        v-for="(item, idx) in contentSuggestions"
        :key="'content-' + idx"
        data-testid="suggestion-item"
        class="dropdown-item"
        role="menuitem"
        tabindex="-1"
        @click="handleSuggestionClick(item)"
      >
        <LearningActivityIcon
          v-if="item.learning_activities && item.learning_activities.length"
          :kind="item.learning_activities"
          :shaded="true"
          class="item-icon"
          :style="{ fill: $themeTokens.primary }"
        />
        <KIcon
          v-else
          icon="interactShaded"
          class="item-icon"
          :style="{ fill: $themeTokens.primary }"
        />
        <div class="item-content">
          <span class="item-title">{{ item.title }}</span>
          <span
            v-if="item.channel_title"
            class="item-channel"
            :style="{ color: $themePalette.grey.v_500 }"
          >
            {{ item.channel_title }}
          </span>
        </div>
        <div
          v-if="item.learning_activities && item.learning_activities.length"
          class="item-tags"
        >
          <span
            v-for="activity in item.learning_activities"
            :key="activity"
            class="metadata-tag"
            :style="{
              backgroundColor: $themeBrand.primary.v_100,
              color: $themeTokens.primary,
            }"
          >
            {{ coreString(activity) }}
          </span>
        </div>
      </div>
    </template>
  </div>

</template>


<script>

  import { LearningActivities } from 'kolibri/constants';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import LearningActivityIcon from 'kolibri-common/components/ResourceDisplayAndSearch/LearningActivityIcon.vue';
  import { getCategoryIcon } from 'kolibri-common/utils/categoryIcon';

  export default {
    name: 'SearchAutocompleteDropdown',
    components: {
      LearningActivityIcon,
    },
    mixins: [commonCoreStrings],
    props: {
      show: {
        type: Boolean,
        default: false,
      },
      query: {
        type: String,
        default: '',
      },
      suggestions: {
        type: Array,
        default: () => [],
      },
      historyItems: {
        type: Array,
        default: () => [],
      },
      recentSearches: {
        type: Array,
        default: () => [],
      },
    },
    computed: {
      filterSuggestions() {
        return this.suggestions.filter(s => s.type !== 'content');
      },
      contentSuggestions() {
        return this.suggestions.filter(s => s.type === 'content');
      },
    },
    methods: {
      getCategoryIcon,
      /**
       * Returns the learning activity kind value(s) to pass to LearningActivityIcon,
       * or null if the item isn't activity-related.
       */
      getActivityKind(item) {
        if (
          item.type === 'content' &&
          item.learning_activities &&
          item.learning_activities.length
        ) {
          return item.learning_activities;
        }
        if (item.type === 'activity' && item.key) {
          return LearningActivities[item.key];
        }
        return null;
      },
      handleSuggestionClick(item) {
        if (item.type === 'content') {
          this.$emit('selectContent', item);
        } else {
          this.$emit('selectFilter', item);
        }
      },
    },
    $trs: {
      history: {
        message: 'History',
        context: 'Header for recently viewed content in autocomplete dropdown',
      },
      recentSearches: {
        message: 'Recent searches',
        context: 'Header for recent search terms in autocomplete dropdown',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .autocomplete-dropdown {
    position: absolute;
    right: 0;
    left: 0;
    z-index: 8;
    max-height: 400px;
    overflow-y: auto;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
  }

  .section {
    padding: 8px 0;
  }

  .section-header {
    padding: 4px 16px;
    margin: 0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .dropdown-item {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    cursor: pointer;

    &:hover {
      background-color: rgba(0, 0, 0, 0.04);
    }
  }

  .item-icon {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    margin-inline-end: 12px;
  }

  .item-content {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .item-title {
    overflow: hidden;
    font-size: 14px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .item-channel {
    font-size: 12px;
  }

  .item-tags {
    display: flex;
    flex-shrink: 0;
    gap: 4px;
    margin-inline-start: 8px;
  }

  .metadata-tag {
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 10px;
  }

  .filter-suggestions-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 16px;
  }

  .filter-pill {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    padding: 5px 10px;
    font-size: 13px;
    font-weight: normal;
    line-height: 1;
    cursor: pointer;
    border-radius: 20px;
  }

  .pill-label {
    white-space: nowrap;
  }

  // KIcon's SVG uses position: relative; top: 0.125em for inline text flow;
  // undo it inside the flex pill so the icon sits at true centre.
  .filter-pill .pill-icon {
    top: 0;
  }

</style>
