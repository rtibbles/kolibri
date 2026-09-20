<template>

  <div
    class="composed-thumbnail"
    data-testid="composed-thumbnail"
    :style="{ backgroundColor: bgColor }"
    aria-hidden="true"
  >
    <svg
      class="blob-layer"
      :viewBox="`0 0 ${canvas.w} ${canvas.h}`"
      preserveAspectRatio="xMidYMid slice"
    >
      <path
        v-for="(blob, i) in blobs"
        :key="`blob-${i}`"
        data-testid="blob"
        :d="blob.d"
        :fill="blob.color"
        :fill-opacity="blob.opacity"
      />
    </svg>

    <KIcon
      v-for="(el, i) in iconElements"
      :key="`el-${i}`"
      :icon="el.icon"
      class="placed-icon"
      :data-testid="el.test"
      :style="el.style"
      :color="el.color"
    />
  </div>

</template>


<script>

  import { computed } from 'vue';
  import GradeLevels from 'kolibri-constants/labels/Levels';
  import { themePalette } from 'kolibri-design-system/lib/styles/theme';
  import {
    hashString,
    makePrng,
    resolveCategory,
    seededHue,
    HUE_WHEEL,
    makeBlob,
    withIncludedFallback,
  } from './utils';

  // Aspect ratios of the card frames this placeholder fills, exported so each
  // card names the ratio it uses explicitly rather than repeating a literal (or
  // silently relying on the default).
  export const DEFAULT_THUMBNAIL_ASPECT_RATIO = 16 / 9;
  export const WIDE_THUMBNAIL_ASPECT_RATIO = 2.5;

  // The composition is deliberately spare: organic background blobs plus one
  // subject constellation. No decorative ornament, no rotation - the
  // constellation is the focal point and the identity-seeded colour does the
  // rest. Everything else (activities, duration, etc.) belongs on the card.

  // Two or three background blobs, anchored at the corners and sized larger when
  // there are fewer. With only two they take opposite corners so the card stays
  // balanced. The subject glyphs take one fixed shade regardless of what sits
  // behind them, so the blobs can range freely without unsettling the
  // central constellation.
  const BLOB_ANCHORS = [
    { x: 0, y: 0.15 }, // top-left
    { x: 1, y: 0.15 }, // top-right
    { x: 1, y: 0.85 }, // bottom-right
    { x: 0, y: 0.85 }, // bottom-left
  ];
  // Radius range (base, jitter) as a fraction of canvas width, keyed to count.
  // The range is kept narrow so one blob can't overwhelm the others in a card.
  const BLOB_RADIUS = {
    2: [0.27, 0.06],
    3: [0.23, 0.05],
  };
  // Fill-opacity stops, drawn without replacement so positions don't repeat in a
  // card. The three 1 slots bias the draw towards fully opaque: a thumbnail
  // never has two blobs at the same partial opacity, but may have several opaque.
  const BLOB_OPACITIES = [0.6, 0.7, 0.8, 1, 1, 1];
  // Palette intensity carries grade-level appropriateness: younger content reads
  // brightest and it eases off towards higher ed. The glyph sits a couple of
  // steps deeper than the blobs. A node's grade levels aggregate from its
  // descendants, so the median stage chooses the tier; content with no grade
  // data lands in the middle.
  const GRADE_STAGE = {
    [GradeLevels.PRESCHOOL]: 0,
    [GradeLevels.BASIC_SKILLS]: 1,
    [GradeLevels.LOWER_PRIMARY]: 1,
    [GradeLevels.UPPER_PRIMARY]: 2,
    [GradeLevels.LOWER_SECONDARY]: 3,
    [GradeLevels.UPPER_SECONDARY]: 4,
    [GradeLevels.TERTIARY]: 5,
    [GradeLevels.PROFESSIONAL]: 6,
    [GradeLevels.WORK_SKILLS]: 6,
  };
  const INTENSITY_TIERS = [
    { maxStage: 2, glyph: 'v_600', blob: 'v_400' }, // primary and below
    { maxStage: 4, glyph: 'v_500', blob: 'v_300' }, // secondary / mixed
    { maxStage: Infinity, glyph: 'v_400', blob: 'v_200' }, // tertiary and up
  ];
  const DEFAULT_STAGE = 3;

  // Yellow's ramp stops at a pale gold (v_600), too light to read as a glyph on
  // the tint, so yellow glyphs borrow the adjacent - warm and harmonious -
  // orange ramp, which carries genuinely deep shades.
  const GLYPH_HUE_SUBSTITUTE = { yellow: 'orange' };

  // Glyphs are arranged as a constellation: the vertices of a regular polygon.
  // The count reads at a glance and siblings with the same metadata arrange
  // alike. One mark is a point, two a line, then triangle, square, pentagon and
  // on up. Every mark sits on a centred ring equidistant from the middle, so the
  // group stays balanced and never flings a corner off the canvas. Points are
  // unit vectors (radius 1), scaled per count by SUBJECT_LAYOUT. The polygon is
  // oriented to sit on a flat base (apex up for odd counts).
  function polygonPoints(n) {
    if (n === 1) {
      return [[0, 0]];
    }
    const points = [];
    for (let i = 0; i < n; i++) {
      const theta = -Math.PI / 2 + Math.PI / n + (i * 2 * Math.PI) / n;
      // Screen space is y-down, so negate sin to put the apex at the top.
      points.push([Math.cos(theta), -Math.sin(theta)]);
    }
    // Recentre on the bounding box: a polygon's circumcentre isn't its visual
    // centre when top and bottom extents differ (most visibly the triangle,
    // whose apex reaches a full radius up but whose base only half a radius
    // down), which would otherwise ride high and crowd the top edge.
    const ys = points.map(p => p[1]);
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    return points.map(([x, y]) => [x, y - cy]);
  }

  // The constellation shows at most this many glyphs (distinct category icons).
  const MAX_SUBJECTS = 12;

  const POINT_LAYOUTS = Object.fromEntries(
    Array.from({ length: MAX_SUBJECTS }, (_, i) => [i + 1, polygonPoints(i + 1)]),
  );

  // The constellation occupies the same fixed area whatever the count: the ring
  // radius is constant, and only the glyphs shrink as the ring gets busier, so
  // adjacent marks stay clear without the group ever growing into the edges.
  // A lone glyph is special - no ring, filling the centre.
  const SUBJECT_RADIUS = 15;
  const SUBJECT_SIZE = {
    1: 34,
    2: 22,
    3: 18,
    4: 17,
    5: 15,
    6: 14,
    7: 12,
    8: 10,
    9: 10,
    10: 9,
    11: 8,
    12: 7,
  };

  function seededShuffle(array, prng) {
    const result = [...array];
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(prng() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
  }

  export default {
    name: 'ComposedThumbnail',
    setup(props) {
      // Two independent seeds. The shape (blob layout) is seeded from content_id,
      // so copies of the same resource keep one recognisable form wherever they
      // appear. The hue is seeded from the node id, so each placement is recoloured
      // - the same resource reads as "the same thing, tweaked" across channels.
      const shapeSeed = computed(() => hashString(props.contentNode.content_id || ''));
      const hueSeed = computed(() => hashString(props.contentNode.id || ''));

      // Composition canvas: width fixed at 100, height from the aspect ratio.
      const canvas = computed(() => ({ w: 100, h: 100 / props.aspectRatio }));

      const category = computed(() => resolveCategory(props.contentNode));

      // Hue follows the node id, not its category family: category metadata
      // aggregates from imported descendants, so a family-derived hue would shift
      // as the imported content set changes.
      const hue = computed(() => seededHue(hueSeed.value));

      const palette = computed(() => themePalette()[hue.value]);

      // Grade-level intensity tier, chosen by the median schooling stage.
      const intensity = computed(() => {
        const stages = withIncludedFallback(props.contentNode, 'grade_levels')
          .map(level => GRADE_STAGE[level])
          .filter(stage => stage !== undefined)
          .sort((a, b) => a - b);
        let median = DEFAULT_STAGE;
        if (stages.length) {
          const mid = Math.floor(stages.length / 2);
          median = stages.length % 2 ? stages[mid] : (stages[mid - 1] + stages[mid]) / 2;
        }
        return INTENSITY_TIERS.find(tier => median <= tier.maxStage);
      });

      // The lightest tint, so the blobs - down to v_200 at higher ed - stay legible.
      const bgColor = computed(() => palette.value.v_50);

      const blobs = computed(() => {
        const { w, h } = canvas.value;
        // Layout (count, corners, radii, organic form, opacity) is seeded from the
        // shape seed, so it is identical across copies of a resource.
        const shapePrng = makePrng(shapeSeed.value ^ 0x9e3779b9);
        const count = 2 + (shapeSeed.value % 2);
        // Two blobs sit on opposite corners for balance; three take a seeded
        // selection of the four corners.
        const corners =
          count === 2
            ? shapeSeed.value & 0x20
              ? [BLOB_ANCHORS[0], BLOB_ANCHORS[2]]
              : [BLOB_ANCHORS[1], BLOB_ANCHORS[3]]
            : seededShuffle(BLOB_ANCHORS, shapePrng).slice(0, count);
        // Distinct opacity per blob, in shape-seeded order.
        const opacities = seededShuffle(BLOB_OPACITIES, shapePrng).slice(0, count);
        // Colour is seeded from the hue seed, so copies recolour: a distinct hue
        // per blob from the full palette, excluding the identity hue so the blobs
        // always read as accents against the tint.
        const huePrng = makePrng(hueSeed.value ^ 0x85ebca6b);
        const hues = seededShuffle(
          HUE_WHEEL.filter(wheelHue => wheelHue !== hue.value),
          huePrng,
        ).slice(0, count);
        const [base, jitter] = BLOB_RADIUS[count];
        const p = themePalette();
        const result = [];
        for (let i = 0; i < count; i++) {
          const r = (base + shapePrng() * jitter) * w;
          result.push({
            ...makeBlob(corners[i].x * w, corners[i].y * h, r, shapePrng),
            color: p[hues[i]][intensity.value.blob],
            opacity: opacities[i],
          });
        }
        return result;
      });

      // Lay out `icons` as a constellation centred on `center` (canvas units):
      // the vertices of a regular polygon on a ring of the given `radius`, each
      // glyph drawn at `size`.
      function constellation(center, icons, radius, size) {
        const offsets = POINT_LAYOUTS[icons.length];
        return icons.map((icon, i) => ({
          icon,
          size,
          point: { x: center.x + offsets[i][0] * radius, y: center.y + offsets[i][1] * radius },
        }));
      }

      // The charge: the node's distinct category glyphs as a centred
      // constellation - or its kind (leaf) / a folder (topic) when the node
      // carries no categories. The central area is kept clear of blobs, so every
      // glyph takes the one tier shade for a unified group.
      const iconElements = computed(() => {
        const { w, h } = canvas.value;
        const glyphHue = GLYPH_HUE_SUBSTITUTE[hue.value] || hue.value;
        const glyphColor = themePalette()[glyphHue][intensity.value.glyph];
        const glyphs = category.value.icons.length
          ? category.value.icons.slice(0, MAX_SUBJECTS)
          : [props.contentNode.is_leaf ? props.contentNode.kind : 'topic'];
        return constellation(
          { x: 0.5 * w, y: 0.5 * h },
          glyphs,
          SUBJECT_RADIUS,
          SUBJECT_SIZE[glyphs.length],
        ).map(({ icon, point, size }) => ({
          test: 'subject-icon',
          icon,
          color: glyphColor,
          style: {
            left: `${(point.x / w) * 100}%`,
            top: `${(point.y / h) * 100}%`,
            width: `${size}%`,
            height: 'auto',
            transform: 'translate(-50%, -50%)',
          },
        }));
      });

      return {
        canvas,
        bgColor,
        blobs,
        iconElements,
      };
    },
    props: {
      contentNode: {
        type: Object,
        required: true,
      },
      // Aspect ratio of the container the composition will fill (width / height).
      aspectRatio: {
        type: Number,
        default: DEFAULT_THUMBNAIL_ASPECT_RATIO,
      },
    },
  };

</script>


<style lang="scss" scoped>

  .composed-thumbnail {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  .blob-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
  }

  .placed-icon {
    position: absolute;
  }

</style>
