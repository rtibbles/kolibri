const { setUp, tearDown } = require('./testServerClient');

require('expect-puppeteer');

beforeEach(() => {
  return setUp();
});

afterEach(() => {
  return tearDown();
});
