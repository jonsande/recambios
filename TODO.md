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

- [x] **Fase 5** — Catálogo público base
  - [x] home
  - [x] categorías
  - [x] listado de productos
  - [x] ficha de producto
  - [x] páginas corporativas
  - [x] navegación base

- [x] **Fase 6** — Búsqueda técnica y filtros
  - [x] búsqueda por SKU
  - [x] búsqueda por referencia cruzada
  - [x] búsqueda por marca/modelo
  - [x] filtros por marca
  - [x] filtros por año
  - [x] filtros por modelo
  - [x] filtros por categoría
  - [x] filtros por condición
  - [x] filtros por atributos técnicos

- [x] **Fase 7** — Compatibilidad por vehículo
  - [x] consulta por vehículo
  - [x] visualización en ficha
  - [x] soporte para diferentes tipos de vehículo

- [x] **Fase 8** — Emails transaccionales y comunicaciones
  - [x] confirmación interna de nueva solicitud
  - [x] confirmación al cliente de recepción
  - [x] plantillas base ES/EN
  - [x] configuración de email para desarrollo y producción

- [x] **Fase 9** — Formulario público de solicitud y carrito de solicitud
  - [x] botón de solicitud por producto
  - [x] carrito de solicitud multiartículo
  - [x] formulario público de solicitud
  - [x] solicitud como invitado
  - [x] solicitud como usuario registrado
  - [x] validación de datos del cliente
  - [x] creación de `Inquiry` e `InquiryItem` desde la web pública
  - [x] transición a `submitted` solo en el envío final real
  - [x] página de confirmación posterior al envío

- [ ] **Fase 10** — Frontend refinado y sistema visual
  - [ ] componentes reutilizables
  - [ ] mobile-first sólido
  - [ ] accesibilidad funcional
  - [ ] estados vacíos y errores
  - [ ] refinado de tablas y bloques técnicos

- [ ] **Fase 11** — Oferta confirmada y pago posterior
  - [x] **Bloque A — Oferta confirmada (flujo positivo)**
    - [x] modelo `InquiryOffer` (1:1 con `Inquiry`) con token público seguro y timestamps de ciclo de vida
    - [x] base de oferta confirmada
    - [x] aceptación o rechazo por el cliente
    - [x] trazabilidad del importe final confirmado
    - [x] semántica explícita de `confirmed_total` como fuente de verdad para preparar pago posterior
    - [x] base para pago posterior
    - [x] flujo público tokenizado para ver oferta y responder (aceptar/rechazar)
    - [x] reglas de transición seguras y prevención de doble respuesta
    - [x] backoffice en Django admin para gestión y envío de ofertas
    - [x] bloqueo en admin de campos comerciales tras envío (`confirmed_total`, `currency`, `lead_time_text`, `customer_message`)
    - [x] validación explícita de “ready to send” antes de enviar la oferta
  - [x] **Bloque B — No ofertable (resolución negativa)**
    - [x] resolución negativa “no ofertable” en `Inquiry` con razón estructurada, mensaje cliente, notas internas y timestamp de cierre
    - [x] acción de admin para finalizar consultas como no ofertables con validaciones de integridad
    - [x] regla de conflicto entre dominios: una `Inquiry` negativamente resuelta no puede convivir con `InquiryOffer`
  - [x] **Bloque C — Notificaciones transaccionales de oferta**
    - [x] email transaccional al cliente al entrar una oferta en estado `sent`, con enlace público tokenizado para aceptar/rechazar
    - [x] trigger de email por transición real `draft -> sent` (sin reenvío en ediciones posteriores)
    - [x] manejo robusto de incidencias de envío de email (logs claros sin revertir el estado comercial `sent`)
    - [x] notificación operativa al proveedor al entrar una oferta en `sent` usando `Supplier.orders_email`
    - [x] agrupación por proveedor en consultas mixtas (un email por proveedor con solo sus líneas)
    - [x] notificación interna cuando falla o falta el email operativo de proveedor, sin revertir estado comercial
  - [x] tests específicos de integridad y flujo de Fase 11
  - [ ] integración real de pasarela de pago (siguiente slice de Fase 11)

- [ ] **Fase 12** — SEO, rendimiento y bilingüe ES/EN
  - [ ] meta tags dinámicos
  - [ ] sitemap
  - [ ] robots.txt
  - [ ] contenidos traducibles
  - [ ] base ES/EN operativa
  - [ ] optimización razonable de imágenes
  - [ ] selector manual de idioma visible
  - [ ] estrategia de selección inicial de idioma
  - [ ] política estable para `/es/` y `/en/`

- [ ] **Fase 13** — Producción y despliegue
  - [ ] settings de producción
  - [ ] static/media
  - [ ] gunicorn
  - [ ] checklist de release
  - [ ] despliegue al servidor

## Mejoras operativas posteriores

- [ ] definir política de idioma del panel de administración
- [ ] decidir si el admin debe usar español por defecto o respetar preferencia de usuario/navegador
- [ ] revisar si la internacionalización estándar de Django admin es suficiente para el backoffice del proyecto
