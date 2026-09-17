# Security Policy

## Supported versions

Only the latest release (the `latest` Docker tag) receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use
[GitHub private vulnerability reporting](https://github.com/Aohzan/glad/security/advisories/new)
to describe the issue, how to reproduce it and its impact. You should get an
acknowledgement within a week.

## Hardening checklist for self-hosting

- Set a long random `SECRET_KEY` and keep it out of version control.
- Serve the app behind a reverse proxy over HTTPS and set `APP_URL` to the
  public `https://` URL: secure cookies, HSTS and the HTTPS redirect follow from it.
- Keep the container image up to date; Dependabot and CodeQL run on this repository.
- Back up the `/app/data` volume (SQLite) or your PostgreSQL database regularly.
