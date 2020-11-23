import JSZip from 'jszip';
import flatMap from 'lodash/flatMap';
import Toposort from 'toposort-class';
import { v4 as uuidv4 } from 'uuid';
import loadBinary from './loadBinary';
import H5PConstructor from './h5pDist';

let originalGetPath;

function escapeRegExp(string) {
  return string.replace(/[.*+\-?^${}()|[\]\\]/g, '\\$&'); // $& means the whole matched string
}

export default class H5P {
  constructor(iframe, filepath, contentNamespace) {
    this.iframe = iframe;
    this.iframe.src = '/h5p/';
    this.filepath = filepath;
    this.contentNamespace = contentNamespace;
    this.dependencies = [];
    this.jsDependencies = {};
    this.cssDependencies = {};
    this.packageFiles = {};
    this.contentPaths = {};
    this.contentJson = '';
    this.library = null;

    loadBinary(this.filepath)
      .then(JSZip.loadAsync)
      .then(zip => {
        this.zip = zip;
        return this.recurseDependencies('h5p.json');
      })
      .then(() => this.setDependencies())
      .then(() => this.processFiles())
      .then(() => this.processJsDependencies())
      .then(() => this.processCssDependencies())
      .then(() => {
        console.log(this);
        if (this.iframe.contentDocument && this.iframe.contentDocument.readyState === 'complete') {
          return this.initH5P();
        }
        this.iframe.addEventListener('load', () => this.initH5P());
      });
  }

  initH5P() {
    this.shimH5P();
    this.cssDependencies.map(css => this.scriptLoader(css, true));
    return this.jsDependencies
      .reduce((p, url) => {
        return p.then(() => {
          return this.scriptLoader(url);
        });
      }, Promise.resolve())
      .then(() => {
        const container = this.iframe.contentWindow.document.createElement('div');
        container.classList.add('h5p-content');
        container.setAttribute('data-content-id', this.contentNamespace);
        this.iframe.contentWindow.document.body.append(container);
        this.iframe.contentWindow.H5P.init(this.iframe.contentWindow.document.body);
      });
  }

  shimH5P() {
    const self = this;

    const IntegrationShim = {
      get contents() {
        return {
          [`cid-${self.contentNamespace}`]: {
            library: self.library,
            jsonContent: self.contentJson,
            displayOptions: {
              copyright: false,
              download: false,
              embed: false,
              export: false,
              frame: false,
              icon: false,
            },
          },
        };
      },
      get l10n() {
        return {
          H5P: {},
        };
      },
    };
    this.iframe.contentWindow.H5PIntegration = IntegrationShim;
    const baseH5P = H5PConstructor(
      IntegrationShim,
      this.iframe.contentWindow,
      this.iframe.contentDocument
    );
    const Shim = {
      ...baseH5P,
      createUUID() {
        return uuidv4();
      },
      isFramed: false,
      getPath(path, contentId) {
        if (self.contentPaths[path]) {
          return self.contentPaths[path];
        }
        return baseH5P.getPath(path, contentId);
      },
    };
    this.iframe.contentWindow.H5P = Shim;
  }

  /**
   * Loads a Javascript file and executes it.
   * @param  {String} url URL for the script
   * @return {Promise}     Promise that resolves when the script has loaded
   */
  scriptLoader(url, css = false) {
    const iframeDocument = this.iframe.contentWindow.document;
    return new Promise((resolve, reject) => {
      let script;
      if (!css) {
        script = iframeDocument.createElement('script');
        script.type = 'text/javascript';
        script.src = url;
        script.async = true;
        script.addEventListener('load', () => resolve(script));
        script.addEventListener('error', reject);
      } else {
        script = iframeDocument.createElement('link');
        script.rel = 'stylesheet';
        script.type = 'text/css';
        script.href = url;
        // Can't detect loading for css, so just assume it worked.
        resolve(script);
      }
      iframeDocument.body.appendChild(script);
    });
  }

  getPath(path) {
    if (this.contentPaths[path]) {
      return this.contentPaths[path];
    }
    return originalGetPath(path);
  }

  setDependencies() {
    const dependencySorter = new Toposort();

    for (let i = 0; i < this.dependencies.length; i++) {
      const dependency = this.dependencies[i];
      this.packageFiles[dependency.packagePath] = {};
      dependencySorter.add(dependency.packagePath, dependency.dependencies);

      this.cssDependencies[dependency.packagePath] = dependency.preloadedCss;

      this.jsDependencies[dependency.packagePath] = dependency.preloadedJs;
    }

    this.sortedDependencies = dependencySorter.sort().reverse();
  }

