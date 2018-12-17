const path = require('path');

module.exports = {
  testMatch: ['**/?(*.)+(integration).js'],
  globalSetup: path.resolve(__dirname, './globalSetup'),
  globalTeardown: path.resolve(__dirname, './globalTeardown'),
  preset: 'jest-puppeteer',
  setupTestFrameworkScriptFile: path.resolve(__dirname, './setup'),
  setupFiles: [],
};
