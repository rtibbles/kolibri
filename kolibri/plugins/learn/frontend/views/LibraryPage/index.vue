<template>

  <div :style="{ maxWidth: '1700px', margin: '0 auto' }">
    <transition name="delay-entry">
      <PostSetupModalGroup
        v-if="!(rootNodesLoading || searchLoading) && welcomeModalVisible"
        isOnMyOwnUser
        @cancel="hideWelcomeModal"
      />
      <MeteredConnectionNotificationModal
        v-else-if="usingMeteredConnection"
        @update="value => (allowDownloadOnMeteredConnection = value)"
      />
    </transition>
    <LearnAppBarPage
      :appBarTitle="appBarTitle"
      :loading="rootNodesLoading"
      :appearanceOverrides="{}"
      :deviceId="deviceId"
      :route="back"
    >
      <main class="main-grid">
        <!-- Search header: search bar + AI response message grouped together -->
        <div
          class="search-header"
          :style="{
            backgroundColor: $themeTokens.surface,
            borderColor: $themePalette.grey.v_300,
          }"
        >
          <LibrarySearchBar
            v-if="!isLocalLibraryEmpty || deviceId"
            data-testid="library-search-bar"
            :value="keywordsInput"
            @input="handleSearchInput"
            @search="handleSearch"
            @clear="handleClearSearch"
            @openFilters="showFilterModal = true"
            @selectContent="handleSelectContent"
            @selectFilter="handleSelectFilter"
          />

          <AIResponseSection
            v-if="!rootNodesLoading && !searchLoading"
            :messages="messages"
            :categoryChips="categoryChips"
          />

          <HorizontalFilterPills
            v-if="!rootNodesLoading && (!isLocalLibraryEmpty || deviceId)"
            data-testid="horizontal-filter-pills"
          />

          <div
            v-if="windowIsSmall"
            class="all-filters-row"
          >
            <KButton
              data-testid="all-filters-button-mobile"
              appearance="flat-button"
              icon="filter"
              :text="$tr('allFilters')"
              @click="showFilterModal = true"
            />
          </div>
        </div>

        <!--
          - If search is loading, show loader.
          - If there are no search results, show channels and resumable
          content.
          - Otherwise, show search results.
        -->
        <KCircularLoader
          v-if="rootNodesLoading || searchLoading"
          class="loader"
          type="indeterminate"
          :delay="false"
        />
        <div
          v-else-if="!displayingSearchResults && !rootNodesLoading"
          data-testid="channels"
        >
          <div>
            <h1
              v-if="!isLocalLibraryEmpty"
              class="channels-label"
            >
              {{ channelsLabel }}
            </h1>
            <div
              v-else-if="
                isLocalLibraryEmpty && isNetworkLibraryAvailable && !isLoadingNetworkLibraries
              "
            >
              <h1 class="channels-label">
                {{ channelsLabel }}
              </h1>
              <p
                data-testid="nothing-in-lib-label"
                class="nothing-in-lib-label"
              >
                {{ coreString('nothingInLibraryLearner') }}
              </p>
            </div>
            <NoResourcePage v-else />
          </div>

          <ChannelCardGroupGrid
            v-if="!isLocalLibraryEmpty"
            data-testid="channel-cards"
            class="grid"
            :contents="rootNodes"
            :deviceId="deviceId"
          />
          <!-- ResumableContentGrid mostly handles whether it renders or not internally !-->
          <!-- but we conditionalize it based on whether we are on another device's library page!-->
          <ResumableContentGrid
            v-if="!deviceId"
            data-testid="resumable-content"
            :currentCardViewStyle="currentCardViewStyle"
            @setCardStyle="style => (currentCardViewStyle = style)"
            @setSidePanelMetadataContent="content => (metadataSidePanelContent = content)"
          />
          <!-- Other Libraries -->
          <OtherLibraries
            v-if="showOtherLibraries"
            data-testid="other-libraries"
            :injectedtr="injecttr"
            @availableNetworkDevices="availableNetworkDevices"
            @isLoadingLibraries="isLoadingLibraries"
          />
        </div>

        <SearchResultsGrid
          v-else-if="displayingSearchResults"
          data-testid="search-results"
          :allowDownloads="allowDownloads"
          :results="results"
          :moreLoading="moreLoading"
          :searchMore="searchMore"
          :currentCardViewStyle="currentCardViewStyle"
          :searchLoading="searchLoading"
          :more="more"
          :exploreGroups="exploreGroups"
          @setCardStyle="style => (currentCardViewStyle = style)"
          @setSidePanelMetadataContent="content => (metadataSidePanelContent = content)"
        />
      </main>

      <!-- All filters side panel -->
      <SidePanelModal
        v-if="showFilterModal"
        data-testid="filter-modal"
        alignment="right"
        closeButtonIconType="close"
        @closePanel="showFilterModal = false"
      >
        <template #header>
          <h1 class="side-panel-title">{{ $tr('allFilters') }}</h1>
        </template>
        <SearchFiltersPanel
          ref="filterPanel"
          v-model="searchTerms"
          data-testid="filter-panel"
          accordion
          :hideKeywords="true"
        />
      </SidePanelModal>

      <!-- Side Panel for metadata -->
      <SidePanelModal
        v-if="metadataSidePanelContent && !rootNodesLoading"
        data-testid="side-panel-modal"
        alignment="right"
        @closePanel="metadataSidePanelContent = null"
        @shouldFocusFirstEl="findFirstEl()"
      >
        <template
          v-if="metadataSidePanelContent.learning_activities.length"
          #header
        >
          <!-- Flex styles tested in ie11 and look good. Ensures good spacing between
              multiple chips - not a common thing but just in case -->
          <div
            v-for="activity in metadataSidePanelContent.learning_activities"
            :key="activity"
            class="side-panel-chips"
            :class="
              $computedClass({
                '::after': {
                  content: '',
                  flex: 'auto',
                },
              })
            "
          >
            <LearningActivityChip
              class="chip"
              :kind="activity"
            />
          </div>
        </template>

        <BrowseResourceMetadata
          ref="resourcePanel"
          :content="metadataSidePanelContent"
          :showLocationsInChannel="true"
          :canDownloadExternally="canDownloadExternally && !deviceId"
        />
      </SidePanelModal>
      <TooltipTour
        v-if="tourActive && isTourActive('LibraryPage') && !isLearner"
        page="LibraryPage"
        @tourEnded="endTour('LibraryPage')"
      />
    </LearnAppBarPage>
  </div>

