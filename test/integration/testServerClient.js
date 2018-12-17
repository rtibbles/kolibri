const { spawn } = require('child_process');
const path = require('path');
const rest = require('rest');

function sendMessage(message) {
  return rest(`http://127.0.0.1:4242/${message}`);
}

async function start() {
  const subprocess = spawn('python', [path.resolve(__dirname, './run_test_server.py')], {
    env: Object.assign({}, process.env, {
      DJANGO_SETTINGS_MODULE: 'kolibri.deployment.default.settings.test',
    }),
  });

  return new Promise(resolve => {
    subprocess.stderr.on('data', data => {
      data = data.toString();
      if (data === 'ready') {
        resolve(subprocess);
      }
    });
    subprocess.on('close', code => {
      if (code === 0) {
        console.log('Test server shutdown cleanly');
      } else {
        console.log(`Test server exited with code ${code}`);
      }
    });
  });
}

async function setUp() {
  return sendMessage('setUp');
}

async function tearDown() {
  return sendMessage('tearDown');
}

async function stop() {
  return sendMessage('stop');
}

module.exports = {
  start,
  setUp,
  tearDown,
  stop,
};
