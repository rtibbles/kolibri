const path = require('path');

module.exports = {
  exitOnPageError: false,
  server: {
    command: 'python ' + path.resolve(__dirname, './run_test_server.py'),
    launchTimeout: 30000,
    port: 8000,
  },
};
