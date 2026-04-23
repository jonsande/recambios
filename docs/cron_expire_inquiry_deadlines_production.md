# Cron de caducidad automática de ofertas/pagos

## Objetivo

Programar la ejecución periódica de:

```bash
python src/manage.py expire_inquiry_deadlines
```

para aplicar automáticamente:

- caducidad de ofertas `sent` fuera de plazo (`SENT -> EXPIRED`)
- cancelación de pagos `pending` fuera de plazo (`PENDING -> CANCELLED`)
- envío de notificaciones de vencimiento (cliente/interno/proveedor según configuración)

## Archivos incluidos en el repositorio

- Script cron: `scripts/cron/expire_inquiry_deadlines.sh`
- Plantilla de crontab: `scripts/cron/expire_inquiry_deadlines.crontab.example`

El script ya incluye:

- lock con `flock` para evitar ejecuciones solapadas
- logging en archivo
- configuración por variables de entorno

## Variables configurables del script

Por defecto:

- `PROJECT_DIR`: raíz del proyecto (autodetectada desde la ruta del script)
- `PYTHON_BIN`: `${PROJECT_DIR}/.venv/bin/python`
- `MANAGE_PY_PATH`: `${PROJECT_DIR}/src/manage.py`
- `DJANGO_SETTINGS_MODULE_VALUE`: `config.settings.prod`
- `LOCK_FILE`: `/tmp/recambios_expire_inquiry_deadlines.lock`
- `LOG_FILE`: `${PROJECT_DIR}/tmp/logs/expire_inquiry_deadlines.log`

Puedes sobrescribirlas desde cron si tu despliegue usa otras rutas.

## Pasos de instalación en producción (cron)

1. Asegurar permisos de ejecución del script:

```bash
chmod +x /ruta/proyecto/scripts/cron/expire_inquiry_deadlines.sh
```

2. Probar ejecución manual con el mismo usuario que ejecutará cron:

```bash
cd /ruta/proyecto
./scripts/cron/expire_inquiry_deadlines.sh
```

3. Revisar log:

```bash
tail -n 100 /ruta/proyecto/tmp/logs/expire_inquiry_deadlines.log
```

4. Añadir tarea en crontab (cada 5 minutos):

```cron
*/5 * * * * PROJECT_DIR=/ruta/proyecto DJANGO_SETTINGS_MODULE_VALUE=config.settings.prod /bin/bash /ruta/proyecto/scripts/cron/expire_inquiry_deadlines.sh
```

También puedes partir de:

`scripts/cron/expire_inquiry_deadlines.crontab.example`

Para editar crontab:

```bash
crontab -e
```

5. Verificar que cron está cargado:

```bash
crontab -l
```

## Comportamiento esperado

- La caducidad no es instantánea: depende de la frecuencia del cron.
- Con `*/5 * * * *`, el desfase máximo típico es ~5 minutos.
- El comando es idempotente: puede ejecutarse repetidamente sin duplicar transiciones.
- Si una ejecución tarda más que el intervalo, el lock evita solapes y deja trazas de `Skip`.

## Verificación operativa recomendada

1. Crear en entorno de staging una oferta `sent` vencida y confirmar paso a `expired`.
2. Crear un pago `pending` vencido y confirmar paso a `cancelled`.
3. Confirmar recepción de emails esperados (cliente/interno/proveedor según checks).
4. Revisar logs durante al menos 24h.

## Troubleshooting

- No hay ejecuciones en log:
  - revisar `crontab -l`
  - confirmar usuario y PATH/venv correctos
- Error de permisos en log/lock:
  - revisar permisos de escritura sobre `tmp/logs` y `/tmp`
- El script no encuentra Python/manage.py:
  - ajustar `PROJECT_DIR`, `PYTHON_BIN`, `MANAGE_PY_PATH` en la línea de cron

## Cómo desactivar temporalmente

- comentar la línea en `crontab -e`
- o cambiar a una periodicidad más baja mientras se investiga
