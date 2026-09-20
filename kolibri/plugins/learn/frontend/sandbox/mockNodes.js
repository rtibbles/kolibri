// Mock content nodes for the thumbnail sandbox - Development only
// A spread of metadata combinations to exercise composed placeholder thumbnails.
import Categories from 'kolibri-constants/labels/Subjects';
import LearningActivities from 'kolibri-constants/labels/LearningActivities';
import GradeLevels from 'kolibri-constants/labels/Levels';
import { ContentNodeKinds } from 'kolibri/constants';

function makeNode(idSeed, overrides) {
  const id = (idSeed.toString(16).padStart(8, '0') + 'abcdef0123456789abcdef01').slice(0, 32);
  const contentId = (
    (idSeed * 31).toString(16).padStart(8, '0') + '9876543210fedcba98765432'
  ).slice(0, 32);
  return {
    id,
    content_id: contentId,
    title: 'Untitled',
    kind: ContentNodeKinds.TOPIC,
    is_leaf: false,
    thumbnail: null,
    parent: 'f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0',
    channel_id: 'c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
    learning_activities: [],
    categories: [],
    grade_levels: [],
    description: '',
    duration: null,
    progress_fraction: 0,
    ...overrides,
  };
}

// Twelve categories that each resolve to a distinct KDS icon (no dedup), so a
// rollup of the first N exercises an N-mark constellation cleanly.
const DISTINCT_CATEGORY_POOL = [
  Categories.MATHEMATICS,
  Categories.SCIENCES,
  Categories.READING_AND_WRITING,
  Categories.SOCIAL_SCIENCES,
  Categories.ARTS,
  Categories.HISTORY,
  Categories.COMPUTER_SCIENCE,
  Categories.DAILY_LIFE,
  Categories.CURRENT_EVENTS,
  Categories.ENVIRONMENT,
  Categories.FINANCIAL_LITERACY,
  Categories.MEDIA_LITERACY,
];

const constellationFolders = DISTINCT_CATEGORY_POOL.map((_, i) =>
  makeNode(30 + i, {
    title: `Folder rolling up ${i + 1} categor${i ? 'ies' : 'y'}`,
    included_categories: DISTINCT_CATEGORY_POOL.slice(0, i + 1),
  }),
);

export default [
  makeNode(1, {
    title: 'Algebra basics',
    categories: [Categories.ALGEBRA],
    grade_levels: [GradeLevels.UPPER_PRIMARY],
  }),
  makeNode(2, {
    title: 'Introduction to biology',
    categories: [Categories.BIOLOGY, Categories.CHEMISTRY],
    grade_levels: [GradeLevels.LOWER_SECONDARY],
  }),
  makeNode(3, {
    title: 'Reading comprehension',
    categories: [Categories.READING_COMPREHENSION],
    grade_levels: [GradeLevels.PRESCHOOL],
  }),
  makeNode(4, {
    title: 'World history',
    categories: [Categories.HISTORY],
    grade_levels: [GradeLevels.UPPER_SECONDARY],
  }),
  makeNode(5, {
    title: 'Music appreciation',
    categories: [Categories.MUSIC],
    grade_levels: [GradeLevels.LOWER_PRIMARY],
  }),
  makeNode(6, {
    title: 'Learn to code',
    categories: [Categories.PROGRAMMING],
    grade_levels: [GradeLevels.TERTIARY],
  }),
  // Sibling topics in the same subject - should look related but distinguishable
  makeNode(7, {
    title: 'Fractions',
    categories: [Categories.ARITHMETIC],
    grade_levels: [GradeLevels.LOWER_PRIMARY],
  }),
  makeNode(8, {
    title: 'Decimals',
    categories: [Categories.ARITHMETIC],
    grade_levels: [GradeLevels.LOWER_PRIMARY],
  }),
  makeNode(9, {
    title: 'Percentages',
    categories: [Categories.ARITHMETIC],
    grade_levels: [GradeLevels.LOWER_PRIMARY],
  }),
  makeNode(10, {
    title: 'Topic with no metadata',
  }),
  // Folders carry no authored categories; the backend aggregates descendant
  // categories into included_categories. These exercise that fallback path.
  // Same family (all SCIENCES) - icons dedupe to one sciencesResource glyph.
  makeNode(19, {
    title: 'Science (folder) - dedupes to one glyph',
    included_categories: [Categories.BIOLOGY, Categories.CHEMISTRY, Categories.PHYSICS],
  }),
  // One example of every constellation size, 1 through 12, each rolling up that
  // many distinct-icon categories (see DISTINCT_CATEGORY_POOL below).
  ...constellationFolders,
  makeNode(11, {
    title: 'Photosynthesis explained',
    kind: ContentNodeKinds.VIDEO,
    is_leaf: true,
    learning_activities: [LearningActivities.WATCH],
    categories: [Categories.BIOLOGY],
    grade_levels: [GradeLevels.LOWER_SECONDARY],
    duration: 372,
  }),
  makeNode(12, {
    title: 'Practice: solving equations',
    kind: ContentNodeKinds.EXERCISE,
    is_leaf: true,
    learning_activities: [LearningActivities.PRACTICE, LearningActivities.REFLECT],
    categories: [Categories.ALGEBRA],
    grade_levels: [GradeLevels.LOWER_SECONDARY],
  }),
  makeNode(13, {
    title: 'A short story',
    kind: ContentNodeKinds.DOCUMENT,
    is_leaf: true,
    learning_activities: [LearningActivities.READ],
    categories: [Categories.LITERATURE],
    grade_levels: [GradeLevels.PRESCHOOL],
    duration: 600,
  }),
  makeNode(14, {
    title: 'Folk songs collection',
    kind: ContentNodeKinds.AUDIO,
    is_leaf: true,
    learning_activities: [LearningActivities.LISTEN],
    categories: [Categories.MUSIC],
    duration: 1500,
  }),
  makeNode(15, {
    title: 'Interactive simulation',
    kind: ContentNodeKinds.HTML5,
    is_leaf: true,
    learning_activities: [LearningActivities.EXPLORE],
  }),
  makeNode(16, {
    title: 'Mystery resource',
    kind: ContentNodeKinds.VIDEO,
    is_leaf: true,
  }),
  // Serious register: workplace training with three activities
  makeNode(18, {
    title: 'Workplace safety training',
    kind: ContentNodeKinds.VIDEO,
    is_leaf: true,
    learning_activities: [
      LearningActivities.WATCH,
      LearningActivities.READ,
      LearningActivities.PRACTICE,
    ],
    categories: [Categories.SKILLS_TRAINING],
    grade_levels: [GradeLevels.WORK_SKILLS],
    duration: 900,
  }),
  // Copy of "A short story" in another channel: same content_id, different node id
  makeNode(17, {
    title: 'A short story (copy in another channel)',
    content_id: ((13 * 31).toString(16).padStart(8, '0') + '9876543210fedcba98765432').slice(0, 32),
    kind: ContentNodeKinds.DOCUMENT,
    is_leaf: true,
    learning_activities: [LearningActivities.READ],
    categories: [Categories.LITERATURE],
    grade_levels: [GradeLevels.PRESCHOOL],
    duration: 600,
  }),
];
