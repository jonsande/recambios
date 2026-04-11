# TODO.md

# Plan de implementación — Tienda de recambios v1

## Progreso general

- [x] **Fase 0** — Preparación técnica del proyecto
  - [x] cerrar split settings
  - [x] configurar PostgreSQL en desarrollo
  - [x] revisar `.env`, `.env.example`, `.gitignore`, `pyproject.toml`
  - [x] preparar base Tailwind
  - [x] cerrar Git/GitHub
  - [x] añadir documentación base (`AGENTS.md`, `SKILLS.md`, `STEPS.md`, `TODO.md`)

- [x] **Fase 1** — Núcleo del dominio y modelo de datos
  - [x] Supplier
  - [x] Brand
  - [x] Category
  - [x] Condition
  - [x] Product
  - [x] PartNumber
  - [x] Vehicle
  - [x] ProductVehicleFitment
  - [x] AttributeDefinition
  - [x] ProductAttributeValue
  - [x] ProductImage
  - [x] SupplierImport
  - [x] SupplierImportRow
  - [x] índices y unicidades básicas

- [x] **Fase 2** — Admin, roles y permisos
  - [x] admin útil del catálogo
  - [x] filtros y búsquedas de admin
  - [x] roles mínimos
  - [x] permisos de proveedor restringido
  - [x] revisión/publicación interna

- [x] **Fase 3** — Inquiry / QuoteRequest
  - [x] Inquiry / QuoteRequest
  - [x] InquiryItem / QuoteRequestItem
  - [x] soporte para usuario registrado
  - [x] soporte para invitado
  - [x] estados de solicitud
  - [x] admin útil de solicitudes
  - [x] notas internas y del cliente
  - [x] seguimiento temporal básico

- [ ] **Fase 4** — Importación Excel
  - [x] plantilla oficial descargable
  - [x] importación manual
  - [x] validación de columnas
  - [ ] preview o simulación
  - [x] trazabilidad de importación
  - [x] informe de errores
  - [ ] dry-run / preview sin escritura en base de datos
  - [ ] soporte futuro para categorías jerárquicas en importación
  - [ ] extensión de importación a PartNumber
  - [ ] extensión de importación a ProductAttributeValue
  - [ ] extensión de importación a ProductVehicleFitment
  - [ ] estrategia de importación de imágenes

- [ ] **Fase 5** — Catálogo público base
  - [ ] home
  - [ ] categorías
  - [ ] listado de productos
  - [ ] ficha de producto
  - [ ] páginas corporativas
  - [ ] navegación base

- [ ] **Fase 6** — Búsqueda técnica y filtros
  - [ ] búsqueda por SKU
  - [ ] búsqueda por referencia cruzada
  - [ ] búsqueda por marca/modelo
  - [ ] filtros por marca
  - [ ] filtros por año
  - [ ] filtros por modelo
  - [ ] filtros por categoría
  - [ ] filtros por condición
  - [ ] filtros por atributos técnicos

- [ ] **Fase 7** — Compatibilidad por vehículo
  - [ ] consulta por vehículo
  - [ ] visualización en ficha
  - [ ] soporte para diferentes tipos de vehículo

- [ ] **Fase 8** — Emails transaccionales y comunicaciones
  - [ ] confirmación interna de nueva solicitud
  - [ ] confirmación al cliente de recepción
  - [ ] plantillas base ES/EN
  - [ ] configuración de email para desarrollo y producción

- [ ] **Fase 9** — Frontend refinado y sistema visual
  - [ ] componentes reutilizables
  - [ ] mobile-first sólido
  - [ ] accesibilidad funcional
  - [ ] estados vacíos y errores
  - [ ] refinado de tablas y bloques técnicos

- [ ] **Fase 10** — Oferta confirmada y pago posterior
  - [ ] base de oferta confirmada
  - [ ] aceptación o rechazo por el cliente
  - [ ] trazabilidad del importe final confirmado
  - [ ] base para pago posterior

- [ ] **Fase 11** — SEO, rendimiento y bilingüe ES/EN
  - [ ] meta tags dinámicos
  - [ ] sitemap
  - [ ] robots.txt
  - [ ] contenidos traducibles
  - [ ] base ES/EN operativa
  - [ ] optimización razonable de imágenes

- [ ] **Fase 12** — Producción y despliegue
  - [ ] settings de producción
  - [ ] static/media
  - [ ] gunicorn
  - [ ] checklist de release
  - [ ] despliegue al servidor