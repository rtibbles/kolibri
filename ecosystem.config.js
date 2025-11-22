module.exports = {
  apps: [
    {
      name: 'watch',
      script: 'yarn',
      args: 'watch --watchonly',
      autorestart: false,
      watch: false,
      kill_timeout: 5000,
    },
    {
      name: 'kolibri',
      script: 'kolibri',
      args: 'start --debug --foreground --port=8000 --settings=kolibri.deployment.default.settings.dev',
      autorestart: false,
      watch: false,
      kill_timeout: 5000,
    },
    {
      name: 'sandbox',
      script: 'yarn',
      args: 'sandbox-dev',
      autorestart: false,
      watch: false,
      kill_timeout: 5000,
    },
  ],
};
