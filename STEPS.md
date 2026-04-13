# STEPS.md

# Guía Paso a Paso para Codex
## Tienda online de recambios de automoción — v1

> Propósito: este archivo guía a Codex fase por fase.
> Antes de tocar una fase, debe leerse el documento completo además del bloque correspondiente y las skills indicadas.
> No avanzar a la siguiente fase si falla la verificación de la actual.

---

## ⚠️ Reglas fundamentales

1. Lee `SKILLS.md` antes de empezar cualquier fase.
2. Respeta el enfoque **Mobile-First** en toda decisión de frontend.
3. No introduzcas Bootstrap.
4. No implementes compra inmediata como flujo principal de v1.
5. Mantén PostgreSQL como base de datos objetivo desde desarrollo.
6. No modeles referencias, compatibilidades o atributos técnicos como texto libre si deben ser buscables o filtrables.
7. No avances de fase si falla la verificación.
8. Haz commits atómicos por bloque funcional.
9. Prioriza claridad y robustez sobre velocidad aparente.
10. Si una decisión de UI entra en conflicto con accesibilidad, gana accesibilidad.

---

## 📋 Skills del proyecto

| Skill | Propósito |
|-------|-----------|
| `tailwind-design-system` | sistema visual, tokens, componentes, responsive patterns |
| `web-accessibility` | HTML semántico, teclado, foco, ARIA, validación a11y |
| `django-feature` | implementar funcionalidad en apps Django |
| `ecommerce-catalog` | catálogo, referencias, compatibilidades, dominio de recambios |
| `django-tests` | tests de comportamiento y dominio |
| `django-refactor` | refactors controlados |
| `deployment-checklist` | settings de producción, release, static/media |
| `seo-audit` | SEO técnico, metas, sitemap, canonical |
| `web-performance-optimization` | imágenes, carga, JS/CSS, rendimiento |

---

## FASE 0 — Preparación técnica del proyecto
**[SKILLS: django-feature, django-refactor]**

### Objetivos
- consolidar estructura del repo
- cerrar configuración base Django
- conectar PostgreSQL en desarrollo
- dejar Git/GitHub listo
- dejar Tailwind preparado, sin frontend de negocio todavía

### Tareas
- validar split settings `base/dev/prod`
- configurar `.env` y `.env.example`
- configurar PostgreSQL local
- revisar `pyproject.toml`, `ruff`, `pytest`
- crear apps base del proyecto si faltan
- dejar `AGENTS.md`, `SKILLS.md`, `STEPS.md` y `TODO.md` en el repo
- inicializar Git y conectar con GitHub
- preparar base Tailwind compatible con Django templates

### Verificación
```bash
python src/manage.py check
python src/manage.py makemigrations --check
ruff check .
pytest
```
Además:
- la app debe arrancar con PostgreSQL
- el repo debe tener `.gitignore` correcto
- la estructura debe estar lista para desarrollo posterior

---

## FASE 1 — Núcleo del dominio y modelo de datos
**[SKILLS: ecommerce-catalog, django-feature, django-tests]**

### Objetivos
Implementar el dominio principal del catálogo y solicitudes.

### Modelos esperados mínimos
- `Supplier`
- `Brand`
- `Category`
- `Condition`
- `Product`
- `PartNumber`
- `Vehicle`
- `ProductVehicleFitment`
- `AttributeDefinition`
- `ProductAttributeValue`
- `ProductImage`
- `Inquiry` / `QuoteRequest`
- `InquiryItem` / `QuoteRequestItem`
- `SupplierImport`
- `SupplierImportRow`

### Propuesta inicial de campos por entidad

#### Supplier
- id
- name
- slug
- code
- country
- website
- contact_name
- contact_email
- contact_phone
- is_active
- created_at
- updated_at

#### Brand
- id
- name
- slug
- brand_type
- country
- is_active
- created_at
- updated_at

#### Category
- id
- name
- slug
- parent
- description
- sort_order
- is_active
- created_at
- updated_at

#### Condition
- id
- code
- name
- slug
- description
- is_active
- created_at
- updated_at

#### Product
- id
- supplier
- supplier_product_code
- sku
- slug
- title
- short_description
- long_description
- brand
- category
- condition
- publication_status
- published_at
- price_visibility_mode
- last_known_price
- currency
- unit_of_sale
- weight
- length
- width
- height
- featured
- is_active
- created_at
- updated_at

#### PartNumber
- id
- product
- brand
- number_raw
- number_normalized
- part_number_type
- is_primary
- notes
- created_at
- updated_at

#### Vehicle
- id
- vehicle_type
- brand
- model
- generation
- variant
- year_start
- year_end
- engine_code
- fuel_type
- displacement_cc
- power_hp
- power_kw
- notes
- is_active
- created_at
- updated_at

