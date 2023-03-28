var pathToRegexp = require('path-to-regexp');

export function generateNavRoute(rootUrl, pathReference, params = {}) {
  let compiledRoute;

  // when there is a direct path
  compiledRoute = `${rootUrl}#${pathReference}`;

  // Are there params being passes
  if (Object.keys(params).length > 0) {
    const makeParamsRoute = pathToRegexp.compile(compiledRoute);
    compiledRoute = makeParamsRoute(params);
  }

  // if the path requires params but none exist, send to root
  const pathParams = [];
  pathToRegexp(compiledRoute, pathParams);

  if (pathParams.length > 0 && Object.keys(params).length < 1) {
    compiledRoute = rootUrl;
  }

  return compiledRoute;
}
