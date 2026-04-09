# AGENTS.md

## Project overview
Este repositorio contiene una tienda online de recambios de coches construida con Django.
El objetivo es priorizar robustez, claridad, mantenibilidad y escalabilidad.

## Core principles
- Haz cambios pequeños, trazables y fáciles de revisar.
- No mezcles refactor y nueva funcionalidad en el mismo cambio salvo necesidad clara.
- Prioriza legibilidad y dominio correcto antes que abstracciones prematuras.
- Mantén separadas las responsabilidades entre catálogo, compatibilidades de vehículos, carrito, pedidos y checkout.

## Architecture rules
- El código de aplicación vive en `src/apps/`.
- La configuración Django vive en `src/config/`.
- La lógica compartida debe ir en `src/apps/common/` solo si realmente es reutilizable.
- Evita dependencias circulares entre apps.
- Las compatibilidades de vehículos deben modelarse con relaciones explícitas, no con campos de texto libres en `Product`.
- Las referencias OEM y equivalentes deben modelarse de forma separada del producto principal.

## Coding rules
- Escribe código Python claro, con nombres explícitos.
- Prefiere class-based models y function-based helpers simples.
- No introduzcas complejidad innecesaria.
- Añade type hints cuando mejoren claridad.
- Mantén imports ordenados.
- Evita comentarios obvios; comenta solo decisiones no triviales.

## Django conventions
- Usa un modelo por responsabilidad clara.
- Añade `verbose_name` y `verbose_name_plural` cuando ayude al admin.
- Define `__str__` útil en todos los modelos.
- Añade índices a campos de búsqueda frecuentes.
- Usa `select_related` y `prefetch_related` cuando la consulta lo requiera.
- Mantén la lógica de negocio fuera de las plantillas.
- Usa formularios, servicios o helpers antes de meter demasiada lógica en vistas.

## Tests and validation
Antes de dar una tarea por terminada:
- ejecuta lint
- ejecuta tests relevantes
- verifica migraciones
- revisa imports y nombres
- resume qué cambió y qué queda pendiente

## Commands
- Instalar dependencias: `pip install -r requirements/dev.txt`
- Ejecutar servidor: `python src/manage.py runserver`
- Crear migraciones: `python src/manage.py makemigrations`
- Aplicar migraciones: `python src/manage.py migrate`
- Ejecutar tests: `pytest`
- Lint: `ruff check .`
- Formato: `ruff format .`

## Done means
Un cambio se considera completo cuando:
1. el código está implementado
2. las migraciones son coherentes
3. los tests relevantes pasan
4. no rompe convenciones del proyecto
5. se documenta cualquier decisión importante

## Interaction style
Cuando la tarea sea grande:
1. inspecciona primero el contexto
2. propón un plan breve
3. implementa por pasos
4. valida antes de cerrar

Cuando falte información importante, indica la suposición adoptada y sigue con la opción más segura.