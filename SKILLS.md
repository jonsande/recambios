# SKILLS.md

## ⚠️ Prioridad de instrucciones del proyecto

Las reglas definidas en este archivo para arquitectura, dominio, UX, accesibilidad y flujo de trabajo **prevalecen** sobre skills genéricas externas cuando haya conflicto.

Orden de prioridad:

1. `SKILLS.md`
2. `STEPS.md`
3. `AGENTS.md`
4. `TODO.md`
5. skills externas genéricas

`TODO.md` sirve para seguimiento de progreso. No redefine arquitectura ni decisiones de producto.

---

## 📌 Contexto del negocio

Este proyecto es una tienda online de recambios de automoción.

### Alcance de producto

Se venderán recambios para:
- coches
- motos
- camiones
- otros vehículos compatibles en catálogo

En la **v1** solo habrá **un proveedor activo**, pero el sistema debe quedar preparado desde el principio para soportar **múltiples proveedores**.

### Modelo comercial de la v1

La v1 **no es un ecommerce de compra inmediata estándar**.

Flujo real:
1. el usuario busca y selecciona productos
2. envía una **solicitud de disponibilidad / presupuesto**
3. el equipo interno confirma con el proveedor disponibilidad, precio final y plazo
4. se responde al cliente
5. el cliente acepta
6. el equipo tramita compra y envío

### Público objetivo

La web debe servir tanto a:
- particulares
- talleres
- profesionales
- empresas

Sin embargo, la experiencia de búsqueda inicial debe estar especialmente optimizada para usuarios técnicos/profesionales.

---

## 🏗️ Stack tecnológico base

### Backend
- Django 5.x
- PostgreSQL desde desarrollo
- Django admin como backoffice inicial

### Frontend
- Tailwind CSS
- enfoque **Mobile-First** obligatorio
- Django Templates como base principal
- HTMX para interacciones servidor-cliente cuando aporte valor
- Alpine.js solo para interacciones locales ligeras

### Calidad técnica
- pytest
- ruff
- Whitenoise en producción
- Git + GitHub

### Reglas de stack
- **NO usar Bootstrap**.
- **NO usar React, Vue, Next.js ni frontend pesado** salvo necesidad futura claramente justificada.
- **NO usar CDNs externos** para fuentes ni JS si pueden servirse localmente.
- Priorizar SSR y HTML semántico.

---

## 📱 Enfoque de diseño

### Regla principal
- Diseñar **primero para móvil** y escalar hacia tablet y desktop.
- Toda UI debe funcionar correctamente en móvil antes de refinar desktop.

### Objetivos UX
La interfaz debe transmitir:
- claridad
- confianza
- precisión técnica
- facilidad de búsqueda
- sensación profesional

El frontend **no** debe parecer una plantilla genérica de ecommerce de moda.
Debe sentirse como una plataforma seria de recambios y consulta técnica.

### Reglas visuales
- usar Tailwind como sistema de utilidades
- construir componentes consistentes
- evitar ornamentación innecesaria
- priorizar legibilidad y jerarquía visual
- diseñar estados vacíos, errores, carga, filtros y tablas con el mismo cuidado que las páginas principales

### Skills de UI
- usar `tailwind-design-system` para layout, tokens, componentes y consistencia visual
- usar `web-accessibility` para semántica, teclado, foco, ARIA, contraste y validación a11y
- si ambas aplican a la vez, **`web-accessibility` manda en semántica e interacción** y `tailwind-design-system` manda en estilo y patrones visuales

---

## 🌍 Idiomas

Idiomas de la v1:
- español por defecto
- inglés adicional

No se implementarán más idiomas en la v1.

La arquitectura debe permitir i18n posterior sin rehacer el proyecto.

---

## 🧠 Reglas de dominio y modelado

### Principio central
El producto no debe contener toda la semántica del sistema. El modelo debe separar responsabilidades.

### Entidades nucleares esperadas
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
- `QuoteRequest` / `Inquiry`
- `QuoteRequestItem` / `InquiryItem`
- `SupplierImport`
- `SupplierImportRow`

### Reglas obligatorias de modelado
- separar identidad comercial de producto y referencias técnicas
- soportar múltiples referencias por producto
- soportar múltiples compatibilidades por producto
- modelar compatibilidad como relación estructurada, nunca como texto libre
- modelar condición con entidad normalizada
- modelar atributos técnicos con definición + valor
- añadir `Supplier` desde el principio aunque solo exista uno en v1
- diseñar el sistema para multiproveedor futuro

### Referencias
Las búsquedas por referencia son críticas.
Debe existir un campo de referencia normalizada para búsquedas robustas.

