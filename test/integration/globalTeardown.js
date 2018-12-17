const { teardown: teardownPuppeteer } = require('jest-environment-puppeteer');
const { stop } = require('./testServerClient');

async function tearDown() {
  await teardownPuppeteer();
  return stop();
}

module.exports = tearDown;
