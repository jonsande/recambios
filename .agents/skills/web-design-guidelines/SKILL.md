---
name: web-design-guidelines
description: Use this skill when reviewing or improving Django templates, frontend components, forms, navigation, accessibility, responsive behavior, and general UI/UX quality. Do not use it for backend-only changes.
---

Review UI code against web interface best practices.

When auditing frontend code:
- Check semantic HTML and accessible structure.
- Check labels, alt text, ARIA usage, keyboard navigation, and focus visibility.
- Check forms for usability, validation clarity, and autocomplete where relevant.
- Check images, loading behavior, and layout stability.
- Check responsive behavior and touch interactions.
- Check dark mode, contrast, and theming issues where relevant.
- Check whether UI state and navigation are understandable and linkable.
- Prefer concrete findings tied to specific files and lines when possible.

If the task is in Django:
- Review templates, form rendering, template partials, and static assets.
- Consider server-rendered HTML behavior, not only SPA patterns.
- Distinguish true accessibility issues from stylistic preferences.