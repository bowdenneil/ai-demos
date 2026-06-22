export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Max-Age': '86400',
        }
      });
    }

    // Only allow POST to /chat/completions and GET to /models
    const url = new URL(request.url);
    const targetUrl = 'https://api.tensorix.ai/v1' + url.pathname;

    // Forward the request to Tensorix
    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.set('Origin', 'https://api.tensorix.ai');

    const init = {
      method: request.method,
      headers: headers,
    };

    if (request.method === 'POST') {
      init.body = await request.text();
    }

    const response = await fetch(targetUrl, init);

    // Clone response and add CORS headers
    const newHeaders = new Headers(response.headers);
    newHeaders.set('Access-Control-Allow-Origin', '*');
    newHeaders.set('Access-Control-Expose-Headers', 'content-type');

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: newHeaders,
    });
  }
};
