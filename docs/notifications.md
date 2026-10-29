# Notifications

Notifications always appear under the bell of the application. Each user chooses in **Settings › Notifications** which alerts they receive, with their thresholds, and the channels they reach them on.

## Channels

- **Email**: *Use my email* sends the notifications to the email address of the account, through the SMTP server of the application (`EMAIL_*` variables).
- **Apprise URL**: any of the services of [Apprise](https://appriseit.com/services/). Examples:

| Service | URL |
| --- | --- |
| ntfy | `ntfy://ntfy.sh/my-topic` or `ntfys://user:password@ntfy.example.com/my-topic` |
| Gotify | `gotifys://gotify.example.com/token` |
| Telegram | `tgram://bot_token/chat_id` |
| Discord | `discord://webhook_id/webhook_token` |
| Signal (signal-cli REST API) | `signal://signal.example.com/+33600000000/+33611111111` |
| Email (another server) | `mailtos://user:password@smtp.example.com?to=me@example.com` |

The URLs are stored encrypted with a key derived from `SECRET_KEY`: after changing the secret key, enter the channels again. A channel can be tested from the settings, and each alert can be limited to some channels.

## Checks

The alerts about dates and thresholds are checked once a day at `NOTIFICATIONS_TIME` (08:00 by default) by the scheduler started with the application; an alert already sent is not sent again (some are repeated after some days while they hold). The alerts about events (login, failed background job or email, signature completed) are sent at once.

Several alerts found by one check are grouped in a single message per channel.
