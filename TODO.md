# TODO.md

# Plan de implementación — Tienda de recambios v1

## Progreso general

- [ ] **Fase 0** — Preparación técnica del proyecto
  - [x] cerrar split settings
  - [x] configurar PostgreSQL en desarrollo
  - [x] revisar `.env`, `.env.example`, `.gitignore`, `pyproject.toml`
  - [ ] preparar base Tailwind
  - [ ] cerrar Git/GitHub
  - [x] añadir documentación base (`AGENTS.md`, `SKILLS.md`, `STEPS.md`, `TODO.md`)

- [ ] **Fase 1** — Núcleo del dominio y modelo de datos
  - [ ] Supplier
  - [ ] Brand
  - [ ] Category
  - [ ] Condition
  - [ ] Product
  - [ ] PartNumber
  - [ ] Vehicle
  - [ ] ProductVehicleFitment
  - [ ] AttributeDefinition
  - [ ] ProductAttributeValue
  - [ ] ProductImage
  - [ ] Inquiry / QuoteRequest
  - [ ] InquiryItem / QuoteRequestItem
  - [ ] SupplierImport
  - [ ] SupplierImportRow
  - [ ] índices y unicidades básicas

- [ ] **Fase 2** — Admin, roles y permisos
  - [ ] admin útil del catálogo
  - [ ] filtros y búsquedas de admin
  - [ ] roles mínimos
  - [ ] permisos de proveedor restringido
  - [ ] revisión/publicación interna

- [ ] **Fase 3** — Importación Excel
  - [ ] plantilla oficial descargable
  - [ ] importación manual
  - [ ] validación de columnas
  - [ ] preview o simulación
  - [ ] trazabilidad de importación
  - [ ] informe de errores

- [ ] **Fase 4** — Catálogo público base
  - [ ] home
  - [ ] categorías
  - [ ] listado de productos
  - [ ] ficha de producto
  - [ ] páginas corporativas
  - [ ] navegación base

- [ ] **Fase 5** — Búsqueda técnica y filtros
  - [ ] búsqueda por SKU
  - [ ] búsqueda por referencia cruzada
  - [ ] búsqueda por marca/modelo
  - [ ] filtros por marca
  - [ ] filtros por año
  - [ ] filtros por modelo
  - [ ] filtros por categoría
  - [ ] filtros por condición
  - [ ] filtros por atributos técnicos

- [ ] **Fase 6** — Compatibilidad por vehículo
  - [ ] consulta por vehículo
  - [ ] visualización en ficha
  - [ ] soporte para diferentes tipos de vehículo

- [ ] **Fase 7** — Flujo de solicitud comercial
  - [ ] botón por producto
  - [ ] carrito de solicitud
  - [ ] solicitud como invitado
  - [ ] solicitud como usuario registrado
  - [ ] estados de solicitud
  - [ ] panel interno de gestión

- [ ] **Fase 8** — Frontend refinado y sistema visual
  - [ ] componentes reutilizables
  - [ ] mobile-first sólido
  - [ ] accesibilidad funcional
  - [ ] estados vacíos y errores
  - [ ] refinado de tablas y bloques técnicos

- [ ] **Fase 9** — SEO, rendimiento y bilingüe ES/EN
  - [ ] meta tags dinámicos
  - [ ] sitemap
  - [ ] robots.txt
  - [ ] contenidos traducibles
  - [ ] base ES/EN operativa
  - [ ] optimización razonable de imágenes

- [ ] **Fase 10** — Producción y despliegue
  - [ ] settings de producción
  - [ ] static/media
  - [ ] gunicorn
  - [ ] checklist de release
  - [ ] despliegue al servidor
