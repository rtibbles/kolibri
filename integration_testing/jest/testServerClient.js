const rest = require('rest');

function sendMessage(message) {
  return rest(`http://127.0.0.1:4242/${message}`);
}

async function setUp() {
  return sendMessage('setUp');
}

async function tearDown() {
  return sendMessage('tearDown');
}

module.exports = {
  setUp,
  tearDown,
};
