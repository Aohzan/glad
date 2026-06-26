# Passkey Conditional UI on Login Page

## Summary

Replace the manual passkey login button with WebAuthn Conditional UI (mediation conditionnelle). Passkeys will be automatically proposed as autocomplete suggestions in the username field when available. The traditional username/password form remains as fallback.

## Current Behavior

- User must click a "Log in with passkey" button to trigger passkey authentication
- The button calls `navigator.credentials.get()` with a non-conditional mediation
- No automatic passkey detection or proposal

## New Behavior

1. On page load, detect WebAuthn + Conditional UI support via `PublicKeyCredential.isConditionalMediationAvailable()`
2. If supported: fetch auth options from `/accounts/api/passkey/auth/options/`, then call `navigator.credentials.get({ mediation: 'conditional', publicKey: options })`
3. The username field gets `autocomplete="webauthn"` -- the browser shows available passkeys as autofill suggestions
4. If the user selects a passkey from autofill: verification with server and redirect (same flow as current)
5. If the user ignores autofill and fills the form normally: traditional password login works
6. The "Log in with passkey" button is **removed**
7. Discrete status messages for errors (aria-live)

## Technical Changes

### `templates/registration/login.html`

- Remove the `#passkey-login` button and `#passkey-login-status` div from `auth_extra` block
- Rewrite JS:
  - On page load: check `PublicKeyCredential.isConditionalMediationAvailable()`
  - If available: fetch auth options, set `autocomplete="webauthn"` on `#id_username`, call `navigator.credentials.get({ mediation: 'conditional' })`
  - Keep existing utility functions (base64url, csrf, nextUrl)
  - Remove click handler
  - Add error handling: silent fallback to password login if conditional UI fails
- Add a small `aria-live="polite"` div for error messages

### `templates/registration/_form_field.html`

No changes. The `autocomplete="webauthn"` attribute is set via JS after render.

### `accounts/views.py`

No changes. Existing endpoints `passkey_auth_options` and `passkey_auth_complete` work as-is.

### `accounts/tests/test_views.py`

No functional changes needed. API tests remain valid.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| WebAuthn not supported | Nothing happens, password login only. No error message. |
| Conditional UI not supported | Same as above |
| Auth options fetch fails | Error logged to console, password login remains available |
| User cancels passkey selection | Autofill closes, user continues with form |
| Server verification fails | Error message shown in aria-live div |
| User submits password form while conditional call pending | Conditional call continues in background; whichever completes first authenticates the user. If conditional call resolves after form submission, the session is already established and the redirect has already occurred -- the conditional result is silently ignored. |

## Browser Compatibility

- Chrome 108+ (Dec 2022)
- Safari 16+ (Sep 2022)
- Edge 108+
- Firefox: not yet supported (in development)

Unsupported browsers gracefully fall back to password login.

## Implementation Notes

- The `autocomplete="webauthn"` attribute is set via JS (`document.getElementById('id_username').setAttribute('autocomplete', 'webauthn')`) rather than modifying the form field template, to avoid touching the reusable `_form_field.html` partial
- The conditional `navigator.credentials.get()` call returns a Promise that resolves when the user selects a passkey from the autocomplete dropdown
- No AbortController is needed since there is no fallback button to manage
