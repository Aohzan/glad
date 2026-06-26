# Passkey Conditional UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual passkey login button with WebAuthn Conditional UI that automatically proposes passkeys as autocomplete suggestions in the username field.

**Architecture:** On page load, detect Conditional UI support, fetch auth options, set `autocomplete="webauthn"` on the username field, and call `navigator.credentials.get({ mediation: 'conditional' })`. The passkey button is removed. Traditional password login remains as fallback.

**Tech Stack:** Django templates, vanilla JavaScript, WebAuthn Conditional UI API

---

### Task 1: Rewrite login.html template and JS for Conditional UI

**Files:**
- Modify: `templates/registration/login.html`

- [ ] **Step 1: Rewrite login.html**

Replace the entire file content with:

```html
{% extends "registration/base_auth_form.html" %}
{% load i18n %}

{% block auth_title %}{% translate "Login" %}{% endblock %}
{% block auth_heading %}{% translate "Log In" %}{% endblock %}

{% block auth_fields %}
          {% include "registration/_form_field.html" with field=form.username %}
          {% include "registration/_form_field.html" with field=form.password %}
{% endblock %}

{% block auth_submit %}{% translate "Log In" %}{% endblock %}

{% block auth_extra %}
        <div id="passkey-login-status" class="small mt-2" aria-live="polite"></div>

        <div class="text-center mt-3">
          <p><a href="{% url 'password_reset' %}">{% translate "Password Reset" %}</a></p>
        </div>
{% endblock %}

{% block scripts %}
<script>
(function () {
  'use strict';

  const statusEl = document.getElementById('passkey-login-status');
  const optionsUrl = '{% url "accounts:passkey_auth_options" %}';
  const completeUrl = '{% url "accounts:passkey_auth_complete" %}';

  function getCsrfToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) return metaTag.getAttribute('content');
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : null;
  }

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.className = 'small mt-2 ' + (isError ? 'text-danger' : 'text-success');
  }

  function base64urlToUint8Array(value) {
    const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '==='.slice((base64.length + 3) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  function uint8ArrayToBase64url(bytes) {
    let binary = '';
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function nextUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('next') || '/';
  }

  async function authenticatePasskey(options) {
    options.challenge = base64urlToUint8Array(options.challenge);
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map((cred) => ({
        ...cred,
        id: base64urlToUint8Array(cred.id),
      }));
    }

    const assertion = await navigator.credentials.get({ publicKey: options });
    const payload = {
      id: assertion.id,
      rawId: uint8ArrayToBase64url(new Uint8Array(assertion.rawId)),
      type: assertion.type,
      response: {
        authenticatorData: uint8ArrayToBase64url(
          new Uint8Array(assertion.response.authenticatorData)
        ),
        clientDataJSON: uint8ArrayToBase64url(
          new Uint8Array(assertion.response.clientDataJSON)
        ),
        signature: uint8ArrayToBase64url(new Uint8Array(assertion.response.signature)),
        userHandle: assertion.response.userHandle
          ? uint8ArrayToBase64url(new Uint8Array(assertion.response.userHandle))
          : null,
      },
    };

    const csrfToken = getCsrfToken();
    const verifyResponse = await fetch(completeUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify(payload),
    });
    if (!verifyResponse.ok) {
      const errorData = await verifyResponse.json().catch(() => ({}));
      console.error('Verification failed:', errorData);
      throw new Error(errorData.error || 'verify_failed');
    }

    window.location.href = nextUrl();
  }

  if (!window.PublicKeyCredential) {
    return;
  }

  PublicKeyCredential.isConditionalMediationAvailable().then(function (available) {
    if (!available) return;

    var usernameField = document.getElementById('id_username');
    if (usernameField) {
      usernameField.setAttribute('autocomplete', 'webauthn');
    }

    getCsrfToken() && fetch(optionsUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
    })
    .then(function (response) {
      if (!response.ok) throw new Error('options_failed');
      return response.json();
    })
    .then(function (options) {
      return authenticatePasskey(options);
    })
    .catch(function (err) {
      if (err.name === 'NotAllowedError') return;
      console.error('Passkey login error:', err);
      if (err.message === 'verify_failed') {
        {% translate "Failed to verify passkey with server." as msg %}showStatus('{{ msg|escapejs }}', true);
      } else if (err.message !== 'options_failed') {
        {% translate "Passkey login failed:" as msg %}showStatus('{{ msg|escapejs }}' + ' ' + (err.message || err.name || 'Unknown error'), true);
      }
    });
  });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Verify the login page loads**

Run: `uv run pytest accounts/tests/test_views.py -v --no-cov`
Expected: All existing tests pass (no test changes needed yet)

- [ ] **Step 3: Commit**

```bash
git add templates/registration/login.html
git commit -m "feat: replace passkey button with conditional UI on login"
```

---

### Task 2: Write tests for login template changes

**Files:**
- Modify: `accounts/tests/test_views.py`

- [ ] **Step 1: Add tests for login page passkey elements**

Add the following tests at the end of `accounts/tests/test_views.py`:

```python


@pytest.mark.django_db
def test_login_page_has_no_passkey_button(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="passkey-login"' not in content


@pytest.mark.django_db
def test_login_page_has_passkey_status_element(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="passkey-login-status"' in content
    assert 'aria-live="polite"' in content


@pytest.mark.django_db
def test_login_page_has_conditional_ui_script(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'isConditionalMediationAvailable' in content
    assert 'mediation' not in content.replace("'conditional'", "")


@pytest.mark.django_db
def test_login_page_conditional_ui_sets_autocomplete(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'autocomplete' in content
    assert 'webauthn' in content
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest accounts/tests/test_views.py::test_login_page_has_no_passkey_button accounts/tests/test_views.py::test_login_page_has_passkey_status_element accounts/tests/test_views.py::test_login_page_has_conditional_ui_script accounts/tests/test_views.py::test_login_page_conditional_ui_sets_autocomplete -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Run all account tests**

Run: `uv run pytest accounts/tests/ -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add accounts/tests/test_views.py
git commit -m "test: add tests for passkey conditional UI on login page"
```

---

### Task 3: Update French translations

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`

- [ ] **Step 1: Generate translation messages**

Run: `uv run python manage.py makemessages -l fr`

- [ ] **Step 2: Translate new/changed strings in `locale/fr/LC_MESSAGES/django.po`**

The removed strings ("Log in with passkey", "Passkeys are not supported on this browser.", "Passkey login was cancelled.", "Failed to get authentication options from server.") will become obsolete. The remaining strings ("Failed to verify passkey with server.", "Passkey login failed:") already have translations. Verify no new untranslated strings exist.

- [ ] **Step 3: Compile translations**

Run: `uv run python manage.py compilemessages`

- [ ] **Step 4: Commit**

```bash
git add locale/fr/LC_MESSAGES/django.po locale/fr/LC_MESSAGES/django.mo
git commit -m "i18n: update French translations for conditional UI"
```

---

### Task 4: Run pre-commit and fix issues

- [ ] **Step 1: Run pre-commit on all files**

Run: `uv run prek run --all-files`

- [ ] **Step 2: Fix any issues reported**

Fix any linting, formatting, or translation issues until all hooks pass.

- [ ] **Step 3: Run full test suite with coverage**

Run: `uv run pytest --cov`
Expected: All tests pass, coverage meets threshold

- [ ] **Step 4: Final commit if needed**

```bash
git add -A
git commit -m "style: fix pre-commit issues"
```
