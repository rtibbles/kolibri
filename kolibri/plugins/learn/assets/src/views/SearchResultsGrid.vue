<template>

  <div v-if="!searchLoading">
    <!-- First section is the results title and the various display buttons  -->
    <!-- for interacting or updating the results   -->
    <h2
      class="results-title"
      data-test="search-results-title"
    >
      {{
        more
          ? coreString('uncountedAdditionalResults', { num: results.length })
          : $tr('results', { results: results.length })
      }}
    </h2>
    <SearchChips
      :searchTerms="searchTerms"
      @removeItem="removeFilterTag"
      @clearSearch="clearSearch"
    />
    <div
      v-if="messages.length && !messagesDismissed"
      class="search-messages"
      :style="{
        backgroundColor: $themeTokens.surface,
        borderColor: $themeTokens.primary,
      }"
    >
      <div class="search-messages-header">
        <KIconButton
          icon="close"
          size="small"
          class="dismiss-button"
          :ariaLabel="$tr('dismissMessages')"
          @click="dismissMessages"
        />
      </div>
      <div
        v-for="(message, i) in messages"
        :key="i"
        class="search-message"
        :style="{
          backgroundColor: $themeTokens.surfaceVariant,
          borderColor: $themeTokens.secondary,
          color: $themeTokens.text,
        }"
      >
        <p class="search-message-text">
          {{ message }}
        </p>
      </div>
    </div>
    <div
      v-if="!windowIsSmall && results.length && !hideCardViewToggle"
      class="toggle-view-buttons"
      data-test="toggle-view-buttons"
    >
      <KIconButton
        icon="menu"
        :ariaLabel="$tr('viewAsList')"
        :color="$themeTokens.text"
        :tooltip="$tr('viewAsList')"
        :disabled="currentCardViewStyle === 'list'"
        @click="toggleCardView('list')"
      />
      <KIconButton
        icon="channel"
        :ariaLabel="$tr('viewAsGrid')"
        :color="$themeTokens.text"
        :tooltip="$tr('viewAsGrid')"
        :disabled="currentCardViewStyle === 'card'"
        @click="toggleCardView('card')"
      />
    </div>
    <!-- Grid of search results  -->
    <LibraryAndChannelBrowserMainContent
      :contents="results"
      :allowDownloads="allowDownloads"
      data-test="search-results-card-grid"
      :currentCardViewStyle="currentCardViewStyle"
      :gridType="gridType"
      @openCopiesModal="copies => (displayedCopies = copies)"
      @toggleInfoPanel="$emit('setSidePanelMetadataContent', $event)"
    />
    <!-- conditionally displayed button if there are additional results -->
    <KButton
      v-if="more"
      :text="coreString('viewMoreAction')"
      appearance="basic-link"
      :disabled="moreLoading"
      class="filter-action-button"
      data-test="more-results-button"
      @click="searchMore"
    />

    <CopiesModal
      v-if="displayedCopies.length"
      :copies="displayedCopies"
      @closeModal="displayedCopies = []"
    />
  </div>

</template>


<script>

  import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import SearchChips from 'kolibri-common/components/SearchChips';
  import CopiesModal from './CopiesModal';
  import LibraryAndChannelBrowserMainContent from './LibraryAndChannelBrowserMainContent';

  export default {
    name: 'SearchResultsGrid',
    components: {
      CopiesModal,
      LibraryAndChannelBrowserMainContent,
      SearchChips,
    },
    mixins: [commonCoreStrings],
    setup() {
      const { windowIsSmall } = useKResponsiveWindow();
      return {
        windowIsSmall,
      };
    },
    props: {
      allowDownloads: {
        type: Boolean,
        default: false,
      },
      currentCardViewStyle: {
        type: String,
        default: 'card',
      },
      hideCardViewToggle: {
        type: Boolean,
        default: false,
      },
      clearSearch: {
        type: Function,
        default: () => {},
      },
      more: {
        type: Object,
        default: null,
      },
      moreLoading: {
        type: Boolean,
        default: false,
      },
      results: {
        type: Array,
        default: () => [],
      },
      removeFilterTag: {
        type: Function,
        default: () => {},
      },
      searchLoading: {
        type: Boolean,
        default: false,
      },
      searchMore: {
        type: Function,
        default: () => {},
      },
      searchTerms: {
        type: Object,
        default: () => {},
      },
      messages: {
        type: Array,
        default: () => [],
      },
    },
    data() {
      return {
        displayedCopies: [],
        messagesDismissed: false,
      };
    },
    computed: {
      gridType() {
        return this.windowBreakpoint > 6 ? 2 : 1;
      },
    },
    watch: {
      messages() {
        // Reset dismissal state when new messages arrive
        this.messagesDismissed = false;
      },
    },
    methods: {
      toggleCardView(value) {
        this.$emit('setCardStyle', value);
      },
      dismissMessages() {
        this.messagesDismissed = true;
      },
    },
    $trs: {
      results: {
        message: '{results, number, integer} {results, plural, one {result} other {results}}',
        context: 'Number of results for a given term after a Library search.',
      },
      viewAsList: {
        message: 'View as list',
        context: 'Label for a button used to view resources as a list.',
      },
      viewAsGrid: {
        message: 'View as grid',
        context: 'Label for a button used to view resources as a grid.',
      },
      dismissMessages: {
        message: 'Dismiss messages',
        context: 'Label for a button used to dismiss search context messages.',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .results-title {
    display: inline-block;
    margin-bottom: 24px;
  }

  .toggle-view-buttons {
    float: right;
  }

  .filter-action-button {
    display: inline-block;
    margin: 4px;
    margin-left: 8px;
  }

  .search-messages {
    position: relative;
    padding: 16px;
    margin-bottom: 24px;
    border: 2px solid;
    border-radius: 8px;
  }

  .search-messages-header {
    position: absolute;
    top: 8px;
    right: 8px;
  }

  .dismiss-button {
    opacity: 0.7;

    &:hover {
      opacity: 1;
    }
  }

  .search-message {
    display: block;
    width: fit-content;
    max-width: calc(100% - 48px);
    padding: 12px 16px;
    margin-bottom: 16px;
    border: 2px solid;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

    &:last-child {
      margin-bottom: 0;
    }
  }

  .search-message-text {
    padding-right: 16px;
    margin: 0;
    font-size: 14px;
    line-height: 1.4;
  }

</style>
