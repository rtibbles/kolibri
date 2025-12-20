import flatten from 'lodash/flatten';

// Feature detection for lookbehind support
let supportsLookbehind;
try {
  new RegExp('(?<!a)b');
  supportsLookbehind = true;
} catch (e) {
  supportsLookbehind = false;
}

export function getAbsoluteFilePath(baseFilePath, relativeFilePath) {
  // Construct a URL with a dummy base so that we can concatenate the
  // dependency URL with the URL relative to the dependency
  // and then read the pathname to get the new path.
  // Take substring to remove the leading slash to match the reference file paths
  // in packageFiles.
  try {
    return decodeURIComponent(
      new URL(relativeFilePath, new URL(baseFilePath, 'http://b.b/')).pathname.substring(1),
    );
  } catch (e) {
    console.debug('Error during URL handling', e); // eslint-disable-line no-console
  }
  return null;
}

export class Mapper {
  constructor(file) {
    this.file = file;
  }

  getPaths() {
    throw new Error('Not implemented');
  }

  replacePaths() {
    throw new Error('Not implemented');
  }
}

// Looks for any URLs referenced inside url()
// Modern version with lookbehind (Safari 16.4+, Chrome 62+, Firefox 78+)
const cssPathRegexModern = /url\((['"]?)(.*?)(?<!\\)(\1)\)/g;

// Legacy version without lookbehind for older browsers
// Uses alternation: quoted URLs with proper escape handling OR unquoted URLs
// - Quoted: url('...') or url("...") where content can have escaped chars like \'
// - Unquoted: url(...) where content has no quotes or whitespace
const cssPathRegexLegacy = /url\((['"])((?:\\.|[^\\])*?)\1\)|url\(([^'"\s)]*)\)/g;

const unescapePathRegex = /\\(.)/g;

function unescapeCssString(str) {
  return str.replace(unescapePathRegex, '$1');
}

function getCSSPathsModern(fileContents) {
  return Array.from(fileContents.matchAll(cssPathRegexModern), ([, , p2]) =>
    p2
      ? // Split first before decoding, in case ? is encoded in the URL
        decodeURIComponent(unescapeCssString(p2.split('?')[0]))
      : '',
  );
}

function getCSSPathsLegacy(fileContents) {
  return Array.from(fileContents.matchAll(cssPathRegexLegacy)).map(
    ([, quote, quotedPath, unquotedPath]) => {
      // For quoted URLs, use quotedPath (group 2); for unquoted, use unquotedPath (group 3)
      const path = quote ? quotedPath : unquotedPath;
      return path
        ? // Split first before decoding, in case ? is encoded in the URL
          decodeURIComponent(unescapeCssString(path.split('?')[0]))
        : '';
    },
  );
}

function replaceCSSPathsModern(fileContents, packageFiles) {
  return fileContents.replace(cssPathRegexModern, function (match, start, path, end) {
    try {
      // Split off any query parameter
      path = unescapeCssString(path.split('?')[0]);
      // Look to see if there is a URL in our packageFiles mapping that
      // that has this as the source path.
      const newUrl = packageFiles[decodeURIComponent(path)];
      if (newUrl) {
        // If so, replace the instance with the new URL.
        return `url(${start}${newUrl}${end})`;
      }
    } catch (e) {
      console.debug('Error during URL handling', e); // eslint-disable-line no-console
    }
    // Otherwise just return the match so that it is unchanged.
    return match;
  });
}

function replaceCSSPathsLegacy(fileContents, packageFiles) {
  return fileContents.replace(
    cssPathRegexLegacy,
    function (match, quote, quotedPath, unquotedPath) {
      // For quoted URLs, use quotedPath (group 2); for unquoted, use unquotedPath (group 3)
      const path = quote ? quotedPath : unquotedPath;
      const quoteChar = quote || '';

      try {
        // Split off any query parameter
        const cleanPath = unescapeCssString(path.split('?')[0]);
        // Look to see if there is a URL in our packageFiles mapping that
        // that has this as the source path.
        const newUrl = packageFiles[decodeURIComponent(cleanPath)];
        if (newUrl) {
          // If so, replace the instance with the new URL.
          return `url(${quoteChar}${newUrl}${quoteChar})`;
        }
      } catch (e) {
        console.debug('Error during URL handling', e); // eslint-disable-line no-console
      }
      // Otherwise just return the match so that it is unchanged.
      return match;
    },
  );
}

// Conditional exports based on lookbehind support
export const getCSSPaths = supportsLookbehind ? getCSSPathsModern : getCSSPathsLegacy;
export const replaceCSSPaths = supportsLookbehind ? replaceCSSPathsModern : replaceCSSPathsLegacy;

class CSSMapper extends Mapper {
  getPaths() {
    return getCSSPaths(this.file.toString());
  }

  replacePaths(packageFiles) {
    return replaceCSSPaths(this.file.toString(), packageFiles);
  }
}

const domParser = new DOMParser();

const domSerializer = new XMLSerializer();

const urlAttributes = ['src', 'href'];

const queryParamRegex = /([^?)]+)?(\?.*)/g;

export function getDOMPaths(fileContents, mimeType) {
  const dom = domParser.parseFromString(fileContents.trim(), mimeType);
  // Get paths from URL attributes (src, href)
  const urlPaths = flatten(
    urlAttributes.map(attr => {
      const elementsWithUrl = Array.from(dom.querySelectorAll(`[${attr}]`));
      return elementsWithUrl.map(element =>
        decodeURIComponent(element.getAttribute(attr).replace(queryParamRegex, '$1')),
      );
    }),
  );

  // Get paths from style attributes
  const elementsWithStyle = Array.from(dom.querySelectorAll('[style]'));
  const stylePaths = flatten(
    elementsWithStyle.map(element => getCSSPaths(element.getAttribute('style'))),
  );

  // Get paths from srcset attributes
  const elementsWithSrcset = Array.from(dom.querySelectorAll('[srcset]'));
  const srcsetPaths = flatten(
    elementsWithSrcset.map(element => {
      const srcset = element.getAttribute('srcset');
      return srcset.split(/,(?![^(]*\))/g).map(entry => {
        const url = entry.trim().split(/\s+/)[0];
        return decodeURIComponent(url.replace(queryParamRegex, '$1'));
      });
    }),
  );

  // Get paths from style blocks
  const styleElements = Array.from(dom.getElementsByTagName('style'));
  const styleBlockPaths = flatten(styleElements.map(element => getCSSPaths(element.textContent)));

  return [...urlPaths, ...stylePaths, ...srcsetPaths, ...styleBlockPaths];
}

function replaceSrcsetUrls(srcset, packageFiles) {
  if (!srcset) {
    return srcset;
  }

  // Split on commas, but not inside parentheses
  // for future-proofing against more complex descriptors)
  const entries = srcset.split(/,(?![^(]*\))/g);

  return entries
    .map(entry => {
      const [url, ...descriptors] = entry.trim().split(/\s+/);
      // Remove any query parameters and decode the URL
      const baseUrl = decodeURIComponent(url.replace(queryParamRegex, '$1'));
      const newUrl = packageFiles[baseUrl];
      if (newUrl) {
        return [newUrl, ...descriptors].join(' ');
      }
      return entry.trim();
    })
    .join(', ');
}

export function replaceDOMPaths(fileContents, packageFiles, mimeType) {
  const dom = domParser.parseFromString(fileContents.trim(), mimeType);

  // Replace URL attributes
  for (const attr of urlAttributes) {
    const urlElements = Array.from(dom.querySelectorAll(`[${attr}]`));
    for (const element of urlElements) {
      const value = element.getAttribute(attr);
      const newUrl = packageFiles[decodeURIComponent(value.replace(queryParamRegex, '$1'))];
      if (newUrl) {
        element.setAttribute(attr, newUrl);
      }
    }
  }

  // Replace style attributes
  const elementsWithStyle = Array.from(dom.querySelectorAll('[style]'));
  for (const element of elementsWithStyle) {
    const styleValue = element.getAttribute('style');
    const newStyleValue = replaceCSSPaths(styleValue, packageFiles);
    element.setAttribute('style', newStyleValue);
  }

  // Replace srcset attributes
  const elementsWithSrcset = Array.from(dom.querySelectorAll('[srcset]'));
  for (const element of elementsWithSrcset) {
    const srcsetValue = element.getAttribute('srcset');
    const newSrcsetValue = replaceSrcsetUrls(srcsetValue, packageFiles);
    element.setAttribute('srcset', newSrcsetValue);
  }

  // Replace style blocks
  const styleElements = Array.from(dom.getElementsByTagName('style'));
  for (const style of styleElements) {
    const originalContent = style.textContent || '';
    const newContent = replaceCSSPaths(originalContent, packageFiles);
    style.textContent = newContent;
  }

  if (mimeType === 'text/html') {
    // Remove the namespace attribute from the root element
    // as serializeToString adds it by default and without this
    // it gets repeated.
    dom.documentElement.removeAttribute('xmlns');
  }
  return domSerializer.serializeToString(dom);
}

export class DOMMapper extends Mapper {
  getPaths() {
    return getDOMPaths(this.file.toString(), this.file.mimeType);
  }

  replacePaths(packageFiles) {
    return replaceDOMPaths(this.file.toString(), packageFiles, this.file.mimeType);
  }
}

export const defaultFilePathMappers = {
  css: CSSMapper,
  html: DOMMapper,
  htm: DOMMapper,
  xhtml: DOMMapper,
  xml: DOMMapper,
};

// Internal exports for testing both implementations
export const _internal = {
  getCSSPathsModern,
  getCSSPathsLegacy,
  replaceCSSPathsModern,
  replaceCSSPathsLegacy,
  supportsLookbehind,
};