  recurseDependencies(jsonFile, visitedPaths = {}, packagePath = '') {
    return this.zip
      .file(jsonFile)
      .async('string')
      .then(content => {
        const json = JSON.parse(content);
        const dependencies = json['preloadedDependencies'] || [];
        // Make a copy so that we are not modifying the same object
        visitedPaths = {
          ...visitedPaths,
        };
        const library = json.mainLibrary;
        return Promise.all(
          dependencies.map(dep => {
            const packagePath = `${dep.machineName}-${dep.majorVersion}.${dep.minorVersion}/`;
            if (!this.library && dep.machineName === library) {
              this.library = `${dep.machineName} ${dep.majorVersion}.${dep.minorVersion}`;
            }
            if (visitedPaths[packagePath]) {
              // If we have visited this dependency before
              // then we are in a cyclic dependency graph
              // so stop!
              return Promise.resolve(packagePath);
            }
            visitedPaths[packagePath] = true;
            return this.recurseDependencies(
              packagePath + 'library.json',
              visitedPaths,
              packagePath
            ).then(() => packagePath);
          })
        ).then(dependencies => {
          if (packagePath) {
            const preloadedJs = (json['preloadedJs'] || []).map(js => js.path);
            const preloadedCss = (json['preloadedCss'] || []).map(css => css.path);
            this.dependencies.push({
              packagePath,
              dependencies,
              preloadedCss,
              preloadedJs,
            });
          }
        });
      });
  }

  processJsDependencies() {
    this.jsDependencies = flatMap(this.sortedDependencies, dependency => {
      return this.jsDependencies[dependency].map(jsDep => {
        const pathPrefix =
          jsDep
            .split('/')
            .slice(0, -1)
            .join('/') + '/';
        const js = Object.entries(this.packageFiles[dependency]).reduce(
          (script, [key, value]) =>
            script.replace(
              new RegExp(`(['"]{1})${escapeRegExp(key.replace(pathPrefix, ''))}\\1`, 'g'),
              `$1${value}$1`
            ),
          this.packageFiles[dependency][jsDep]
        );
        return URL.createObjectURL(new Blob([js], { type: 'text/javascript' }));
      });
    });
  }

  processCssDependencies() {
    this.cssDependencies = flatMap(this.sortedDependencies, dependency => {
      return this.cssDependencies[dependency].map(cssDep => {
        const pathPrefix =
          cssDep
            .split('/')
            .slice(0, -1)
            .join('/') + '/';
        const css = Object.entries(this.packageFiles[dependency]).reduce(
          (script, [key, value]) =>
            script.replace(
              new RegExp(
                `(url\\(['"]?)(${escapeRegExp(
                  key.replace(pathPrefix, '')
                )})(\\?[^'^"]+)?(['"]?\\))`,
                'g'
              ),
              `$1${value}$4`
            ),
          this.packageFiles[dependency][cssDep]
        );
        return URL.createObjectURL(new Blob([css], { type: 'text/css' }));
      });
    });
  }

  processContent(file) {
    const fileName = file.name.replace('content/', '');
    if (fileName === 'content.json') {
      return file.async('string').then(content => {
        this.contentJson = content;
      });
    }
    // Create blob urls for every item in the content folder
    return file.async('blob').then(blob => {
      this.contentPaths[fileName] = URL.createObjectURL(blob);
    });
  }

  processPackageFile(file, packagePath) {
    const fileName = file.name.replace(packagePath, '');
    if (
      this.jsDependencies[packagePath].indexOf(fileName) > -1 ||
      this.cssDependencies[packagePath].indexOf(fileName) > -1
    ) {
      return file.async('string').then(content => {
        this.packageFiles[packagePath][fileName] = content;
      });
    }
    return file.async('blob').then(blob => {
      this.packageFiles[packagePath][fileName] = URL.createObjectURL(blob);
    });
  }

  processFiles() {
    const contentFiles = this.zip.file(/content\//);
    return Promise.all(
      contentFiles.map(file => this.processContent(file)),
      ...flatMap(Object.keys(this.packageFiles), packagePath => {
        const packageFiles = this.zip.file(new RegExp(escapeRegExp(packagePath)));
        return packageFiles.map(file => this.processPackageFile(file, packagePath));
      })
    );
  }
}
