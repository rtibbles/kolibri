/**
 * Pure utilities for composed placeholder thumbnails.
 * Everything here is deterministic: same inputs always produce the same outputs,
 * so the same content node renders identically on every device and surface.
 */
import camelCase from 'lodash/camelCase';
import { CategoriesLookup } from 'kolibri/constants';

// Deterministic 32-bit hash from a string (djb2).
export function hashString(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) >>> 0;
  }
  return hash;
}

// Deterministic PRNG (LCG) from an integer seed; returns floats in [0, 1).
export function makePrng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1103515245 + 12345) >>> 0;
    return s / 4294967296;
  };
}

// The 8 usable KDS hues. A node's hue is picked from this wheel by its seed.
export const HUE_WHEEL = [
  'red',
  'orange',
  'yellow',
  'green',
  'darkgreen',
  'lightblue',
  'blue',
  'pink',
];

// Hue for a node, picked deterministically from its seed.
export function seededHue(seed) {
  return HUE_WHEEL[seed % HUE_WHEEL.length];
}

// Category icons that exist in KDS (KIcon names).
const CATEGORY_ICONS = new Set([
  'schoolResource',
  'mathematicsResource',
  'sciencesResource',
  'readingAndWritingResource',
  'socialSciencesResource',
  'artsResource',
  'historyResource',
  'computerScienceResource',
  'dailyLifeResource',
  'currentEventsResource',
  'diversityResource',
  'entrepreneurshipResource',
  'environmentResource',
  'financialLiteracyResource',
  'mediaLiteracyResource',
  'mentalHealthResource',
  'publicHealthResource',
  'basicSkillsResource',
  'digitalLiteracyResource',
  'learningSkillsResource',
  'literacyResource',
  'logicCriticalThinkingResource',
  'numeracyResource',
  'skillsResource',
  'forTeachersResource',
  'guidesResource',
  'lessonPlansResource',
]);

function categoryIconName(name) {
  if (name === 'WORK') {
    return 'skillsResource';
  }
  if (name === 'FOUNDATIONS') {
    return 'basicSkillsResource';
  }
  return camelCase(name) + 'Resource';
}

// Walk one category id from most to least specific until a known KDS icon is found.
function resolveCategoryIcon(categoryId) {
  const segments = categoryId.split('.');
  for (let i = segments.length; i > 0; i--) {
    const name = CategoriesLookup[segments.slice(0, i).join('.')];
    if (name) {
      const candidate = categoryIconName(name);
      if (CATEGORY_ICONS.has(candidate)) {
        return candidate;
      }
    }
  }
  return null;
}

// A metadata field's effective values: authored values win; the backend-derived
// included_* aggregate (rolled up from descendants) is the fallback.
export function withIncludedFallback(node, field) {
  const authored = node[field];
  if (authored && authored.length) {
    return authored;
  }
  return node['included_' + field] || [];
}

/**
 * Resolve a node's categories to:
 * - the subject family name of the primary category (for palette keying)
 * - deduplicated KDS icons for each category (most specific available per category)
 * @param {object} contentNode - a content node, with categories and included_categories
 * @returns {{family: string|null, icons: string[]}} the palette family and its icons
 */
export function resolveCategory(contentNode) {
  // Prefer more specific categories: deeper taxonomy paths (more segments) sort
  // first, so they win the limited display slots over their broader ancestors.
  const categories = withIncludedFallback(contentNode, 'categories')
    .slice()
    .sort((a, b) => b.split('.').length - a.split('.').length);
  if (!categories.length) {
    return { family: null, icons: [] };
  }
  const segments = categories[0].split('.');
  // Family: two-segment prefix (SCHOOL.X) if it resolves, else top-level domain.
  const family =
    (segments.length > 1 && CategoriesLookup[segments.slice(0, 2).join('.')]) ||
    CategoriesLookup[segments[0]] ||
    null;
  const icons = [];
  for (const categoryId of categories) {
    const icon = resolveCategoryIcon(categoryId);
    if (icon && !icons.includes(icon)) {
      icons.push(icon);
    }
  }
  return { family, icons };
}

// Convex hull via Andrew's monotone chain. Pure and deterministic: the output is
// a function of the input points only. Replacing the jittered control points with
// their hull keeps the blob curve free of self-intersections.
function convexHull(points) {
  const sorted = points.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  if (sorted.length < 3) {
    return sorted;
  }
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }
  const upper = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }
  // Drop the last point of each chain (shared with the start of the other).
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

/**
 * Organic rounded blob: a smooth closed curve of quadratic Béziers through the
 * midpoints of the convex hull of 7 jittered radial control points (LE brand
 * style). Returns the SVG path string. Replacing the jittered points with their
 * hull keeps the curve convex and free of self-intersections.
 * @param {number} cx - centre x of the blob
 * @param {number} cy - centre y of the blob
 * @param {number} r - mean radius the control points vary around
 * @param {Function} prng - seeded generator returning floats in [0, 1)
 * @returns {{d: string}} the closed curve as an SVG path `d` attribute
 */
export function makeBlob(cx, cy, r, prng) {
  const points = [];
  for (let i = 0; i < 7; i++) {
    const angle = (i * 2 * Math.PI) / 7 + (prng() - 0.5) * 0.5;
    const radius = r * (0.82 + prng() * 0.3);
    points.push({ x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
  }
  const outer = convexHull(points);
  const n = outer.length;
  const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const inner = outer.map((p, i) => mid(p, outer[(i + 1) % n]));
  let d = `M ${inner[n - 1].x} ${inner[n - 1].y}`;
  for (let i = 0; i < n; i++) {
    d += ` Q ${outer[i].x} ${outer[i].y} ${inner[i].x} ${inner[i].y}`;
  }
  return { d: d + ' Z' };
}
