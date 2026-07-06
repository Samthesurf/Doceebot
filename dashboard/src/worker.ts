const INDEX_PATHS = new Set(['/dashboard', '/dashboard/', '/dashboard/login', '/logs', '/logs/']);

function asAssetRequest(request: Request, pathname: string): Request {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/dashboard') {
      url.pathname = '/dashboard/';
      return Response.redirect(url.toString(), 308);
    }

    if (INDEX_PATHS.has(url.pathname) || url.pathname.startsWith('/logs/')) {
      return env.ASSETS.fetch(asAssetRequest(request, '/'));
    }

    if (url.pathname.startsWith('/dashboard/')) {
      return env.ASSETS.fetch(
        asAssetRequest(request, url.pathname.replace(/^\/dashboard/, '') || '/'),
      );
    }

    return env.ASSETS.fetch(request);
  },
};
