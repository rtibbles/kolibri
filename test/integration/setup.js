import { setUp, tearDown } from './testServerClient';

require('expect-puppeteer');

beforeEach(() => {
  return setUp();
});

afterEach(() => {
  return tearDown();
});
