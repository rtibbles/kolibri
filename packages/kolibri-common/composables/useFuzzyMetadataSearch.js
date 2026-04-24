import { watch } from 'vue';
import { get } from '@vueuse/core';
import { SearcherFactory, Query, Config } from '@m31coding/fuzzy-search';
import { coreString } from 'kolibri/uiText/commonCoreStrings';

/**
 * Candidate words that should also match learning activities.
 * These supplement the translated label so that related terms
 * (e.g. "video" for WATCH) trigger a match in autocomplete.
 */
const ACTIVITY_SYNONYMS = {
  WATCH: ['video', 'movie', 'film', 'animation'],
  LISTEN: ['audio', 'podcast', 'music', 'song'],
  READ: ['book', 'article', 'text', 'document', 'story'],
  PRACTICE: ['exercise', 'quiz', 'test', 'drill', 'worksheet'],
  CREATE: ['make', 'build', 'draw', 'design', 'craft'],
  EXPLORE: ['interactive', 'game', 'simulation'],
  REFLECT: ['journal', 'review', 'self-assessment'],
};

/**
 * Composable for fuzzy matching against translated metadata labels.
 *
 * Builds a searchable index from the available labels in the current search context
 * (learning activities, categories, grade levels, accessibility options, resources
 * needed, languages) and provides instant client-side fuzzy matching.
 *
 * @param {Ref} searchableLabels - Reactive ref to globalLabels from useBaseSearch
 * @returns {{ search: (query: string) => Array<{label, filterKey, filterValue, type}> }}
 */
// Create a config that supports non-Latin scripts (Arabic, Cyrillic, Han, etc.)
function _createSearcherConfig() {
  const config = Config.createDefaultConfig();
  // Allow all Unicode characters for multilingual support
  config.normalizerConfig.allowCharacter = () => true;
  return config;
}

export default function useFuzzyMetadataSearch(searchableLabels) {
  const searcherConfig = _createSearcherConfig();
  let searcher = SearcherFactory.createSearcher(searcherConfig);
  let entityList = [];
  let indexVersion = 0;
  let builtVersion = -1;

  function _buildIndex() {
    const labels = get(searchableLabels);
    if (!labels) return;

    entityList = [];
    let idCounter = 0;

    // Learning activities: { KEY: value } mapping
    if (labels.learningActivitiesShown) {
      for (const [key, value] of Object.entries(labels.learningActivitiesShown)) {
        entityList.push({
          id: idCounter++,
          key,
          label: coreString(key),
          filterKey: 'learning_activities',
          filterValue: value,
          type: 'activity',
        });
      }
    }

    // Categories: nested { Label: { value, nested: {...} } } structure
    if (labels.libraryCategories) {
      _flattenCategories(labels.libraryCategories, entityList, idCounter);
      idCounter = entityList.length;
    }

    // Grade levels: array of SCREAMING_SNAKE keys
    if (labels.gradeLevelsList) {
      for (const key of labels.gradeLevelsList) {
        entityList.push({
          id: idCounter++,
          label: coreString(key),
          filterKey: 'grade_levels',
          filterValue: key,
          type: 'grade_level',
        });
      }
    }

    // Accessibility options: array of SCREAMING_SNAKE keys
    if (labels.accessibilityOptionsList) {
      for (const key of labels.accessibilityOptionsList) {
        entityList.push({
          id: idCounter++,
          label: coreString(key),
          filterKey: 'accessibility_labels',
          filterValue: key,
          type: 'accessibility',
        });
      }
    }

    // Resources needed: { KEY: value } mapping
    if (labels.resourcesNeeded) {
      for (const [key, value] of Object.entries(labels.resourcesNeeded)) {
        entityList.push({
          id: idCounter++,
          label: coreString(key),
          filterKey: 'learner_needs',
          filterValue: value,
          type: 'resource',
        });
      }
    }

    // Languages: array of { id, lang_name } objects
    if (labels.languagesList) {
      for (const lang of labels.languagesList) {
        entityList.push({
          id: idCounter++,
          label: lang.lang_name || lang.id,
          filterKey: 'languages',
          filterValue: lang.id,
          type: 'language',
        });
      }
    }

    // Rebuild the searcher index
    searcher = SearcherFactory.createSearcher(searcherConfig);
    if (entityList.length > 0) {
      searcher.indexEntities(
        entityList,
        e => e.id,
        e => {
          const terms = [e.label];
          if (e.type === 'activity' && ACTIVITY_SYNONYMS[e.key]) {
            terms.push(...ACTIVITY_SYNONYMS[e.key]);
          }
          return terms;
        },
      );
    }
  }

  // Build index initially and mark dirty when labels change
  _buildIndex();
  builtVersion = indexVersion;
  watch(
    searchableLabels,
    () => {
      indexVersion++;
    },
    { deep: true },
  );

  /**
   * Search the metadata labels index with fuzzy matching.
   * @param {string} query - Search query string
   * @returns {Array<{label, filterKey, filterValue, type}>}
   */
  function search(query) {
    if (!query || query.length < 2) {
      return [];
    }

    // Rebuild index lazily if labels have changed
    if (builtVersion !== indexVersion) {
      _buildIndex();
      builtVersion = indexVersion;
    }

    const result = searcher.getMatches(new Query(query, 3));
    return result.matches.map(match => match.entity);
  }

  /**
   * Given the current keywords and a selected filter, remove the word(s)
   * from keywords that triggered the match for that filter.
   * @param {string} keywords - Current search keywords string
   * @param {Object} filter - The selected filter entity
   * @returns {string} Keywords with matched words removed
   */
  function removeMatchedWords(keywords, filter) {
    if (!keywords || !filter) return keywords || '';
    const terms = _getMatchableTerms(filter);
    const inputWords = keywords.split(/\s+/);
    const remaining = inputWords.filter(word => {
      const lower = word.toLowerCase();
      return !terms.some(term => term.startsWith(lower) || lower.startsWith(term));
    });
    return remaining.join(' ').trim();
  }

  return { search, removeMatchedWords };
}

