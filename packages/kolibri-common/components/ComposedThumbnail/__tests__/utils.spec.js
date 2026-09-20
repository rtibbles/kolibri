import Categories from 'kolibri-constants/labels/Subjects';
import { hashString, makePrng, HUE_WHEEL, seededHue, resolveCategory, makeBlob } from '../utils';

// describe, it, expect are Jest globals — do NOT import them

describe('hashString', () => {
  it('is deterministic', () => {
    expect(hashString('abc123')).toEqual(hashString('abc123'));
  });
  it('differs for different inputs', () => {
    expect(hashString('abc123')).not.toEqual(hashString('abc124'));
  });
  it('returns an unsigned 32-bit integer', () => {
    const h = hashString('e2c9c64aefea48c89cf1e6c8c4b3e7a1');
    expect(h).toBeGreaterThanOrEqual(0);
    expect(h).toBeLessThanOrEqual(0xffffffff);
    expect(Number.isInteger(h)).toBe(true);
  });
});

describe('makePrng', () => {
  it('produces a deterministic sequence in [0, 1)', () => {
    const a = makePrng(12345);
    const b = makePrng(12345);
    for (let i = 0; i < 20; i++) {
      const value = a();
      expect(value).toEqual(b());
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });
  it('different seeds produce different sequences', () => {
    expect(makePrng(1)()).not.toEqual(makePrng(2)());
  });
});

describe('colour wheel', () => {
  it('has the 8 usable KDS hues in wheel order', () => {
    expect(HUE_WHEEL).toEqual([
      'red',
      'orange',
      'yellow',
      'green',
      'darkgreen',
      'lightblue',
      'blue',
      'pink',
    ]);
  });
});

describe('seededHue', () => {
  it('returns a wheel hue deterministically', () => {
    const hue = seededHue(12345);
    expect(HUE_WHEEL).toContain(hue);
    expect(seededHue(12345)).toEqual(hue);
  });
});

describe('resolveCategory', () => {
  it('returns family of the primary category and per-category icons', () => {
    const { family, icons } = resolveCategory({ categories: [Categories.ALGEBRA] });
    expect(family).toEqual('MATHEMATICS');
    expect(icons).toEqual(['mathematicsResource']);
  });
  it('walks up the taxonomy when no icon exists for the specific category', () => {
    // ARITHMETIC has no arithmeticResource icon; walks up to MATHEMATICS
    const { icons } = resolveCategory({ categories: [Categories.ARITHMETIC] });
    expect(icons).toEqual(['mathematicsResource']);
  });
  it('deduplicates icons across categories resolving to the same icon', () => {
    const { icons } = resolveCategory({
      categories: [Categories.BIOLOGY, Categories.CHEMISTRY],
    });
    expect(icons).toEqual(['sciencesResource']);
  });
  it('keeps distinct icons for distinct categories', () => {
    const { icons } = resolveCategory({
      categories: [Categories.BIOLOGY, Categories.HISTORY],
    });
    expect(icons).toEqual(['sciencesResource', 'historyResource']);
  });
  it('applies the WORK and FOUNDATIONS icon exceptions', () => {
    expect(resolveCategory({ categories: [Categories.WORK] }).icons).toEqual(['skillsResource']);
    expect(resolveCategory({ categories: [Categories.FOUNDATIONS] }).icons).toEqual([
      'basicSkillsResource',
    ]);
  });
  it('returns empty result for no categories', () => {
    expect(resolveCategory({ categories: [] })).toEqual({ family: null, icons: [] });
    expect(resolveCategory({})).toEqual({ family: null, icons: [] });
  });
  it('falls back to derived included_categories when no authored categories', () => {
    const { family, icons } = resolveCategory({
      categories: [],
      included_categories: [Categories.ALGEBRA],
    });
    expect(family).toEqual('MATHEMATICS');
    expect(icons).toEqual(['mathematicsResource']);
  });
  it('authored categories win over included_categories', () => {
    const { icons } = resolveCategory({
      categories: [Categories.HISTORY],
      included_categories: [Categories.ALGEBRA],
    });
    expect(icons).toEqual(['historyResource']);
  });
});

describe('makeBlob', () => {
  it('is deterministic for the same prng seed', () => {
    expect(makeBlob(50, 20, 15, makePrng(7))).toEqual(makeBlob(50, 20, 15, makePrng(7)));
  });
  it('returns a closed SVG path of quadratic Béziers', () => {
    const { d } = makeBlob(50, 20, 15, makePrng(7));
    expect(d).toMatch(/^M [\d.-]+ [\d.-]+( Q [\d.-]+ [\d.-]+ [\d.-]+ [\d.-]+)+ Z$/);
  });
  it('differs for different seeds', () => {
    expect(makeBlob(50, 20, 15, makePrng(1)).d).not.toEqual(makeBlob(50, 20, 15, makePrng(2)).d);
  });
});