#### ProductVehicleFitment
- id
- product
- vehicle
- fitment_notes
- source
- is_verified
- created_at
- updated_at

#### AttributeDefinition
- id
- name
- slug
- data_type
- unit
- is_filterable
- is_visible_on_product
- allows_multiple_values
- sort_order
- created_at
- updated_at

#### ProductAttributeValue
- id
- product
- attribute_definition
- value_text
- value_number
- value_boolean
- value_normalized
- created_at
- updated_at

#### ProductImage
- id
- product
- image
- alt_text
- sort_order
- is_primary
- created_at
- updated_at

#### Inquiry / QuoteRequest
- id
- reference_code
- user
- guest_email
- guest_name
- guest_phone
- company_name
- tax_id
- language
- status
- notes_from_customer
- internal_notes
- response_due_at
- supplier_feedback_at
- created_at
- updated_at

#### InquiryItem / QuoteRequestItem
- id
- inquiry
- product
- requested_quantity
- customer_note
- last_known_price_snapshot
- created_at
- updated_at

#### SupplierImport
- id
- supplier
- uploaded_by
- original_file
- import_status
- total_rows
- successful_rows
- failed_rows
- started_at
- finished_at
- created_at
- updated_at

#### SupplierImportRow
- id
- supplier_import
- row_number
- raw_payload
- processing_status
- linked_product
- error_message
- created_at

### Nota de diseño
Esta propuesta es la base inicial para la fase de modelado.
Puede ajustarse cuando se implemente la fase correspondiente, pero el objetivo es llegar a esa fase con una estructura suficientemente decidida como para evitar improvisación.

### Reglas
- `Supplier` debe existir desde v1
- `Condition` debe incluir: nuevo, usado, reacondicionado, core, despiece
- `Product` debe soportar precio visible o no visible
- debe poder haber precio estimado orientativo
- referencias y compatibilidades deben estar bien indexadas
- diseñar unicidades e índices razonables

### Verificación
- migraciones limpias
- admin carga correctamente
- tests de integridad básicos pasan
- búsquedas por referencia normalizada son posibles
- relaciones producto-vehículo y producto-referencia quedan operativas

---

## FASE 2 — Admin, roles y permisos
**[SKILLS: django-feature, django-tests]**

### Objetivos
Construir un backoffice útil desde muy pronto.

### Debe incluir
- admin útil para catálogo
- inlines donde aporten valor
- búsqueda y filtros admin
- gestión de usuarios y grupos/roles
- permisos para proveedor restringido
- workflow de borrador/revisión/publicación cuando proceda

### Reglas
- el proveedor no publica directamente
- el proveedor solo ve/edita lo autorizado
- el admin interno debe poder revisar y publicar

### Verificación
- administrador puede gestionar catálogo y solicitudes
- proveedor restringido no ve áreas prohibidas
- tests básicos de permisos pasan

---

## FASE 3 — Inquiry / QuoteRequest
**[SKILLS: django-feature, django-tests]**

### Objetivos
Implementar la base del flujo de solicitud comercial de la v1.

### Debe incluir
- modelo `Inquiry` / `QuoteRequest`
- modelo `InquiryItem` / `QuoteRequestItem`
- soporte para usuario registrado
- soporte para invitado
- estados de solicitud claros
- datos de contacto del solicitante
- notas del cliente
- notas internas
- `response_due_at`
- `supplier_feedback_at`
- admin útil para revisión interna

### Reglas
- no implementar todavía UI pública
- no implementar envío de emails todavía
- no implementar pago ni checkout
- mantener el flujo alineado con la lógica de solicitud previa de la v1

### Verificación
- una solicitud puede existir para usuario registrado o invitado
- las líneas de solicitud quedan correctamente asociadas
- el admin permite revisar y actualizar estados
- tests básicos de integridad y flujo pasan

---

## FASE 4 — Importación Excel
**[SKILLS: django-feature, ecommerce-catalog, django-tests]**

### Objetivos
Permitir carga manual del catálogo mediante Excel.

### Debe incluir
- plantilla Excel oficial descargable
- importación manual desde admin o panel interno
- validación de estructura
- vista previa o simulación si es viable
- creación/actualización según SKU o reglas definidas
- trazabilidad por importación y por fila
- informe de errores

### Reglas
- el formato interno manda
- no duplicar entidades normalizadas
- registrar errores sin corromper datos

### Mejoras posteriores previstas dentro de la línea de importación
- dry-run / preview sin escritura en base de datos
- soporte para categorías jerárquicas en importación
- extensión de importación a `PartNumber`
- extensión de importación a `ProductAttributeValue`
- extensión de importación a `ProductVehicleFitment`
- estrategia de importación de imágenes
- posible mapeo flexible por proveedor en fases posteriores

