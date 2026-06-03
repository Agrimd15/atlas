// Password gate for the private /full coverage view (Vercel Edge Middleware).
//
// DORMANT until you set a SITE_PASSWORD env var in Vercel. When set, /full shows a
// small password-only page (no username) and remembers you for 30 days via a cookie.
// The public demo at / is never gated. Everything travels over HTTPS only.

export const config = {
  // Gate only the private full-coverage view; the public demo at / stays open.
  matcher: ['/full', '/full/:path*'],
};

const COOKIE = 'atlas_full';

// Cookie value is a hash of the password, so the password itself is never stored.
async function tokenFor(secret) {
  const bytes = new TextEncoder().encode('atlas-coverage:' + secret);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

function passwordPage(error) {
  const html = `<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas Coverage</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:grid;place-items:center;
    background:radial-gradient(900px 420px at 50% -10%,#fff,transparent 60%),#f3f6fa;
    font-family:"Albert Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:#15181f}
  form{background:#fff;border:1px solid #dce0e7;border-radius:14px;padding:36px 30px;width:312px;
    box-shadow:0 8px 28px rgba(16,42,77,.08);text-align:center}
  .mark{font-size:2rem;font-weight:700;letter-spacing:.14em;color:#15181f}
  .mark .dot{color:#b3122b}
  .sub{font-family:ui-monospace,"SFMono-Regular",monospace;font-size:10px;letter-spacing:.28em;
    text-transform:uppercase;color:#b3122b;margin:8px 0 24px}
  input{width:100%;padding:12px 14px;font-size:15px;border:1px solid #dce0e7;border-radius:10px;outline:none}
  input:focus{border-color:#1a3f6e;box-shadow:0 0 0 4px rgba(19,49,92,.12)}
  button{width:100%;margin-top:12px;padding:12px;font-size:14px;font-weight:600;color:#fff;
    background:#13315c;border:0;border-radius:10px;cursor:pointer}
  button:hover{background:#1a3f6e}
  .err{color:#b3122b;font-size:12.5px;margin-top:12px;min-height:1.1em}
</style></head><body>
  <form method="POST" autocomplete="off">
    <div class="mark">ATLAS<span class="dot">.</span></div>
    <div class="sub">Private Coverage</div>
    <input type="password" name="password" placeholder="Password" autofocus aria-label="Password">
    <button type="submit">Enter</button>
    <div class="err">${error || ''}</div>
  </form>
</body></html>`;
  return new Response(html, { status: 401, headers: { 'content-type': 'text/html; charset=utf-8' } });
}

export default async function middleware(request) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return; // no password configured, site is open

  const expected = await tokenFor(password);

  if (request.method === 'POST') {
    let given = '';
    try { given = String((await request.formData()).get('password') || ''); } catch (_) {}
    if (given !== password) return passwordPage('Incorrect password. Try again.');
    // Correct: set the cookie, then reload the current URL (works behind the /atlas proxy too).
    return new Response('<!DOCTYPE html><meta http-equiv="refresh" content="0"><title>Unlocking</title>', {
      status: 200,
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'set-cookie': `${COOKIE}=${expected}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`,
      },
    });
  }

  const cookies = (request.headers.get('cookie') || '').split(/;\s*/);
  if (cookies.includes(`${COOKIE}=${expected}`)) return; // authorized

  return passwordPage('');
}
