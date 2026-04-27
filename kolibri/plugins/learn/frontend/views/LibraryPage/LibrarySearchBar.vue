<template>

  <form
    class="library-search-bar"
    @submit.prevent="handleSubmit"
  >
    <div
      class="search-row"
      :style="{
        backgroundColor: $themeTokens.surface,
        borderColor: $themePalette.grey.v_300,
      }"
    >
      <label
        class="visuallyhidden"
        :for="inputId"
      >{{ coreString('searchLabel') }}</label>
      <input
        :id="inputId"
        ref="searchInput"
        :value="value"
        type="search"
        class="search-input"
        :style="{ color: $themeTokens.text }"
        dir="auto"
        :placeholder="placeholder || coreString('findSomethingToLearn')"
        @input="handleInput"
        @keydown.enter.prevent="handleSubmit"
        @focus="handleFocus"
        @blur="handleBlur"
      >
      <div
        v-if="highlightSegments"
        class="search-input-overlay"
        aria-hidden="true"
      >
        <span
          v-for="(seg, idx) in highlightSegments"
          :key="idx"
          :class="{ 'highlight-matched': seg.matched }"
          :style="
            seg.matched
              ? {
                backgroundColor: $themeBrand.primary.v_100,
              }
              : {}
          "
        >{{ seg.text }}</span>
      </div>
      <div class="search-actions">
        <KIconButton
          v-if="value"
          icon="clear"
          :color="$themeTokens.text"
          size="small"
          data-testid="search-clear-button"
          :ariaLabel="coreString('clearAction')"
          @click="handleClear"
        />
        <KButton
          v-if="!windowIsSmall"
          data-testid="all-filters-button"
          appearance="flat-button"
          :text="$tr('allFilters')"
          @click="$emit('openFilters')"
        />
        <KButton
          data-testid="search-submit-button"
          :primary="true"
          type="submit"
          :appearanceOverrides="searchButtonStyles"
          :ariaLabel="coreString('startSearchButtonLabel')"
        >
          <template #icon>
            <KIcon
              icon="search"
              :style="{ width: '24px', height: '24px' }"
              :color="$themeTokens.textInverted"
            />
          </template>
        </KButton>
      </div>
    </div>

    <SearchAutocompleteDropdown
      :show="showDropdown"
      :query="value"
      :suggestions="currentSuggestions"
      :historyItems="historyItems"
      :recentSearches="recentSearchTerms"
      @selectContent="handleSelectContent"
      @selectSearch="handleSelectSearch"
      @selectFilter="handleSelectFilter"
      @hoverFilter="handleHoverFilter"
    />
  </form>

</template>


<script>

  import { ref } from 'vue';
  import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import useUser from 'kolibri/composables/useUser';
  import { injectBaseSearch } from 'kolibri-common/composables/useBaseSearch';
  import { getMatchedWordSegments } from 'kolibri-common/composables/useFuzzyMetadataSearch';
  import useRecentSearches from 'kolibri-common/composables/useRecentSearches';
  import useLearnerResources from '../../composables/useLearnerResources';
  import SearchAutocompleteDropdown from './SearchAutocompleteDropdown';

  export default {
    name: 'LibrarySearchBar',
    components: {
      SearchAutocompleteDropdown,
    },
    mixins: [commonCoreStrings],
    setup() {
      const { user_id } = useUser();
      const { keyWordAutoCompleteHandler, autoCompleteSuggestions } = injectBaseSearch();
      const { recentSearches, addSearch } = useRecentSearches(user_id);
      const { resumableContentNodes } = useLearnerResources();
      const { windowIsSmall } = useKResponsiveWindow();
      const isFocused = ref(false);
      const hoveredFilter = ref(null);

      return {
        keyWordAutoCompleteHandler,
        autoCompleteSuggestions,
        recentSearches,
        addSearch,
        resumableContentNodes,
        windowIsSmall,
        isFocused,
        hoveredFilter,
      };
    },
    props: {
      value: {
        type: String,
        default: '',
      },
      placeholder: {
        type: String,
        default: '',
      },
    },
    computed: {
      inputId() {
        return `library-search-input-${this._uid}`;
      },
      searchButtonStyles() {
        return {
          minWidth: '48px',
          padding: '0',
          borderRadius: '0 4px 4px 0',
        };
      },
      showDropdown() {
        if (!this.isFocused) return false;
        if (this.value) {
          // Typing state: show when we have suggestions
          return this.currentSuggestions.length > 0;
        }
        // Focus state (no query): show when we have history or recent searches
        return this.historyItems.length > 0 || this.recentSearchTerms.length > 0;
      },
      historyItems() {
        if (!this.resumableContentNodes) return [];
        return this.resumableContentNodes.slice(0, 5);
      },
      recentSearchTerms() {
        return this.recentSearches || [];
      },
      currentSuggestions() {
        return this.autoCompleteSuggestions || [];
      },
      highlightSegments() {
        if (!this.hoveredFilter || !this.value) return null;
        return getMatchedWordSegments(this.value, this.hoveredFilter);
      },
    },
    methods: {
      handleInput(event) {
        const value = event.target.value;
        this.$emit('input', value);
        if (this.keyWordAutoCompleteHandler) {
          this.keyWordAutoCompleteHandler(value);
        }
      },
      handleSubmit() {
        this.isFocused = false;
        if (this.addSearch && this.value) {
          this.addSearch(this.value);
        }
        this.$emit('search', this.value);
      },
      handleFocus() {
        this.isFocused = true;
        this.$emit('focus');
      },
      handleBlur() {
        // Delay to allow click on dropdown items to register before hiding
        setTimeout(() => {
          this.isFocused = false;
        }, 200);
        this.$emit('blur');
      },
      handleSelectContent(item) {
        this.isFocused = false;
        this.$emit('selectContent', item);
      },
      handleSelectSearch(term) {
        this.isFocused = false;
        this.$emit('input', term);
        this.$emit('search', term);
      },
      handleSelectFilter(filter) {
        this.hoveredFilter = null;
        this.isFocused = false;
        this.$emit('selectFilter', filter);
      },
      handleHoverFilter(filter) {
        this.hoveredFilter = filter;
      },
      handleClear() {
        this.$emit('clear');
        this.$emit('input', '');
        if (this.keyWordAutoCompleteHandler) {
          this.keyWordAutoCompleteHandler('');
        }
        this.$refs.searchInput.focus();
      },
    },
    $trs: {
      allFilters: {
        message: 'All filters',
        context: 'Button text to open the full filter panel modal',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .library-search-bar {
    position: relative;
    width: 100%;
  }

  .search-row {
    position: relative;
    display: flex;
    align-items: center;
    height: 48px;
    border: 1px solid;
    border-radius: 4px;
  }

  .search-input {
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0 12px;
    font-size: 16px;
    background: transparent;
    border: 0;
    outline: none;

    &::placeholder {
      opacity: 0.6;
    }

    /* Remove browser-default search input clear icon */
    &::-webkit-search-cancel-button {
      display: none;
    }
  }

  .search-actions {
    display: flex;
    flex-shrink: 0;
    gap: 4px;
    align-items: center;
    padding-inline-end: 4px;
  }

  .search-input-overlay {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    display: flex;
    align-items: center;
    padding: 0 12px;
    font-size: 16px;
    color: transparent;
    pointer-events: none;
  }

  .highlight-matched {
    padding: 1px 2px;
    border-radius: 3px;
    opacity: 0.5;
  }

</style>
