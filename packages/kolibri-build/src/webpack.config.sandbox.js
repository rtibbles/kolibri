/**
 * Webpack configuration for sandbox handler bundles.
 *
 * Sandbox handlers run inside the sandboxed iframe and cannot access
 * Kolibri core. They are built as self-contained IIFE bundles with
 * no externals.
 *
 * This configuration reuses the base webpack config and only overrides
 * what's necessary for sandbox handlers.
 */

const path = require('node:path');
const webpack = require('webpack');
const { merge } = require('webpack-merge');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const logging = require('kolibri-logging');
const BundleTracker = require('./webpackBundleTracker');
const baseConfig = require('./webpack.config.base');
const WebpackMessages = require('./webpackMessages');

/**
 * Generate webpack config for a sandbox handler bundle.
 *
 * @param {Object} data - Bundle data from webpack_json
 * @param {Object} options - Build options
 * @returns {Object} Webpack configuration
 */
module.exports = (
  data,
  {
    mode = 'development',
    hot = false,
    port = 3000,
    address = 'localhost',
    cache = false,
    transpile = false,
    devServer = false,
    setDevServerPublicPath = true,
  } = {},
) => {
  if (
    typeof data.name === 'undefined' ||
    typeof data.bundle_id === 'undefined' ||
    typeof data.config_path === 'undefined' ||
    typeof data.static_dir === 'undefined' ||
    typeof data.stats_file === 'undefined' ||
    typeof data.plugin_path === 'undefined' ||
    typeof data.version === 'undefined'
  ) {
    logging.error(data.name + ' sandbox handler is misconfigured, missing parameter(s)');
    return;
  }

  const configData = require(data.config_path);
  let webpackConfig;
  if (data.index !== null) {
    webpackConfig = configData[data.index].webpack_config;
  } else {
    webpackConfig = configData.webpack_config;
  }

  // Resolve entry path
  let entry = webpackConfig.entry;
  if (typeof entry === 'string') {
    if (entry.startsWith('./') || entry.startsWith('../')) {
      entry = path.join(data.plugin_path, entry);
    }
    entry = { [data.name]: entry };
  } else {
    // Handle object entries
    const resolvedEntry = {};
    Object.keys(entry).forEach(key => {
      let entryPath = entry[key];
      if (entryPath.startsWith('./') || entryPath.startsWith('../')) {
        entryPath = path.join(data.plugin_path, entryPath);
      }
      const entryKey = key === data.bundle_id ? data.name : key;
      resolvedEntry[entryKey] = entryPath;
    });
    entry = resolvedEntry;
  }

  // Get kolibri-sandbox source path for aliasing
  const kolibriSandboxPath = path.resolve(__dirname, '../../kolibri-sandbox/src');

  // Start with base config
  const base = baseConfig({ mode, hot: false, cache, transpile });

  let bundle = {
    // CRITICAL: No externals - sandbox handlers are self-contained
    externals: {},

    name: data.name,
    mode,

    entry,

    output: {
      path: path.resolve(path.join(data.static_dir, data.name)),
      filename: '[name]-' + data.version + '.js',
      // IIFE format for script tag injection in sandbox
      iife: true,
      pathinfo: false,
      publicPath: 'auto',
    },

    resolve: {
      extensions: ['.js', '.vue', '.scss'],
      alias: {
        // Allow importing from kolibri-sandbox
        'kolibri-sandbox': kolibriSandboxPath,
      },
      modules: [
        path.join(data.plugin_path, 'node_modules'),
        path.join(process.cwd(), 'node_modules'),
      ],
    },

    resolveLoader: {
      modules: [
        path.join(data.plugin_path, 'node_modules'),
        path.join(process.cwd(), 'node_modules'),
      ],
    },

    plugins: [
      new MiniCssExtractPlugin({
        filename: '[name]' + data.version + '.css',
      }),
      // BundleTracker creates stats about our built files
      new BundleTracker({
        filename: data.stats_file,
      }),
      // Define module name and version
      new webpack.DefinePlugin({
        __kolibriModuleName: JSON.stringify(data.name),
        __version: JSON.stringify(data.version),
      }),
      // Add custom messages per bundle
      new WebpackMessages({
        name: data.name + ' (sandbox)',
        logger: str => logging.info(str),
      }),
    ],
  };

  // Merge with base config
  bundle = merge(base, bundle);

  // Dev server settings
  if (devServer) {
    if (setDevServerPublicPath) {
      const publicPath = `http://${address}:${port}/${data.name}/`;
      bundle.output.publicPath = publicPath;
    }
    bundle.watch = true;
    bundle.watchOptions = {
      aggregateTimeout: 300,
    };
  }

  // Cache settings
  if (cache) {
    bundle.cache = {
      ...bundle.cache,
      buildDependencies: {
        config: [__filename, data.config_path],
      },
    };
  }

  return bundle;
};
