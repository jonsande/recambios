# Roles y permisos v1 (admin interno)

## Resumen de roles

- `administrator`: rol canónico documentado. Autoridad real por `is_superuser`.
- `internal_staff`: usuario staff con grupo `internal_staff`.
- `restricted_supplier`: usuario staff con grupo `restricted_supplier` y asignación activa en `SupplierUserAssignment`.
- `registered_customer`: grupo base creado para fases futuras sin flujo público en esta fase.
- `guest`: usuario anónimo, solo documentado (sin implementación de auth pública en Fase 2).

## Reglas operativas en Fase 2

- El proveedor restringido solo puede trabajar sobre datos del proveedor asignado.
- El proveedor restringido solo puede editar objetos ligados a productos en estado `draft`.
- El proveedor restringido puede pasar producto de `draft` a `review`.
- El proveedor restringido no puede publicar ni establecer `published_at`.
- `internal_staff` y `administrator` pueden revisar y publicar.

## Alcance de permisos por grupo

### `internal_staff`
- Gestión completa (`add`, `change`, `delete`, `view`) de:
  - proveedores y asignaciones proveedor-usuario
  - catálogo (productos, referencias, atributos, imágenes, taxonomías)
  - vehículos y compatibilidades
  - importaciones y filas de importación
  - usuarios y grupos
- Permiso adicional: `catalog.can_publish_product`.

### `restricted_supplier`
- Permisos de edición sobre datos de contribución:
  - `Product`, `PartNumber`, `ProductAttributeValue`, `ProductImage`, `ProductVehicleFitment`
- Permisos de importación:
  - `SupplierImport`: `add`, `change`, `view` (con restricciones de admin por objeto)
  - `SupplierImportRow`: `view`
- Permisos de consulta para soporte de formularios/autocomplete:
  - `Supplier`, `Brand`, `Category`, `Condition`, `AttributeDefinition`, `Vehicle`
- Sin permiso `catalog.can_publish_product`.

## Nota de implementación

La matriz de grupos y permisos se sincroniza por migración de datos:
`apps.users.migrations.0001_role_groups`.