### Verificación
- una importación válida crea/actualiza correctamente
- una importación inválida informa errores entendibles
- se puede descargar plantilla oficial

---

## FASE 5 — Catálogo público base
**[SKILLS: django-feature, tailwind-design-system, web-accessibility]**

### Objetivos
Construir el catálogo navegable público.

### Debe incluir
- home básica
- listado de categorías
- listado de productos
- ficha de producto
- páginas corporativas básicas
- navegación clara

### Reglas UI
- Mobile-First
- Tailwind
- componentes reutilizables
- HTML semántico
- diseño serio, técnico y claro

### Verificación
- páginas renderizan sin errores
- móvil funciona correctamente
- desktop escala correctamente
- accesibilidad básica cubierta

---

## FASE 6 — Búsqueda técnica y filtros
**[SKILLS: ecommerce-catalog, django-feature, django-tests]**

### Objetivos
Implementar búsqueda útil para usuarios técnicos y generales.

### Debe incluir
- búsqueda por SKU
- búsqueda por referencia cruzada
- búsqueda por marca/modelo cuando proceda
- filtros por marca, año, modelo, categoría, condición y atributos técnicos
- resultados refinables

### Reglas
- la búsqueda por referencia tiene prioridad de calidad
- el sistema debe permitir encontrar productos por marca de vehículo
- optimizar consultas razonablemente

### Verificación
- consultas técnicas devuelven resultados correctos
- filtros combinados funcionan
- tests básicos de búsqueda pasan

---

## FASE 7 — Compatibilidad por vehículo
**[SKILLS: ecommerce-catalog, django-feature, django-tests]**

### Objetivos
Permitir navegar y validar compatibilidades.

### Debe incluir
- relación producto-vehículo operativa
- consulta por marca/modelo/año o combinación equivalente
- visualización clara en ficha de producto
- estructura compatible con distintos tipos de vehículo

### Reglas
- no optimizar solo para coches; debe ser soportable para otros vehículos desde v1
- mantener la estructura extensible

### Verificación
- se puede consultar compatibilidad
- la relación es consistente
- tests y validaciones de integridad pasan

---

## FASE 8 — Emails transaccionales y comunicaciones
**[SKILLS: django-feature, django-tests]**

### Objetivos
Implementar la capa inicial de comunicaciones del flujo comercial.

### Debe incluir
- confirmación interna de nueva solicitud
- confirmación al cliente de recepción de solicitud
- base de plantillas de email
- soporte ES/EN en plantillas críticas
- separación clara entre emails internos y emails al cliente
- configuración segura para desarrollo y producción

### Reglas
- no automatizar todavía la comunicación con proveedor salvo que sea estrictamente necesario
- evitar lógica compleja de colas o automatización avanzada en la primera iteración
- cada email debe corresponder a un evento de negocio claro

### Verificación
- existe envío básico de emails en desarrollo
- las plantillas clave se renderizan correctamente
- el sistema puede enviar al menos confirmación interna y confirmación al cliente
- tests básicos del flujo de email pasan

---

## FASE 9 — Frontend refinado y sistema visual
**[SKILLS: tailwind-design-system, web-accessibility, web-design-guidelines]**

### Objetivos
Refinar UI y convertirla en un sistema coherente.

### Debe incluir
- componentes reutilizables
- estados de interacción
- estados vacíos
- filtros bien presentados
- tablas o bloques técnicos legibles
- jerarquía visual consistente

### Reglas
- Mobile-First siempre
- no embellecer a costa de claridad técnica
- accesibilidad y foco visibles

### Verificación
- experiencia móvil sólida
- consistencia visual entre páginas
- accesibilidad funcional revisada

---

## FASE 10 — Oferta confirmada y pago posterior
**[SKILLS: django-feature, django-tests]**

### Objetivos
Preparar la capa posterior a la confirmación manual de disponibilidad, precio y plazo.

### Debe incluir
- modelo o estructura para oferta confirmada, si resulta necesaria
- aceptación o rechazo por parte del cliente
- base para pago posterior a confirmación
- trazabilidad de importe final confirmado
- separación clara entre solicitud inicial y pago posterior

### Reglas
- no convertir esto en checkout inmediato clásico
- el pago debe ocurrir después de confirmación manual interna
- mantener flexibilidad para elegir pasarela o método de pago más adelante

### Verificación
- existe una base de dominio coherente para aceptar una oferta confirmada
- el importe final confirmado queda trazable
- la solución no rompe el flujo principal de solicitud previa

---

## FASE 11 — SEO, rendimiento y contenido bilingüe
**[SKILLS: seo-audit, web-performance-optimization, web-accessibility]**

### Objetivos
Dejar la web preparada para indexación y uso real.

