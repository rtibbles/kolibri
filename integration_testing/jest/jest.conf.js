const path = require('path');

module.exports = {
  testMatch: ['**/?(*.)+(int).js'],
  preset: 'jest-puppeteer',
  rootDir: path.resolve(__dirname, '../test'),
  setupFilesAfterEnv: [path.resolve(__dirname, './setup.int')],
};
