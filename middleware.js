// Optional password gate (Vercel Edge Middleware).
//
// DORMANT until you set a SITE_PASSWORD env var in Vercel
// (Project → Settings → Environment Variables). With no password set the site
// stays open, so it's safe to deploy as-is and flip protection on later with
// zero code changes.
//
// When active it gates ONLY the private /full coverage view — any username, the
// password you set. The public demo at / stays open. Sent over HTTPS only.

export const config = {
  // Gate only the private full-coverage view; the public demo at / stays open.
  matcher: ['/full', '/full/:path*'],
};

export default function middleware(request) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return; // no password configured → site is open

  const header = request.headers.get('authorization') || '';
  const [scheme, encoded] = header.split(' ');
  if (scheme === 'Basic' && encoded) {
    const decoded = atob(encoded);
    const given = decoded.slice(decoded.indexOf(':') + 1);
    if (given === password) return; // authorized → continue
  }

  return new Response('Authentication required.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Atlas Coverage", charset="UTF-8"' },
  });
}
