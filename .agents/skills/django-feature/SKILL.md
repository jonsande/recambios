---
name: django-feature
description: Use this skill when adding or extending a feature in an existing Django app, especially when the work may involve models, migrations, admin, forms, views, urls, templates, serializers, or tests. Do not use it for deployment-only tasks or broad architecture planning.
---

You are implementing a Django feature in an existing codebase.

Checklist:
1. Inspect the relevant app files before making changes.
2. Identify whether the change requires updates to models, migrations, admin, forms, views, urls, templates, serializers, permissions, or tests.
3. Keep the change minimal and aligned with the current project architecture.
4. If a model changes, create or update migrations and check downstream impacts.
5. Add or update admin integration when relevant.
6. Add or update focused tests for the intended behavior.
7. Run the smallest relevant validation commands before finishing.
8. Summarize touched files, behavior changed, assumptions made, and follow-up risks.