/**
 * Messages for /login?error=<code>. The Google callback redirects here instead of returning JSON,
 * because a JSON error is a dead end in an iPhone Home Screen web app (no back button).
 * Codes come from backend/app/routers/auth.py (_sign_in_failed).
 */
const MESSAGES = {
  google: "Google sign-in didn't finish. Try again.",
  unverified: "Google hasn't verified that email address, so it can't be used to sign in.",
}

export function signInErrorMessage(code) {
  if (typeof code !== 'string') return null
  return Object.prototype.hasOwnProperty.call(MESSAGES, code) ? MESSAGES[code] : null
}
