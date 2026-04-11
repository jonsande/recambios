
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

### Propuesta inicial de campos por entidad

#### Supplier
- id                        : Identificador interno único del proveedor.
- name                      : Nombre comercial oficial del proveedor.
- slug                      : Versión del nombre preparada para URL o identificadores legibles.
- code                      : Código interno corto del proveedor, útil para integraciones o gestión interna.
- country                   : País del proveedor.
- website                   : Página web oficial del proveedor.
- contact_name              : Nombre de la persona de contacto principal.
- contact_email             : Email de contacto principal del proveedor.
- contact_phone             : Teléfono de contacto principal del proveedor.
- is_active                 : Indica si el proveedor está activo en el sistema.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Brand
- id                        : Identificador interno único de la marca.
- name                      : Nombre canónico de la marca.
- slug                      : Versión del nombre preparada para URL o filtros legibles.
- brand_type                : Tipo de marca; por ejemplo, marca de vehículo, fabricante de recambio o ambas.
- country                   : País asociado a la marca, si se desea almacenar.
- is_active                 : Indica si la marca está activa y disponible para uso en catálogo.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Category
- id                        : Identificador interno único de la categoría.
- name                      : Nombre visible de la categoría.
- slug                      : Versión del nombre preparada para URL amigables.
- parent                    : Categoría padre, para construir jerarquías de categorías.
- description               : Texto descriptivo opcional de la categoría.
- sort_order                : Orden numérico para controlar cómo se listan las categorías.
- is_active                 : Indica si la categoría está activa y visible en el sistema.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Condition
- id                        : Identificador interno único de la condición del producto.
- code                      : Código interno estable de la condición; por ejemplo `new`, `used`, `remanufactured`.
- name                      : Nombre visible de la condición; por ejemplo “Nuevo” o “Usado”.
- slug                      : Versión preparada para URLs, filtros o uso interno legible.
- description               : Explicación opcional de lo que significa esa condición.
- is_active                 : Indica si esa condición puede seguir utilizándose en el catálogo.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Product
- id                        : Identificador interno único del producto (interno al sistema). Lo genera el sistema. Es único. No sirve para relaciones internas entre tablas. No debe tener significado comercial. Le importa al sistema, no al usuario.
- supplier                  : Proveedor al que pertenece el producto.
- supplier_product_code     : Código con el que el proveedor identifica internamente ese producto.
- sku                       : Código interno de tu tienda.
- slug                      : Etiqueta para URL amigables.
- title                     : Nombre comercial visible.
- short_description         : Descripción breve para listados, tarjetas o resúmenes.
- long_description          : Descripción detallada del producto, con más contexto técnico o comercial.
- brand                     : Marca principal del producto, por ejemplo Valeo, Bosch, BMW.
- category                  : Categoría principal del producto.
- condition                 : Estado o condición del producto; por ejemplo nuevo, usado, reacondicionado.
- publication_status        : Estado editorial del producto; por ejemplo borrador, pendiente de revisión o publicado.
- published_at              : Fecha y hora en que el producto se publica realmente en la web.
- price_visibility_mode     : Define si el producto muestra precio visible o si obliga a consultar precio y plazo.
- last_known_price          : Último precio conocido del producto; no implica precio final garantizado.
- currency                  : Moneda del precio almacenado; por ejemplo EUR.
- unit_of_sale              : Unidad de venta; por ejemplo unidad, juego, kit, pareja.
- weight                    : Peso del producto, útil para logística o información técnica.
- length                    : Longitud del producto o embalaje, si se desea gestionar.
- width                     : Anchura del producto o embalaje.
- height                    : Altura del producto o embalaje.
- featured                  : Indica si el producto debe destacarse en home, categorías u otras zonas.
- is_active                 : Indica si el producto está activo en el sistema.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### PartNumber
- id                        : Identificador interno único de la referencia.
- product                   : Producto al que pertenece esta referencia.
- brand                     : Marca asociada a esa referencia concreta.
- number_raw                : Referencia tal como aparece en origen, sin normalizar.
- number_normalized         : Referencia transformada para facilitar búsquedas robustas.
- part_number_type          : Tipo de referencia; por ejemplo interna, OE, OEM, equivalente o antigua.
- is_primary                : Indica si esta es la referencia principal del producto.
- notes                     : Observaciones opcionales sobre la referencia.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Vehicle
- id                        : Identificador interno único del vehículo o configuración de vehículo.
- vehicle_type              : Tipo de vehículo; por ejemplo coche, moto, camión, furgoneta.
- brand                     : Marca del vehículo.
- model                     : Modelo del vehículo.
- generation                : Generación o serie del modelo, si aplica.
- variant                   : Variante o versión concreta del vehículo.
- year_start                : Año desde el que aplica esa configuración de vehículo.
- year_end                  : Año hasta el que aplica esa configuración de vehículo.
- engine_code               : Código de motor, cuando sea relevante.
- fuel_type                 : Tipo de combustible; por ejemplo gasolina, diésel, híbrido.
- displacement_cc           : Cilindrada en centímetros cúbicos.
- power_hp                  : Potencia en caballos.
- power_kw                  : Potencia en kilovatios.
- notes                     : Observaciones técnicas o aclaraciones sobre la configuración del vehículo.
- is_active                 : Indica si esta configuración de vehículo sigue activa para el catálogo.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### ProductVehicleFitment
- id                        : Identificador interno único de la relación de compatibilidad.
- product                   : Producto compatible.
- vehicle                   : Vehículo o configuración de vehículo compatible.
- fitment_notes             : Notas específicas sobre la compatibilidad.
- source                    : Fuente del dato de compatibilidad; por ejemplo proveedor, importación o revisión manual.
- is_verified               : Indica si la compatibilidad ha sido verificada manualmente o se considera fiable.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### AttributeDefinition
- id                        : Identificador interno único de la definición de atributo.
- name                      : Nombre visible del atributo; por ejemplo voltaje, color, lado de montaje.
- slug                      : Versión del nombre preparada para uso interno, filtros o URLs técnicas.
- data_type                 : Tipo de dato esperado; por ejemplo texto, número o booleano.
- unit                      : Unidad asociada al atributo, si aplica; por ejemplo V, mm, kg.
- is_filterable             : Indica si este atributo se puede usar como filtro en el catálogo.
- is_visible_on_product     : Indica si debe mostrarse en la ficha pública del producto.
- allows_multiple_values    : Indica si un producto puede tener más de un valor para ese atributo.
- sort_order                : Orden de visualización del atributo.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### ProductAttributeValue
- id                        : Identificador interno único del valor de atributo.
- product                   : Producto al que pertenece este valor.
- attribute_definition      : Definición del atributo al que corresponde este valor.
- value_text                : Valor textual del atributo, cuando el tipo de dato es texto.
- value_number              : Valor numérico del atributo, cuando el tipo de dato es número.
- value_boolean             : Valor booleano del atributo, cuando el tipo de dato es sí/no.
- value_normalized          : Versión normalizada del valor, útil para búsquedas o filtros consistentes.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### ProductImage
- id                        : Identificador interno único de la imagen.
- product                   : Producto al que pertenece la imagen.
- image                     : Archivo o ruta de la imagen.
- alt_text                  : Texto alternativo descriptivo para accesibilidad.
- sort_order                : Orden de aparición de la imagen en galerías o listados.
- is_primary                : Indica si esta es la imagen principal del producto.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### Inquiry / QuoteRequest
- id                        : Identificador interno único de la solicitud.
- reference_code            : Código de referencia visible para localizar la solicitud fácilmente.
- user                      : Usuario registrado que hizo la solicitud, si existe.
- guest_email               : Email del solicitante cuando hace la solicitud como invitado.
- guest_name                : Nombre del solicitante invitado.
- guest_phone               : Teléfono del solicitante invitado.
- company_name              : Nombre de la empresa, si el solicitante actúa como profesional o empresa.
- tax_id                    : Identificación fiscal, si se desea almacenar.
- language                  : Idioma en el que se ha realizado la solicitud.
- status                    : Estado actual de la solicitud; por ejemplo enviada, en revisión o respondida.
- notes_from_customer       : Observaciones aportadas por el cliente.
- internal_notes            : Notas internas del equipo, no visibles para el cliente.
- created_at                : Fecha y hora de creación de la solicitud.
- updated_at                : Fecha y hora de la última modificación de la solicitud.
- response_due_at           : Fecha objetivo o límite interna para responder a la solicitud.
- supplier_feedback_at      : Fecha y hora en que se recibió respuesta o confirmación del proveedor.

