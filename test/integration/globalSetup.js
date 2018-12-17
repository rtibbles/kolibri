const { setup: setupPuppeteer } = require('jest-environment-puppeteer');
const { start } = require('./testServerClient');

async function setup() {
  await setupPuppeteer();
  return start();
}

module.exports = setup;