### Compatibilidad
La compatibilidad por vehículo debe ser buscable y filtrable.
No almacenar compatibilidades importantes como strings arbitrarios.

### Condiciones soportadas en v1
- nuevo
- usado
- reacondicionado
- core
- despiece

### Precios en v1
Cada producto debe soportar un modo de visibilidad de precio:
- sin precio visible
- con precio visible informativo

Si un producto muestra precio, debe tratarse como:
- **Último precio conocido**
- nunca como precio final garantizado
- siempre sujeto a confirmación posterior de disponibilidad, precio y plazo

La UI debe dejar claro que incluso cuando hay precio visible:
- sigue siendo necesaria la consulta previa

Si no muestra precio, la UI debe usar una llamada a la acción tipo:
- **Consultar precio y plazo**

---

## 🔎 Búsqueda y filtrado

La búsqueda debe ser uno de los pilares del proyecto.

### Búsquedas prioritarias
- SKU
- referencia principal
- referencias cruzadas
- marca de vehículo
- modelo de vehículo
- marca del recambio
- categoría
- texto general relevante

### Filtros mínimos v1
- marca
- año
- modelo
- categoría
- condición
- atributos técnicos

### Reglas
- diseñar pensando primero en búsquedas técnicas
- permitir también búsquedas más generales por texto
- una búsqueda por marca de vehículo debe poder listar productos relacionados y permitir refinado posterior

---

## 🧾 Flujo comercial y funcional

### V1: solicitud previa
No hay compra inmediata estándar como flujo principal.

### Debe existir
- botón por producto para consulta/supervisión comercial
- carrito de solicitud multiartículo
- solicitud como invitado
- solicitud como usuario registrado

### El sistema debe permitir
- recopilar datos del cliente
- recopilar datos de los productos solicitados
- añadir observaciones del cliente
- gestionar el estado de la solicitud
- registrar respuesta interna
- dejar trazabilidad mínima del proceso

### Estados recomendados para solicitud
- borrador
- enviada
- en revisión
- pendiente de respuesta del proveedor
- respondida al cliente
- aceptada por cliente
- rechazada por cliente
- cerrada

---

## 👤 Roles y permisos

### Roles mínimos v1
- administrador
- staff interno
- proveedor restringido
- cliente registrado
- invitado

### Administrador / staff interno
Debe poder:
- gestionar productos
- gestionar proveedores
- gestionar marcas, categorías, condiciones y vehículos
- gestionar atributos técnicos
- gestionar imágenes
- gestionar importaciones Excel
- gestionar solicitudes de clientes
- gestionar usuarios
- revisar y publicar borradores del proveedor

### Proveedor restringido
Debe poder:
- crear productos o propuestas en borrador
- editar solo sus propios borradores o registros permitidos
- subir imágenes
- proponer novedades
- proponer ofertas
- cargar Excel en su zona autorizada si así se habilita

No debe poder:
- publicar directamente
- ver usuarios o clientes completos
- ver márgenes internos o costes internos
- ver configuraciones globales
- modificar objetos no autorizados
- editar contenido de otros proveedores

---

## 📥 Importación Excel

La v1 debe incluir importación manual desde archivo Excel.

### Requisitos de la v1
- carga manual desde admin o panel interno
- plantilla Excel oficial descargable
- validación clara de columnas
- informe de errores por fila
- posibilidad de vista previa
- creación o actualización de registros según reglas definidas
- trazabilidad de importación

### Regla clave
El Excel real del proveedor no debe dictar directamente el modelo interno.
La plataforma debe tener una estructura canónica propia.

### Prioridad de implementación
Primero:
- plantilla oficial interna
- importador controlado

Más adelante:
- mapeo flexible por proveedor

---

## 🛡️ Accesibilidad

Objetivo mínimo: WCAG 2.1 AA razonable en toda la UI.

### Reglas obligatorias
- navegación completa por teclado
- foco visible siempre
- formularios con labels asociados
- HTML semántico antes que ARIA
- contraste suficiente
- imágenes con `alt`
- botones/iconos sin texto visible con `aria-label`
- mobile-first también en accesibilidad

---

## 🚀 SEO y rendimiento

### SEO v1
- URLs limpias
- slugs consistentes
- meta tags dinámicos
- sitemap
- robots.txt
- estructura semántica buena
- soporte base para ES/EN

### Rendimiento v1
- no sobredimensionar JS
- cargar solo lo necesario
- imágenes optimizadas
- evitar dependencia de frontend pesado

No convertir Lighthouse extremo en un bloqueo de fases tempranas, pero sí mantener buenas prácticas desde el inicio.

---