#### InquiryItem / QuoteRequestItem
- id                        : Identificador interno único de la línea de solicitud.
- inquiry                   : Solicitud a la que pertenece esta línea.
- product                   : Producto solicitado.
- requested_quantity        : Cantidad solicitada de ese producto.
- customer_note             : Nota específica del cliente para esa línea concreta.
- last_known_price_snapshot : Último precio conocido copiado en el momento de la solicitud, a modo informativo.
- created_at                : Fecha y hora de creación del registro.
- updated_at                : Fecha y hora de la última modificación del registro.

#### SupplierImport
- id                        : Identificador interno único de la importación.
- supplier                  : Proveedor al que pertenece la importación.
- uploaded_by               : Usuario que subió o lanzó la importación.
- original_file             : Archivo original importado.
- import_status             : Estado general de la importación; por ejemplo pendiente, procesando, completada o con errores.
- total_rows                : Número total de filas detectadas en el archivo.
- successful_rows           : Número de filas procesadas correctamente.
- failed_rows               : Número de filas que fallaron.
- started_at                : Fecha y hora de inicio del proceso de importación.
- finished_at               : Fecha y hora de finalización del proceso de importación.
- created_at                : Fecha y hora de creación del registro de importación.
- updated_at                : Fecha y hora de la última modificación del registro de importación.

#### SupplierImportRow
- id                        : Identificador interno único de la fila importada.
- supplier_import           : Importación a la que pertenece esta fila.
- row_number                : Número de fila dentro del archivo original.
- raw_payload               : Datos originales de la fila antes de transformarse.
- processing_status         : Estado del procesamiento de esta fila; por ejemplo correcta, omitida o con error.
- linked_product            : Producto enlazado o creado a partir de esta fila, si existe.
- error_message             : Mensaje de error asociado a la fila, si falló el procesamiento.
- created_at                : Fecha y hora de creación del registro.


==========================================

### Directrices clave para la creación de productos

* nunca meter referencias múltiples en un solo campo de `Product`
* nunca meter compatibilidades complejas en texto libre dentro de `Product`
* usar `PartNumber` y `ProductVehicleFitment` como tablas fuertes desde el principio