/**
 * Build a list of lowercase terms that a filter could have been matched by.
 * Includes the full label, individual words of multi-word labels,
 * and activity synonyms where applicable.
 */
function _getMatchableTerms(filter) {
  const terms = [filter.label.toLowerCase()];
  const words = filter.label.toLowerCase().split(/\s+/);
  if (words.length > 1) terms.push(...words);
  if (filter.type === 'activity' && filter.key && ACTIVITY_SYNONYMS[filter.key]) {
    terms.push(...ACTIVITY_SYNONYMS[filter.key].map(s => s.toLowerCase()));
  }
  return terms;
}

/**
 * Split keywords into segments indicating which words match the given filter.
 * Used to render highlight overlays in the search input.
 *
 * @param {string} keywords - Current search keywords string
 * @param {Object} filter - The filter entity being hovered
 * @returns {Array<{text: string, matched: boolean}>} Segments with whitespace preserved
 */
export function getMatchedWordSegments(keywords, filter) {
  if (!keywords || !filter) return [{ text: keywords || '', matched: false }];
  const terms = _getMatchableTerms(filter);
  // Split while preserving whitespace as separate segments
  const tokens = keywords.split(/(\s+)/);
  return tokens.map(token => {
    if (/^\s+$/.test(token)) {
      return { text: token, matched: false };
    }
    const lower = token.toLowerCase();
    const matched = terms.some(term => term.startsWith(lower) || lower.startsWith(term));
    return { text: token, matched };
  });
}

/**
 * Recursively flatten nested category structure into a flat list.
 */
function _flattenCategories(categories, list, startId) {
  let id = startId;
  for (const [key, info] of Object.entries(categories)) {
    list.push({
      id: id++,
      key,
      label: coreString(key),
      filterKey: 'categories',
      filterValue: info.value,
      type: 'category',
    });
    if (info.nested && Object.keys(info.nested).length > 0) {
      id = _flattenCategories(info.nested, list, id);
    }
  }
  return id;
}
