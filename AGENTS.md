# AGENTS.md

## Project overview
This repository contains a Django-based automotive parts e-commerce project.
Priorities: robustness, clarity, maintainability, accessibility, and scalability.

## Technical baseline
- Backend framework: Django
- Database target: PostgreSQL
- Frontend styling: Tailwind CSS
- Templating approach: Django templates first
- JavaScript approach: progressive enhancement; avoid unnecessary frontend complexity
- Accessibility target: WCAG 2.1 AA by default

## Architecture rules
- Django project config lives in `src/config/`.
- Django apps live in `src/apps/`.
- Keep domain boundaries explicit: `common`, `catalog`, `vehicles`, `cart`, `orders`, `checkout`, `search`.
- Product identity, product references, and vehicle compatibility must be modeled separately.
- Avoid circular dependencies between apps.
- Keep reusable domain logic out of templates.

## Frontend and UI rules
- Use Tailwind CSS for frontend styling. Do not introduce Bootstrap.
- Prefer reusable utility patterns and design tokens over ad hoc styling.
- Favor server-rendered Django templates and progressive enhancement unless a stronger frontend requirement appears later.
- Build a coherent design system: typography, spacing, colors, states, form controls, cards, navigation, filters, product grids, pagination, and empty states.
- The frontend should feel modern, clean, and high-trust for automotive e-commerce.

## Skill usage rules
- Use `tailwind-design-system` for design tokens, component structure, visual consistency, responsive patterns, and reusable UI conventions.
- Use `web-accessibility` for semantic HTML, keyboard interaction, ARIA usage, focus management, contrast, and accessibility review.
- If both skills apply, `web-accessibility` takes precedence for semantics and interaction requirements, while `tailwind-design-system` governs styling and component patterns.
- Use `django-feature` for implementing or extending Django functionality.
- Use `ecommerce-catalog` for product catalog, references, fitment, compatibility, and automotive-specific modeling.
- Use `django-tests` when behavior changes or new business rules are introduced.
- Use `django-refactor` only for behavior-preserving cleanup or structural improvements.
- Use `deployment-checklist` for production settings, static/media strategy, process management, and release readiness.

## Data modeling rules
- Separate product identity from product references.
- Support multiple references per product, including OEM and equivalent codes.
- Model vehicle compatibility as structured relations, not free text.
- Prefer normalized entities for make, model, generation, engine, and year range.
- Add indexes for frequent lookups, especially reference codes, slugs, and compatibility joins.
- Design for future multi-supplier support, even if the first release only uses one supplier.

## Coding rules
- Make small, reviewable changes.
- Do not mix refactor and feature work unless necessary.
- Prefer explicit, readable code over clever abstractions.
- Add type hints when they improve clarity.
- Keep imports tidy and follow project linting rules.
- Avoid placeholder code that is not immediately useful.

## Testing and validation
Before finishing a task:
- run `ruff check .`
- run the smallest relevant test set
- run `python src/manage.py check`
- run `python src/manage.py makemigrations --check` when models may be affected
- summarize assumptions, changed files, and follow-up risks

## Accessibility requirements
- All interactive functionality must be usable by keyboard alone.
- Do not remove visible focus indication.
- All images must have appropriate `alt` text.
- All form fields must have associated labels.
- Use semantic HTML elements before adding ARIA.
- Meet WCAG 2.1 AA contrast expectations by default.

## Output expectations
When completing a task, summarize:
- files changed
- behavior introduced or modified
- assumptions made
- validation performed
- follow-up risks or recommended next steps