</template>


<script>

  import { get, set } from '@vueuse/core';

  import { onMounted, getCurrentInstance, ref, watch } from 'vue';
  import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
  import pluginData from 'kolibri-plugin-data';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import useUser from 'kolibri/composables/useUser';
  import { handleApiError, clearError } from 'kolibri/utils/appError';
  import samePageCheckGenerator from 'kolibri-common/utils/samePageCheckGenerator';
  import ContentNodeResource from 'kolibri-common/apiResources/ContentNodeResource';
  import { mapState } from 'vuex';
  import checkMeteredConnection from 'kolibri-common/utils/checkMeteredConnection';
  import LearningActivityChip from 'kolibri-common/components/ResourceDisplayAndSearch/LearningActivityChip.vue';
  import { searchKeys } from 'kolibri-common/composables/useBaseSearch';
  import SidePanelModal from 'kolibri-common/components/SidePanelModal';
  import SearchFiltersPanel from 'kolibri-common/components/SearchFiltersPanel';
  import useChannels from 'kolibri-common/composables/useChannels';
  import TooltipTour from 'kolibri/components/onboarding/TooltipTour';
  import useTour from 'kolibri/composables/useTour';
  import { pageLoading } from 'kolibri-common/composables/usePageLoading';
  import { KolibriStudioId, PageNames } from '../../constants';
  import useCardViewStyle from '../../composables/useCardViewStyle';
  import useContentLink from '../../composables/useContentLink';
  import useCoreLearn from '../../composables/useCoreLearn';
  import useDeviceSettings from '../../composables/useDeviceSettings';
  import {
    currentDeviceData,
    setCurrentDevice,
    StudioNotAllowedError,
  } from '../../composables/useDevices';
  import useSearch from '../../composables/useSearch';
  import useLearnerResources from '../../composables/useLearnerResources';
  import BrowseResourceMetadata from '../BrowseResourceMetadata';
  import commonLearnStrings from '../commonLearnStrings';
  import ChannelCardGroupGrid from '../ChannelCardGroupGrid';
  import SearchResultsGrid from '../SearchResultsGrid';
  import AIResponseSection from '../SearchResultsGrid/AIResponseSection';
  import LearnAppBarPage from '../LearnAppBarPage';
  import PostSetupModalGroup from '../../../../device/frontend/views/PostSetupModalGroup.vue';
  import HorizontalFilterPills from './HorizontalFilterPills';
  import LibrarySearchBar from './LibrarySearchBar';
  import MeteredConnectionNotificationModal from './MeteredConnectionNotificationModal.vue';
  import ResumableContentGrid from './ResumableContentGrid';
  import OtherLibraries from './OtherLibraries';
  import NoResourcePage from './NoResourcePage';

  const welcomeDismissalKey = 'DEVICE_WELCOME_MODAL_DISMISSED';

  export default {
    name: 'LibraryPage',
    metaInfo() {
      return {
        title: this.learnString('learnLabel'),
      };
    },
    components: {
      AIResponseSection,
      BrowseResourceMetadata,
      ChannelCardGroupGrid,
      SidePanelModal,
      LearningActivityChip,
      MeteredConnectionNotificationModal,
      ResumableContentGrid,
      SearchResultsGrid,
      SearchFiltersPanel,
      LearnAppBarPage,
      OtherLibraries,
      PostSetupModalGroup,
      NoResourcePage,
      TooltipTour,
      LibrarySearchBar,
      HorizontalFilterPills,
    },
    mixins: [commonLearnStrings, commonCoreStrings],
    setup(props) {
      const currentInstance = getCurrentInstance().proxy;
      const store = currentInstance.$store;
      const router = currentInstance.$router;
      const { tourActive, isTourActive, startTour, endTour, resumeTour } = useTour();
      const { isUserLoggedIn, isCoach, isAdmin, isSuperuser, isLearner, user_id } = useUser();
      const { allowDownloadOnMeteredConnection } = useDeviceSettings();
      const {
        searchTerms,
        displayingSearchResults,
        searchLoading,
        moreLoading,
        results,
        more,
        search,
        searchMore,
        removeMatchedWords,
        currentRoute,
        messages,
      } = useSearch();
      search();
      const { fetchResumableContentNodes } = useLearnerResources();

      const { canAddDownloads, canDownloadExternally } = useCoreLearn();
      const { currentCardViewStyle } = useCardViewStyle();
      const { back, genContentLinkBackLinkCurrentPage } = useContentLink();
      const { deviceName } = currentDeviceData();
      const { fetchChannels } = useChannels();
      const { windowIsSmall } = useKResponsiveWindow();

      onMounted(() => {
        const keywords = currentRoute().query.keywords;
        if (keywords && keywords.length) {
          set(keywordsInput, keywords);
          search(keywords);
        }
      });

      const rootNodes = ref([]);
      const rootNodesLoading = ref(false);
      const keywordsInput = ref('');

      function _showChannels(channels, baseurl) {
        if (get(isUserLoggedIn) && !baseurl) {
          fetchResumableContentNodes();
        }
        const shouldResolve = samePageCheckGenerator();
        return ContentNodeResource.fetchCollection({
          getParams: {
            parent__isnull: true,
            include_coach_content: get(isAdmin) || get(isCoach) || get(isSuperuser),
            baseurl,
          },
        }).then(
          channelCollection => {
            if (shouldResolve()) {
              // we want them to be in the same order as the channels list
              set(
                rootNodes,
                channels
                  .map(channel => {
                    const node = channelCollection.find(n => n.channel_id === channel.id);
                    if (node) {
                      // The `channel` comes with additional data that is
                      // not returned from the ContentNodeResource.
                      // Namely thumbnail, description and tagline (so far)
                      node.title = channel.name || node.title;
                      node.thumbnail = channel.thumbnail;
                      node.description = channel.tagline || channel.description;
                      return node;
                    }
                  })
                  .filter(Boolean),
              );

              pageLoading.value = false;
              clearError();
              store.commit('SET_PAGE_NAME', PageNames.LIBRARY);
              set(rootNodesLoading, false);
            }
          },
          error => {
            pageLoading.value = false;
            if (shouldResolve()) {
              handleApiError({ error, reloadOnReconnect: true });
            }
            set(rootNodesLoading, false);
          },
        );
      }

      function _showLibrary(baseurl) {
        return fetchChannels({ baseurl }).then(channels => {
          if (!channels.length && baseurl) {
            router.replace({ name: PageNames.LIBRARY });
            return;
          }

          const query = currentRoute().query;

          if (searchKeys.some(key => query[key])) {
            // If currently on a route with search terms
            // just finish early and let the component handle loading
            pageLoading.value = false;
            clearError();
            store.commit('SET_PAGE_NAME', PageNames.LIBRARY);
            set(rootNodesLoading, false);
            return Promise.resolve();
          }
          return _showChannels(channels, baseurl);
        });
      }

      function showLibrary() {
        set(rootNodesLoading, true);
        pageLoading.value = true;
        if (props.deviceId) {
          return setCurrentDevice(props.deviceId)
            .then(device => {
              const baseurl = device.base_url;
              // _showLibrary should unset the rootNodesLoading
              return _showLibrary(baseurl);
            })
            .catch(error => {
              if (error === StudioNotAllowedError) {
                router.replace({ name: PageNames.LIBRARY });
                return;
              }
              return Promise.reject(error);
            });
        }
        return _showLibrary();
      }

      watch(() => props.deviceId, showLibrary);

      watch(displayingSearchResults, () => {
        if (!displayingSearchResults.value && !rootNodes.value.length) {
          showLibrary();
        }
      });

      showLibrary();

      return {
        allowDownloadOnMeteredConnection,
        canAddDownloads,
        canDownloadExternally,
        displayingSearchResults,
        searchTerms,
        searchLoading,
        moreLoading,
        results,
        more,
        searchMore,
        removeMatchedWords,
        currentCardViewStyle,
        deviceName,
        back,
        rootNodesLoading,
        rootNodes,
        pageLoading,
        isUserLoggedIn,
        isLearner,
        tourActive,
        isTourActive,
        startTour,
        endTour,
        resumeTour,
        userId: user_id,
        messages,
        keywordsInput,
        windowIsSmall,
        genContentLinkBackLinkCurrentPage,
      };
    },
    props: {
      deviceId: {
        type: String,
        default: null,
      },
    },
    data: function () {
      return {
        isLocalLibraryEmpty: false,
        metadataSidePanelContent: null,
        showFilterModal: false,
        usingMeteredConnection: true,
        isNetworkLibraryAvailable: true,
        isLoadingNetworkLibraries: true,
      };
    },
    computed: {
      ...mapState({
        welcomeModalVisibleState: 'welcomeModalVisible',
      }),
      allowDownloads() {
        return this.canAddDownloads && Boolean(this.deviceId);
      },
      appBarTitle() {
        return this.learnString(this.deviceId ? 'exploreLibraries' : 'learnLabel');
      },
      welcomeModalVisible() {
        return (
          this.welcomeModalVisibleState &&
          window.localStorage.getItem(`${welcomeDismissalKey}-${this.userId}`) !== 'true'
        );
      },
      showOtherLibraries() {
        const validUser = !this.deviceId && this.isUserLoggedIn;
        if (!validUser) {
          return false;
        }
        if (!pluginData.canCheckMeteredConnection) {
          return true;
        }
        if (this.allowDownloadOnMeteredConnection) {
          return true;
        }
        return !this.usingMeteredConnection;
      },
      channelsLabel() {
        if (this.deviceId) {
          if (this.deviceId === this.studioId) {
            return this.learnString('kolibriLibrary');
          } else {
            return this.$tr('libraryOf', { device: this.deviceName });
          }
        } else {
          return this.coreString('yourLibrary');
        }
      },
      studioId() {
        return KolibriStudioId;
      },
      exploreGroups() {
        // Group results by category metadata for "More to explore" section
        if (!this.results || !this.results.length) return [];
        const groups = {};
        for (const result of this.results) {
          if (result.categories && result.categories.length) {
            for (const cat of result.categories) {
              if (!groups[cat]) {
                groups[cat] = { label: this.coreString(cat), count: 0, items: [] };
              }
              groups[cat].count += 1;
              groups[cat].items.push(result);
            }
          }
        }
        return Object.values(groups);
      },
      categoryChips() {
        // Derive category chips from result metadata
        if (!this.results || !this.results.length) return [];
        const seen = {};
        const chips = [];
        for (const result of this.results) {
          if (result.categories && result.categories.length) {
            for (const cat of result.categories) {
              if (!seen[cat]) {
                seen[cat] = true;
                chips.push({ label: this.coreString(cat), value: cat });
              }
            }
          }
        }
        return chips;
      },
    },
    watch: {
      rootNodes(newNodes) {
        this.isLocalLibraryEmpty = !newNodes.length;
      },
      searchTerms() {
        this.showFilterModal = false;
      },
      pageLoading(newVal, oldVal) {
        if (oldVal && !newVal) {
          const isTourStarted = this.resumeTour(this.userId, 'LibraryPage');
          if (isTourStarted) {
            setTimeout(() => {
              this.startTour('LibraryPage');
            }, 3000);
          }
        }
      },
    },
    created() {
      const welcomeDismissalKey = 'DEVICE_WELCOME_MODAL_DISMISSED';

      if (window.sessionStorage.getItem(`${welcomeDismissalKey}-${this.userId}`) !== 'true') {
        this.$store.commit('SET_WELCOME_MODAL_VISIBLE', true);
      }

      // parallels logic for showOtherLibraries
      if (
        !this.deviceId &&
        this.isUserLoggedIn &&
        !this.allowDownloadOnMeteredConnection &&
        pluginData.canCheckMeteredConnection
      ) {
        checkMeteredConnection().then(isMetered => {
          this.usingMeteredConnection = isMetered;
        });
      }
    },
    methods: {
      hideWelcomeModal() {
        window.localStorage.setItem(`${welcomeDismissalKey}-${this.userId}`, true);
        this.$store.commit('SET_WELCOME_MODAL_VISIBLE', false);
        this.startTour('LibraryPage');
      },
      findFirstEl() {
        this.$refs.resourcePanel.focusFirstEl();
      },
      handleSearchInput(value) {
        this.keywordsInput = value;
      },
      handleSearch(value) {
        this.keywordsInput = value;
        this.searchTerms = { ...this.searchTerms, keywords: value };
      },
      handleClearSearch() {
        this.keywordsInput = '';
        this.searchTerms = { ...this.searchTerms, keywords: '' };
      },
      handleSelectContent(item) {
        const link = this.genContentLinkBackLinkCurrentPage(item.id, true);
        if (link) {
          this.$router.push(link);
        }
      },
      handleSelectFilter(filter) {
        if (filter.filterKey && filter.filterValue) {
          const current = { ...(this.searchTerms[filter.filterKey] || {}) };
          current[filter.filterValue] = true;
          const updatedKeywords = this.removeMatchedWords(this.keywordsInput, filter);
          this.keywordsInput = updatedKeywords;
          this.searchTerms = {
            ...this.searchTerms,
            [filter.filterKey]: current,
            keywords: updatedKeywords,
          };
        }
      },
      injecttr(...args) {
        return this.$tr(...args);
      },
      availableNetworkDevices(e) {
        this.isNetworkLibraryAvailable = e;
      },
      isLoadingLibraries(isLoading) {
        this.isLoadingNetworkLibraries = isLoading;
      },
    },
    $trs: {
      allFilters: {
        message: 'All filters',
        context: 'Title of the modal dialog that shows all available search filters',
      },
      libraryOf: {
        message: 'Library of {device}',
        context: 'A header for a device Library',
      },
      /* eslint-disable kolibri/vue-no-unused-translations */
      // These are mostly used in the OtherLibraries component and passed in from here.
      otherLibraries: {
        message: 'Other libraries',
        context: 'Header for viewing other remote content Library',
      },
      searchingOtherLibrary: {
        message: 'Searching for libraries around you.',
        context: 'Connection state for showing other library',
      },
      noOtherLibraries: {
        message: 'No other libraries around you right now',
        context: 'Connection state when there is no other libraries around',
      },
      showingAllLibraries: {
        message: 'Showing all available libraries around you.',
        context: 'Connection state when the device is connected and shows other libraries',
      },
      moreLibraries: {
        message: 'More',
        context: 'Title section containing unpinned devices',
      },
      pinned: {
        message: 'Pinned',
        context: 'Sub heading for the pinned devices',
      },
      /* eslint-enable kolibri/vue-no-unused-translations */
    },
  };

