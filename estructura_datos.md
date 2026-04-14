# Estructura de datos (estado actual)

Última revisión: 2026-04-14

## Entidades nucleares actuales
- `Supplier`
- `SupplierUserAssignment`
- `Brand`
- `Category`
- `Condition`
- `PartNumberType`
- `Product`
- `PartNumber`
- `Vehicle`
- `ProductVehicleFitment`
- `AttributeDefinition`
- `ProductAttributeValue`
- `ProductImage`
- `Inquiry`
- `InquiryItem`
- `SupplierImport`
- `SupplierImportRow`

## Campos por entidad

### Supplier
- `id`: identificador interno.
- `name`: nombre comercial del proveedor.
- `slug`: slug único del proveedor.
- `code`: código interno único del proveedor.
- `country`: país del proveedor.
- `website`: web del proveedor.
- `contact_name`: nombre de contacto.
- `contact_email`: email de contacto.
- `contact_phone`: teléfono de contacto.
- `is_active`: proveedor activo/inactivo.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### SupplierUserAssignment
- `id`: identificador interno.
- `supplier`: proveedor asociado.
- `user`: usuario asociado.
- `is_active`: asignación activa/inactiva.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Brand
- `id`: identificador interno.
- `name`: nombre de marca.
- `slug`: slug único de marca.
- `brand_type`: tipo de marca (`vehicle`, `parts`, `both`).
- `country`: país asociado.
- `is_active`: marca activa/inactiva.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Category
- `id`: identificador interno.
- `name`: nombre de categoría.
- `slug`: slug único de categoría.
- `parent`: categoría padre (autorreferencia, opcional).
- `description`: descripción opcional.
- `sort_order`: orden de visualización.
- `is_active`: categoría activa/inactiva.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Condition
- `id`: identificador interno.
- `code`: código único de condición.
- `name`: nombre único de condición.
- `slug`: slug único de condición.
- `description`: descripción opcional.
- `is_active`: condición activa/inactiva.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### PartNumberType
- `id`: identificador interno.
- `code`: código único del tipo de referencia (normalizado en mayúsculas y sin símbolos).
- `name`: nombre visible del tipo.
- `sort_order`: orden de visualización.
- `is_active`: tipo activo/inactivo.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Product
- `id`: identificador interno.
- `supplier`: proveedor propietario del producto.
- `supplier_product_code`: código de proveedor (opcional).
- `sku`: referencia OEM principal única global (`Referencia (OEM)` en ES / `Reference (OEM)` en EN).
- `brand`: marca fabricante asociada a la referencia OEM principal (`Marca` en ES / `Brand` en EN), opcional.
- `slug`: slug único autogenerado desde `sku`.
- `title`: título del producto.
- `short_description`: descripción corta.
- `long_description`: descripción larga.
- `category`: categoría principal.
- `condition`: condición del producto.
- `publication_status`: estado editorial (`draft`, `review`, `published`).
- `published_at`: fecha/hora de publicación (opcional).
- `price_visibility_mode`: visibilidad de precio (`hidden`, `visible_info`).
- `last_known_price`: último precio conocido (opcional).
- `currency`: moneda (por defecto `EUR`).
- `unit_of_sale`: unidad de venta (por defecto `unit`).
- `quantity`: cantidad asociada al producto (entero, por defecto `1`).
- `unit_of_quantity`: unidad de esa cantidad (por defecto `Pcs`).
- `weight`: peso (opcional).
- `length`: largo (opcional).
- `width`: ancho (opcional).
- `height`: alto (opcional).
- `featured`: producto destacado.
- `is_active`: producto activo/inactivo.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### PartNumber
- `id`: identificador interno.
- `product`: producto al que pertenece la referencia.
- `brand`: marca asociada a la referencia (opcional).
- `number_raw`: referencia en formato origen.
- `number_normalized`: referencia normalizada para búsqueda.
- `part_number_type`: tipo de referencia (`FK` a `PartNumberType`).
- `is_primary`: referencia principal del producto.
- `notes`: notas opcionales.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Vehicle
- `id`: identificador interno.
- `vehicle_type`: tipo de vehículo (`car`, `motorcycle`, `truck`, `van`, `other`).
- `brand`: marca del vehículo.
- `model`: modelo del vehículo.
- `generation`: generación (opcional).
- `variant`: variante (opcional).
- `year_start`: año inicio (opcional).
- `year_end`: año fin (opcional).
- `engine_code`: código de motor (opcional).
- `fuel_type`: combustible (`gasoline`, `diesel`, `hybrid`, `electric`, `lpg`, `cng`, `other`).
- `displacement_cc`: cilindrada en cc (opcional).
- `power_hp`: potencia en hp (opcional).
- `power_kw`: potencia en kW (opcional).
- `notes`: notas técnicas (opcional).
- `is_active`: vehículo activo/inactivo.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### ProductVehicleFitment
- `id`: identificador interno.
- `product`: producto compatible.
- `vehicle`: vehículo compatible.
- `fitment_notes`: notas de compatibilidad (opcional).
- `source`: origen del dato (`supplier`, `import`, `manual`).
- `is_verified`: compatibilidad verificada.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### AttributeDefinition
- `id`: identificador interno.
- `name`: nombre del atributo.
- `slug`: slug único del atributo.
- `data_type`: tipo de dato (`text`, `number`, `boolean`).
- `unit`: unidad del atributo (opcional).
- `is_filterable`: usable como filtro en catálogo.
- `is_visible_on_product`: visible en ficha de producto.
- `allows_multiple_values`: admite múltiples valores por producto.
- `sort_order`: orden de visualización.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### ProductAttributeValue
- `id`: identificador interno.
- `product`: producto asociado.
- `attribute_definition`: definición del atributo.
- `value_text`: valor textual (opcional).
- `value_number`: valor numérico (opcional).
- `value_boolean`: valor booleano (opcional).
- `value_normalized`: valor normalizado para filtros/búsquedas.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### ProductImage
- `id`: identificador interno.
- `product`: producto asociado.
- `image`: imagen del producto.
- `alt_text`: texto alternativo (opcional).
- `sort_order`: orden de la imagen.
- `is_primary`: imagen principal.
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### Inquiry
- `id`: identificador interno.
- `reference_code`: código de referencia único.
- `user`: usuario registrado (opcional).
- `guest_name`: nombre de invitado (opcional si hay `user`; obligatorio si no hay `user`).
- `guest_email`: email de invitado (opcional si hay `user`; obligatorio si no hay `user`).
- `guest_phone`: teléfono de invitado (opcional).
- `company_name`: empresa (opcional).
- `tax_id`: identificador fiscal (opcional).
- `language`: idioma (`es`, `en`).
- `status`: estado de la consulta (`draft`, `submitted`, `in_review`, `supplier_pending`, `responded`, `accepted`, `rejected`, `closed`), por defecto `submitted`.
- `notes_from_customer`: notas del cliente.
- `internal_notes`: notas internas.
- `response_due_at`: fecha objetivo de respuesta (opcional).
- `supplier_feedback_at`: fecha de respuesta del proveedor (opcional).
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### InquiryItem
- `id`: identificador interno.
- `inquiry`: consulta asociada.
- `product`: producto solicitado.
- `requested_quantity`: cantidad solicitada (entero, por defecto `1`).
- `customer_note`: nota del cliente (opcional).
- `last_known_price_snapshot`: snapshot del último precio conocido (opcional).
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### SupplierImport
- `id`: identificador interno.
- `supplier`: proveedor de la importación.
- `uploaded_by`: usuario que subió el fichero (opcional).
- `original_file`: fichero original importado (opcional).
- `import_status`: estado (`pending`, `processing`, `completed`, `completed_with_errors`, `failed`).
- `total_rows`: total de filas leídas.
- `successful_rows`: filas procesadas correctamente.
- `failed_rows`: filas con error.
- `processing_notes`: notas del proceso (incluye advertencias/resumen).
- `started_at`: fecha/hora de inicio (opcional).
- `finished_at`: fecha/hora de fin (opcional).
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

### SupplierImportRow
- `id`: identificador interno.
- `supplier_import`: importación asociada.
- `row_number`: número de fila original.
- `raw_payload`: contenido crudo de la fila.
- `processing_status`: estado de fila (`pending`, `success`, `skipped`, `error`).
- `linked_product`: producto enlazado/creado (opcional).
- `error_message`: mensaje de error (opcional).
- `created_at`: fecha de creación.
- `updated_at`: fecha de actualización.

## Directrices clave para creación de producto
- No meter múltiples referencias en un campo de `Product`.
- No modelar compatibilidades complejas como texto libre en `Product`.
- Usar `PartNumber` y `ProductVehicleFitment` como entidades de relación fuertes.
- Mantener separada la identidad del producto, sus referencias y su compatibilidad vehicular.
- La identidad OEM del producto se captura en `sku` + `brand`.
- Al crear o actualizar un `Product`, el sistema sincroniza automáticamente `PART NUMBERS` para garantizar que exista una referencia primaria OEM:
  - `part_number_type = OEM`
  - `number_raw = sku`
  - `brand = brand` (campo de marca del producto)
  - `is_primary = True`
