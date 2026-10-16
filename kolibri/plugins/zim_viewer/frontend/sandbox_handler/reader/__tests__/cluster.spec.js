import { sliceBlob } from '../cluster';
import { CorruptZimError } from '../errors';

function cluster(offsets, body = []) {
  const bytes = new Uint8Array(offsets.length * 4 + body.length);
  const view = new DataView(bytes.buffer);
  offsets.forEach((offset, i) => view.setUint32(i * 4, offset, true));
  bytes.set(body, offsets.length * 4);
  return { decompressed: bytes, extended: false };
}

describe('sliceBlob', () => {
  it('slices a blob out by its offsets', () => {
    const blob = sliceBlob(cluster([8, 11], [1, 2, 3]), 0);
    expect([...blob]).toEqual([1, 2, 3]);
  });

  it('rejects a blob past the end of the offset table', () => {
    expect(() => sliceBlob(cluster([8, 11], [1, 2, 3]), 1)).toThrow(CorruptZimError);
  });

  it('rejects offsets that run backwards', () => {
    expect(() => sliceBlob(cluster([11, 8], [1, 2, 3]), 0)).toThrow(CorruptZimError);
  });

  it('rejects offsets past the end of the cluster', () => {
    expect(() => sliceBlob(cluster([8, 99], [1, 2, 3]), 0)).toThrow(CorruptZimError);
  });
});
