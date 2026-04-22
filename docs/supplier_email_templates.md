# Plantillas de emails automáticos a proveedores

## Dónde se configuran

En Django admin, dentro de la ficha de cada proveedor:

- `Automatic Supplier Notifications`
- campos de plantilla de asunto y cuerpo para:
  - consulta enviada (`inquiry submitted`)
  - oferta enviada (`offer sent`)

Si una plantilla se deja vacía, el sistema usa la plantilla por defecto del proyecto.

## Sintaxis y variables

Las plantillas usan sintaxis de Django Template (`{{ ... }}`, `{% ... %}`).

### Contexto en plantilla de consulta (`inquiry submitted`)

- `inquiry`: objeto de consulta (por ejemplo, `reference_code`, `status`, `company_name`, etc.)
- `supplier`: objeto proveedor (por ejemplo, `name`, `code`, `contact_name`, etc.)
- `items`: líneas de la consulta del proveedor con `sku`, `title`, `quantity`

### Contexto en plantilla de oferta enviada (`offer sent`)

- `offer`: objeto oferta (por ejemplo, `reference_code`, `confirmed_total`, etc.)
- `inquiry`, `supplier`, `items`: igual que arriba

## Ejemplo (consulta al proveedor)

### Asunto

```django
Consulta {{ inquiry.reference_code }} | Proveedor {{ supplier.code }} | {{ items|length }} líneas
```

### Cuerpo

```django
Hola {{ supplier.contact_name|default:"equipo" }},

Se ha recibido una nueva consulta:
- Referencia: {{ inquiry.reference_code }}
- Estado: {{ inquiry.get_status_display }}
- Empresa cliente: {{ inquiry.company_name|default:"N/D" }}

Piezas solicitadas:
{% for item in items %}
- {{ item.sku }} | {{ item.title }} | Cantidad: {{ item.quantity }}
{% empty %}
- No hay líneas en la consulta.
{% endfor %}

Por favor, confirmad disponibilidad y precio final.
```