### Debe incluir
- meta tags dinámicos
- sitemap
- robots.txt
- slugs limpios
- base ES/EN
- contenido traducible
- optimización razonable de imágenes y estáticos
- selector manual de idioma visible en la web pública
- estrategia de selección inicial de idioma para usuarios nuevos
- política clara para `/es/` y `/en/`

### Reglas
- español por defecto
- inglés adicional
- no abrir más idiomas en v1
- priorizar URLs explícitas por idioma (`/es/` y `/en/`)
- preferir detección inicial por `Accept-Language` del navegador antes que geolocalización agresiva por país
- evitar duplicación innecesaria de URLs públicas sin prefijo de idioma

### Verificación
- HTML con metas correctas
- sitemap accesible
- robots.txt correcto
- páginas principales listas en ES y EN
- selector manual de idioma operativo
- estrategia inicial de idioma documentada e implementada de forma coherente

---

## FASE 12 — Producción y despliegue
**[SKILLS: deployment-checklist]**

### Objetivos
Preparar despliegue en servidor contratado.

### Debe incluir
- settings de producción seguros
- static/media definidos
- gunicorn o equivalente
- reverse proxy según infraestructura
- collectstatic
- migraciones
- logs básicos
- backup mínimo

### Verificación
- `prod.py` correcto
- despliegue reproducible
- checklist de release clara
- rollback básico documentado

---

## ✅ Criterios de aceptación por fase

### Fase 0
- Django arranca con PostgreSQL en desarrollo
- settings divididos funcionan
- lint y checks básicos pasan
- el repo está listo para trabajar con Codex

### Fase 1
- el modelo de datos central está implementado
- migraciones son coherentes
- existen índices y unicidades básicas
- el dominio soporta referencias, compatibilidades, proveedor e imports
- `Product` soporta `published_at`
- `SupplierImport` conserva trazabilidad temporal completa

### Fase 2
- el admin permite gestionar el dominio sin fricción grave
- los roles mínimos funcionan
- el proveedor no puede publicar ni acceder a áreas restringidas

### Fase 3
- `Inquiry` y `InquiryItem` están implementados
- una solicitud puede existir para usuario registrado o invitado
- el estado de la solicitud es entendible y gestionable
- el backoffice puede revisar y actualizar solicitudes

### Fase 4
- existe plantilla Excel oficial descargable
- la importación crea o actualiza datos sin duplicidades graves
- errores y trazabilidad quedan registrados

### Fase 5
- el catálogo público es navegable y usable en móvil
- la ficha de producto y los listados son claros
- la base visual ya es consistente

### Fase 6
- la búsqueda por referencia y SKU funciona con fiabilidad
- los filtros mínimos acordados están operativos
- el refinado de resultados es usable

### Fase 7
- la compatibilidad por vehículo puede consultarse y entenderse
- el sistema soporta distintos tipos de vehículo sin acoplarse solo a coches

### Fase 8
- existe una base funcional de emails transaccionales
- las plantillas clave están operativas
- cliente y equipo interno reciben comunicaciones básicas correctas

### Fase 9
- la interfaz es coherente, clara y mobile-first
- los componentes reutilizables cubren las áreas clave
- accesibilidad funcional mínima está revisada

### Fase 10
- existe base funcional para aceptación de oferta confirmada y pago posterior
- la solución mantiene separado el flujo de solicitud inicial del pago

### Fase 11
- SEO técnico base está implementado
- ES/EN están operativos en estructura y contenido base
- rendimiento es razonable para una primera versión pública
- existe una estrategia clara de idioma público

### Fase 12
- producción está documentada y configurada
- el despliegue es reproducible
- existe checklist de release y rollback básico

---

## Mejoras operativas posteriores

### Idioma del panel de administración
- definir política de idioma del panel de administración
- decidir si el admin debe usar español por defecto o respetar preferencia de usuario/navegador
- revisar si la internacionalización estándar de Django admin es suficiente para el backoffice del proyecto

### Nota
Estas mejoras no reabren la Fase 2; se consideran refinamientos operativos posteriores sobre una fase ya completada.

## 📌 Resumen de alcance v1

### Entra en v1
- monoproveedor
- multiproveedor preparado a nivel de modelo
- ES/EN
- catálogo robusto
- búsqueda técnica
- filtros
- compatibilidad por vehículo
- registro opcional de usuario
- solicitud como invitado
- carrito de solicitud
- importación Excel manual
- panel admin sólido
- rol proveedor restringido

### Queda fuera de v1
- multiproveedor real operativo
- compra inmediata plenamente automática
- integración automática avanzada con proveedor
- logística automatizada completa
- promociones complejas
- analítica avanzada
- más idiomas
- búsqueda avanzada con motor externo

---