## ✍️ Convenciones editoriales y de naming

### Idioma y tono de contenido
- La interfaz pública debe redactarse primero en español y después en inglés.
- El tono debe ser claro, profesional, técnico y confiable.
- Evitar lenguaje marketiniano excesivo o ambiguo.
- No usar términos vagos cuando exista denominación técnica más precisa.

### Convenciones de naming técnico
- Python: `snake_case`
- clases Python: `PascalCase`
- constantes: `UPPER_SNAKE_CASE`
- nombres de apps: cortos, en minúscula, basados en dominio
- nombres de templates: `snake_case.html`
- nombres de bloques y parciales: explícitos y estables
- URLs: slugs limpios, legibles y estables
- CSS/Tailwind: preferir utilidades; si hay clases personalizadas, usar nombres semánticos y cortos

### Convenciones para entidades del dominio
- `Supplier`: nombre comercial oficial del proveedor
- `Brand`: usar nombre canónico, evitar duplicados por capitalización o variantes triviales
- `Category`: nombres singulares o plurales consistentes en todo el catálogo; no mezclar criterios
- `Condition`: usar slugs internos estables: `new`, `used`, `remanufactured`, `core`, `for_parts`
- `Product`: el título comercial debe ser claro, técnico y no excesivamente largo
- `PartNumber`: conservar el valor original y una versión normalizada para búsqueda
- `Vehicle`: nombres canónicos de marca/modelo/variante; evitar texto libre redundante

### Convenciones de slugs
- usar minúsculas
- usar guiones medios
- evitar IDs numéricos en URL pública salvo necesidad técnica interna
- los slugs deben ser estables y no depender de campos volátiles
- para contenido bilingüe, permitir estrategia traducible más adelante sin romper URLs innecesariamente

### Convenciones editoriales para productos
- Título recomendado: tipo de pieza + marca relevante + modelo o detalle técnico principal cuando aporte claridad
- No meter en el título toda la compatibilidad completa del vehículo
- La descripción corta debe resumir qué es la pieza y para qué sirve
- La descripción larga puede incluir compatibilidades, notas técnicas, estado, observaciones y condiciones comerciales
- Cuando haya precio visible, mostrarlo como **Último precio conocido** y acompañarlo de texto que indique confirmación posterior
- Cuando no haya precio visible, usar CTA explícita de consulta

### Convenciones para atributos técnicos
- el nombre visible del atributo debe ser corto y estable
- la unidad debe modelarse de forma consistente
- evitar crear atributos duplicados por pequeñas diferencias ortográficas
- distinguir entre valor visible al usuario y valor normalizado si hace falta para filtros

### Convenciones para importación
- la plantilla oficial manda sobre el formato del proveedor
- nombrar columnas de la plantilla de forma explícita y estable
- documentar qué campos son obligatorios y cuáles opcionales
- registrar siempre origen, fecha e identificación de la importación

## 🧪 Testing y validación

Antes de cerrar una tarea:
- ejecutar `ruff check .`
- ejecutar tests relevantes
- ejecutar `python src/manage.py check`
- ejecutar `python src/manage.py makemigrations --check` si hay modelos implicados
- resumir suposiciones, cambios y riesgos

### Filosofía de tests
- tests pequeños y útiles
- cubrir reglas de negocio reales
- no inflar el proyecto con tests irrelevantes

---

## 🧱 Estructura del proyecto esperada

```text
src/
├─ config/
│  ├─ settings/
│  │  ├─ base.py
│  │  ├─ dev.py
│  │  └─ prod.py
│  ├─ urls.py
│  ├─ asgi.py
│  └─ wsgi.py
├─ apps/
│  ├─ common/
│  ├─ users/
│  ├─ catalog/
│  ├─ vehicles/
│  ├─ inquiries/
│  ├─ suppliers/
│  ├─ imports/
│  ├─ pages/
│  └─ seo/
├─ templates/
├─ static/
└─ manage.py
```

Se pueden ajustar nombres si mejora claridad, pero mantener límites de dominio nítidos.

---

## 🧭 Reglas de trabajo con Codex

- cambios pequeños y revisables
- no mezclar refactor y feature salvo necesidad clara
- inspeccionar primero el código existente
- documentar decisiones importantes
- no improvisar modelo de datos por conveniencia de UI
- seguir `STEPS.md` por fases
- actualizar `TODO.md` conforme avanza el proyecto

---

## ✅ Definición de “hecho”

Una tarea está realmente terminada cuando:
1. está implementada
2. respeta el dominio y arquitectura definidos
3. pasa validaciones relevantes
4. no introduce deuda innecesaria
5. deja claro qué queda pendiente

---