</script>


<style lang="scss" scoped>

  @import '~kolibri-design-system/lib/styles/definitions';
  @import '../HybridLearningContentCard/card';

  $margin: 24px;

  .card-main-wrapper {
    @extend %dropshadow-1dp;

    position: relative;
    display: inline-flex;
    width: 100%;
    height: 130px;
    max-height: 258px;
    padding-bottom: $margin;
    text-decoration: none;
    vertical-align: top;
    border-radius: $radius;
    transition: box-shadow $core-time ease;

    &:hover {
      @extend %dropshadow-6dp;
    }

    &:focus {
      outline-width: 4px;
      outline-offset: 6px;
    }
  }

  .main-grid {
    padding: 0 24px 96px;
  }

  .channels-label {
    margin-bottom: 12px;
  }

  .nothing-in-lib-label {
    padding-top: 0;
    margin-top: 0;
  }

  .loader {
    margin-top: 60px;
  }

  .side-panel-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-start;
    margin-top: 8px;
    margin-left: -8px;
  }

  .chip {
    margin-bottom: 8px;
    margin-left: 8px;
  }

  .search-header {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px 20px;
    margin-bottom: 24px;
    border: 1px solid;
    border-radius: 8px;
  }

  .all-filters-row {
    display: flex;
    justify-content: center;
  }

  .side-panel-title {
    margin: 0;
    overflow: hidden;
    font-size: 18px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

</style>
