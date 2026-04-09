---
name: django-refactor
description: Use this skill for safe refactors in a Django codebase when behavior should remain unchanged or only minimally adjusted. Do not use it for intentional feature expansion unless the task explicitly includes it.
---

Refactor rules:
- Preserve behavior unless the task explicitly includes a behavior change.
- Separate mechanical renames from logic changes when possible.
- Keep diffs reviewable and easy to verify.
- Check for migration, import-path, and template-reference risks.
- Run targeted validation after each meaningful step when practical.
- Call out places where refactor safety cannot be fully guaranteed without broader test coverage.