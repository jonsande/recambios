---
name: ecommerce-catalog
description: Use this skill for tasks involving automotive parts catalog design, product references, OEM codes, cross references, brands, categories, fitment, and structured vehicle compatibility modeling.
---

When working on the automotive catalog:
- Separate product identity from product references.
- Support multiple references per product where relevant.
- Treat compatibility as structured data, not free text.
- Prefer normalized entities for vehicle make, model, version, engine, fuel type, body type, and year range when the project scope justifies it.
- Add indexes for lookup fields used in search or matching.
- Consider admin usability for bulk catalog maintenance.
- Flag risky assumptions about catalog semantics before implementing them.
- Prefer schema decisions that make imports, deduplication, and compatibility queries easier to maintain later.