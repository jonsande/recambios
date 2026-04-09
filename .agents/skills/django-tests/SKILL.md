---
name: django-tests
description: Use this skill when creating or updating Django tests for models, views, forms, admin behavior, permissions, query behavior, or business rules.
---

Testing rules:
- Write the smallest useful test set that covers the intended behavior.
- Prefer focused and readable tests over broad brittle tests.
- Cover model constraints, validation, and query behavior where relevant.
- For views, test status code, template usage, permissions, redirects, and key context when applicable.
- Avoid unnecessary fixtures when factories or direct setup are clearer.
- Prefer testing business behavior over internal implementation details.
- Mention what is intentionally not tested.