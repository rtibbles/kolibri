import { render } from '@testing-library/vue';
import Categories from 'kolibri-constants/labels/Subjects';
import GradeLevels from 'kolibri-constants/labels/Levels';
import ComposedThumbnail from '../index.vue';

// describe, it, expect are Jest globals — do NOT import them

function makeNode(overrides = {}) {
  return {
    id: '0000000aabcdef0123456789abcdef01',
    content_id: '000000c89876543210fedcba98765432',
    kind: 'video',
    is_leaf: true,
    categories: [],
    grade_levels: [],
    ...overrides,
  };
}

function renderThumbnail(node) {
  return render(ComposedThumbnail, { props: { contentNode: node } });
}

const subjectIcons = container => container.querySelectorAll('[data-testid="subject-icon"]');
const blobNodes = container => container.querySelectorAll('[data-testid="blob"]');
const blobPaths = container => [...blobNodes(container)].map(path => path.getAttribute('d'));

// Two node ids chosen to hash to different hues (the wheel has only 8 hues, so
// arbitrary ids can collide). RED_ID -> red, BLUE_ID -> blue.
const RED_ID = '00abcdef0123456789abcdef01234567';
const BLUE_ID = '06abcdef0123456789abcdef01234567';

// Fourteen categories that each resolve to a distinct KDS icon (no dedup),
// for exercising the constellation cap.
const DISTINCT_CATEGORIES = [
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
  Categories.MENTAL_HEALTH,
  Categories.PUBLIC_HEALTH,
];

describe('ComposedThumbnail', () => {
  it('is decorative: root has aria-hidden', () => {
    const { container } = renderThumbnail(makeNode());
    const root = container.querySelector('[data-testid="composed-thumbnail"]');
    expect(root).toHaveAttribute('aria-hidden', 'true');
  });

  describe('shape and colour seeds', () => {
    it('renders identically for the same node', () => {
      const a = renderThumbnail(makeNode()).container.innerHTML;
      const b = renderThumbnail(makeNode()).container.innerHTML;
      expect(a).toEqual(b);
    });

    it('keeps blob shape across copies of a resource, recolouring by node id', () => {
      // Same content_id (a copy in another channel), different node id.
      const shared = 'cccccccc9876543210fedcba98765432';
      const a = renderThumbnail(makeNode({ content_id: shared, id: RED_ID })).container;
      const b = renderThumbnail(makeNode({ content_id: shared, id: BLUE_ID })).container;
      // Shape is seeded from content_id, so the blob geometry is identical.
      expect(blobPaths(a)).toEqual(blobPaths(b));
      // Hue is seeded from the node id, so the two recolour differently.
      expect(a.innerHTML).not.toEqual(b.innerHTML);
    });

    it('changes blob shape for a different content_id', () => {
      const a = renderThumbnail(
        makeNode({ content_id: 'aaaaaaaa9876543210fedcba98765432', id: RED_ID }),
      ).container;
      const b = renderThumbnail(
        makeNode({ content_id: 'ffffffff9876543210fedcba98765432', id: RED_ID }),
      ).container;
      expect(blobPaths(a)).not.toEqual(blobPaths(b));
    });
  });

  describe('subject constellation', () => {
    it('renders one glyph per distinct category icon', () => {
      const { container } = renderThumbnail(
        makeNode({ categories: [Categories.BIOLOGY, Categories.HISTORY] }),
      );
      expect(subjectIcons(container).length).toEqual(2);
    });

    it('deduplicates categories that resolve to the same icon', () => {
      // BIOLOGY and CHEMISTRY both resolve to sciencesResource.
      const { container } = renderThumbnail(
        makeNode({ categories: [Categories.BIOLOGY, Categories.CHEMISTRY] }),
      );
      expect(subjectIcons(container).length).toEqual(1);
    });

    it('caps the constellation at twelve glyphs', () => {
      const { container } = renderThumbnail(makeNode({ categories: DISTINCT_CATEGORIES }));
      expect(DISTINCT_CATEGORIES.length).toBeGreaterThan(12);
      expect(subjectIcons(container).length).toEqual(12);
    });

    it('falls back to the kind glyph for an uncategorised leaf', () => {
      const { container } = renderThumbnail(makeNode({ categories: [] }));
      expect(subjectIcons(container).length).toEqual(1);
    });

    it('falls back to a folder glyph for an uncategorised topic', () => {
      const { container } = renderThumbnail(
        makeNode({ is_leaf: false, kind: 'topic', categories: [] }),
      );
      expect(subjectIcons(container).length).toEqual(1);
    });

    it('uses included_categories when there are no authored categories (folder rollup)', () => {
      const { container } = renderThumbnail(
        makeNode({
          is_leaf: false,
          kind: 'topic',
          categories: [],
          included_categories: [Categories.BIOLOGY, Categories.HISTORY],
        }),
      );
      expect(subjectIcons(container).length).toEqual(2);
    });
  });

  it('does not render activity icons — those belong on the card', () => {
    const { container } = renderThumbnail(
      makeNode({ categories: [Categories.BIOLOGY], learning_activities: ['watch', 'read'] }),
    );
    expect(container.querySelectorAll('[data-testid="activity-icon"]').length).toEqual(0);
  });

  describe('blobs', () => {
    it('renders two or three blobs', () => {
      const { container } = renderThumbnail(makeNode());
      const count = blobNodes(container).length;
      expect(count).toBeGreaterThanOrEqual(2);
      expect(count).toBeLessThanOrEqual(3);
    });

    it('gives every blob a fill-opacity', () => {
      const { container } = renderThumbnail(makeNode());
      for (const blob of blobNodes(container)) {
        expect(blob).toHaveAttribute('fill-opacity');
      }
    });
  });

  it('varies palette intensity with grade level', () => {
    // Same node and categories, different grade band — the shades shift, so the
    // rendered output differs.
    const young = renderThumbnail(
      makeNode({ categories: [Categories.BIOLOGY], grade_levels: [GradeLevels.PRESCHOOL] }),
    ).container.innerHTML;
    const tertiary = renderThumbnail(
      makeNode({ categories: [Categories.BIOLOGY], grade_levels: [GradeLevels.TERTIARY] }),
    ).container.innerHTML;
    expect(young).not.toEqual(tertiary);
  });
});
