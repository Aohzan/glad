# Database Configuration

GLAD supports two database backends:

1. SQLite (default)
2. PostgreSQL

## Default Configuration (SQLite)

By default, GLAD uses SQLite with the database file stored in the `data/glad.db` location. This configuration works out of the box without any additional setup.

## PostgreSQL Configuration

To use PostgreSQL instead of SQLite, set the following environment variables:

```bash
# Required
DB=postgres
DB_NAME=glad
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost

# Optional (defaults shown)
DB_PORT=5432
DB_SSL_MODE=prefer  # Options: disable, allow, prefer, require, verify-ca, verify-full
```

### Example configuration in .env file

Create or update your `.env` file with the following content:

```shell
DB=postgres
DB_NAME=glad
DB_USER=your_postgres_user
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
```

### Docker Compose Example

Here's an example `docker-compose.yml` snippet for using PostgreSQL:

```yaml
version: '3'

services:
  glad:
    build: .
    environment:
      - DB=postgres
      - DB_NAME=glad
      - DB_USER=postgres
      - DB_PASSWORD=postgrespassword
      - DB_HOST=postgres
      - DB_PORT=5432
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      - POSTGRES_PASSWORD=postgrespassword
      - POSTGRES_USER=postgres
      - POSTGRES_DB=glad

volumes:
  postgres_data:
```

## Migrating from SQLite to PostgreSQL

If you're switching from SQLite to PostgreSQL, you'll need to run the migrations again:

```bash
# Set the PostgreSQL environment variables first, then:
python manage.py migrate
```
