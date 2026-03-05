# Glad

[![Build and Publish Docker Image](https://github.com/Aohzan/glad/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Aohzan/glad/actions/workflows/docker-publish.yml)

Glad is a web app to follow its investments and properties, principally based on financial and properties in France (glad come from Breton).

## Features

- Finance
  - Savings accounts
  - Investment accounts
- Properties
  - Real estate (in progress)
  - Rental properties (in progress)
  - SCPI (in progress)
  - Load (TODO)

### Web application

- Multi-language support
- Multi-currency support
- Dark mode
- Responsive design
- Passwordless authentication with passkeys (WebAuthn)

## Configuration

### Docker Compose

```yaml
services:
  glad:
    image: ghcr.io/aohzan/glad:latest
    container_name: glad
    restart: unless-stopped
    ports:
      - 8000:8000
    volumes:
      - /opt/glad:/app/data
    environment:
      SECRET_KEY: "xxxxxxxxx"
      APP_URL: "https://glad.my.domain"
      ALLOWED_HOSTS: "glad.my.domain"
```

### Database

Glad supports both SQLite (default) and PostgreSQL databases. See [Database Configuration](docs/database.md) for details on how to set up PostgreSQL support.

## License

This project is licensed under the GNU GPLv3 License - see the LICENSE file for details.
