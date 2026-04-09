---
name: deployment-checklist
description: Use this skill for Django deployment preparation, production settings review, static and media handling, environment variables, process management, reverse proxy setup, and release validation.
---

Deployment checklist:
- Verify required environment variables and secrets strategy.
- Review DEBUG, ALLOWED_HOSTS, CSRF settings, secure cookies, HTTPS-related settings, and database configuration.
- Confirm static files and media file strategy.
- Confirm application server and reverse proxy configuration.
- Confirm migration and collectstatic steps.
- Confirm logging, error monitoring, and backup basics.
- Produce a release checklist and rollback notes.
- Flag unclear operational assumptions instead of inventing infrastructure details.