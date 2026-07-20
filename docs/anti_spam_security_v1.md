# Plan de protección anti-spam y abuso — V1

**Estado:** pendiente de implementación  
**Fecha de decisión:** 20 de julio de 2026  
**Revisión prevista:** semana del 27 de julio de 2026  
**Ámbito:** formulario público de solicitud de ofertas e inicio de Stripe Checkout

## Contexto

La web todavía no está en producción. El negocio será inicialmente pequeño y estará gestionado por una sola persona, por lo que una solicitud automática no solo consume recursos técnicos: también puede generar trabajo comercial manual.

La prioridad para la V1 es disponer de una protección suficiente antes del lanzamiento sin construir un sistema antifraude complejo ni introducir mantenimiento innecesario.

Ningún CAPTCHA demuestra por sí solo que una persona sea humana. La estrategia será combinar varias defensas pequeñas y mantenerlas configurables.

## Decisión

Implementar antes de producción una protección sencilla por capas:

1. Cloudflare Turnstile en modo `Managed` en el envío final de solicitudes de oferta.
2. Validación del token de Turnstile en el servidor antes de crear registros.
3. Un campo honeypot accesible en el mismo formulario.
4. Limitación de tasa para solicitudes de oferta.
5. Limitación de tasa independiente para iniciar Stripe Checkout.
6. Registro básico de verificaciones fallidas y límites excedidos.
7. Mantener las defensas propias del flujo de pago: token de oferta, caducidad, reutilización/idempotencia de Checkout y firma del webhook de Stripe.

No se añadirá CAPTCHA de forma general a la pasarela de pago ni a los webhooks.

## Alcance funcional de la V1

### Envío de solicitudes de oferta

El `POST` que registra una solicitud deberá superar:

- protección CSRF de Django;
- honeypot vacío;
- comprobación de Turnstile válida en el backend;
- límite aproximado inicial de **5 solicitudes por hora e IP**.

El límite definitivo debe quedar en configuración para poder ajustarlo sin modificar la vista. Conviene priorizar límites de ráfaga frente a límites diarios muy bajos, ya que talleres, empresas y redes móviles pueden compartir una dirección IP.

Turnstile deberá:

- utilizar el modo `Managed`, no invisible, inicialmente;
- comprobarse mediante `Siteverify` en el backend;
- validar al menos el resultado, `hostname` y `action` esperados;
- usar claves distintas para pruebas y producción;
- almacenar la clave secreta únicamente en variables de entorno;
- mostrar un error comprensible y accesible, permitiendo reintentar;
- definir explícitamente la conducta ante indisponibilidad del proveedor.

Decisión inicial sugerida ante una caída de Turnstile: permitir la solicitud solamente si las demás comprobaciones son correctas, registrándola como incidencia para revisión. Esta conducta debe revisarse durante la implementación y quedar configurable.

El honeypot debe quedar fuera de la navegación normal y no confundir a lectores de pantalla, autocompletado o gestores de contraseñas.

### Inicio de Stripe Checkout

El `POST` que crea o reutiliza una sesión de Stripe deberá tener:

- límite aproximado inicial de **10 intentos por hora e IP**;
- límite adicional por token/oferta;
- reutilización o idempotencia de sesiones;
- mensajes que no revelen información útil para enumerar ofertas;
- registro de ráfagas y errores.

No se exigirá Turnstile normalmente en este paso. Si en el futuro aparece abuso real, se podrá exigir únicamente después de superar un umbral de riesgo.

### Webhook de Stripe

El webhook no llevará CAPTCHA ni controles dependientes de navegador. Mantendrá:

- validación estricta de la firma de Stripe;
- procesamiento idempotente;
- rechazo de eventos no válidos;
- registro suficiente para diagnosticar errores.

## Arquitectura y configuración

Los límites y las claves deberán proceder de settings/variables de entorno. Nombres orientativos:

```text
TURNSTILE_ENABLED
TURNSTILE_SITE_KEY
TURNSTILE_SECRET_KEY
TURNSTILE_EXPECTED_HOSTNAME
TURNSTILE_FAIL_OPEN
INQUIRY_RATE_LIMIT
CHECKOUT_RATE_LIMIT
```

La obtención de la IP real debe confiar únicamente en el proxy configurado por la aplicación. No se debe aceptar ciegamente cualquier cabecera `X-Forwarded-For`, porque un cliente podría falsificarla para eludir los límites.

Antes de decidir el almacenamiento de contadores se revisará el despliegue:

- si ya existe Redis, usar caché compartida con operaciones atómicas;
- si no existe Redis y habrá un único proceso web, una solución local sencilla puede ser aceptable al comienzo;
- si habrá varios workers, valorar el límite en Redis, Nginx o Cloudflare;
- no introducir Redis solo por esta función sin comparar antes el coste operativo.

## Fuera de alcance en la V1

Se aplaza hasta que el tráfico o el abuso real lo justifiquen:

- puntuación de riesgo propia;
- límites combinados complejos por IP, sesión, email, país o ASN;
- CAPTCHA condicional avanzado;
- confirmación obligatoria de solicitudes por email;
- análisis detallado de tiempos y comportamiento;
- panel de métricas propio;
- reglas WAF avanzadas;
- servicios especializados de fraude;
- CAPTCHA en aceptación/rechazo de ofertas o edición de direcciones.

El tiempo de envío puede registrarse en el futuro como señal, pero no será motivo de bloqueo en la V1 por el riesgo de falsos positivos con autocompletado y usuarios legítimos rápidos.

## Plan de implementación

### Fase 1 — Descubrimiento y diseño

- Identificar todas las rutas `POST` afectadas.
- Revisar cómo se desplegarán proxy, workers y caché.
- Elegir dónde residirá el rate limiting.
- Crear el widget y las credenciales de Turnstile para desarrollo y producción.
- Definir mensajes, eventos de log y comportamiento ante caída de Turnstile.

### Fase 2 — Solicitudes de oferta

- Crear un servicio reutilizable de validación de Turnstile con timeout.
- Integrarlo en el formulario/vista antes de abrir la transacción de creación.
- Añadir el honeypot con tratamiento accesible.
- Aplicar el límite por IP.
- Incorporar configuración, traducciones y registros.

### Fase 3 — Checkout

- Aplicar límites por IP y oferta al inicio de Checkout.
- Confirmar que la creación/reutilización sea idempotente.
- Revisar que los errores no permitan enumerar tokens.
- Confirmar que el webhook conserve su flujo independiente y firmado.

### Fase 4 — Pruebas y despliegue

- Probar token correcto, ausente, inválido, caducado y reutilizado.
- Probar indisponibilidad y timeout de Turnstile.
- Probar honeypot relleno.
- Probar límites sin crear registros ni sesiones remotas adicionales.
- Probar usuarios autenticados y anónimos, teclado y mensajes de error.
- Probar IP directa y cabeceras del proxy de producción.
- Actualizar política de privacidad y documentación de despliegue.
- Ejecutar Ruff, pruebas relevantes, `manage.py check` y las verificaciones del repositorio.

## Criterios de aceptación

La tarea se considerará terminada cuando:

- una solicitud legítima pueda enviarse con Turnstile activo;
- una respuesta de Turnstile falsa o reutilizada no cree solicitudes;
- el honeypot bloquee bots básicos sin aparecer para usuarios ni tecnologías de asistencia;
- superar el límite no cree registros y devuelva una respuesta clara;
- el límite de Checkout no afecte al webhook;
- los límites puedan ajustarse mediante configuración;
- las claves secretas no aparezcan en plantillas, logs ni repositorio;
- las pruebas cubran los caminos permitidos, rechazados y de fallo del proveedor;
- la política de privacidad refleje el uso de Turnstile;
- se haya validado el comportamiento detrás del proxy real.

## Estimación

Estimación orientativa para una implementación cuidada:

| Bloque | Tiempo |
| --- | ---: |
| Turnstile y validación backend | 3–5 h |
| Honeypot accesible | 1–2 h |
| Rate limiting de solicitud y Checkout | 4–7 h |
| Resolución de IP detrás del proxy | 1–2 h |
| Pruebas, accesibilidad y traducciones | 3–5 h |
| Configuración y documentación | 1–2 h |
| **Total aproximado** | **13–23 h** |

La previsión es de dos o tres jornadas. No debe retrasarse el lanzamiento para construir las funciones aplazadas si la protección V1 ya está validada.

## Seguimiento tras el lanzamiento

Durante las primeras semanas se revisarán:

- solicitudes bloqueadas por Turnstile;
- límites excedidos;
- falsos positivos comunicados por clientes;
- frecuencia de timeouts del proveedor;
- intentos repetidos de iniciar Checkout;
- volumen real de spam que llegue a administración.

Solo se ampliará la estrategia ante evidencia concreta. La primera ampliación probable, si llegan solicitudes con emails falsos, sería la confirmación por correo. Si aparecen ráfagas distribuidas, se valorarían límites combinados y una caché compartida.

## Referencias técnicas

- [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/)
- [Validación de tokens en el servidor](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)
- [Planes de Turnstile](https://developers.cloudflare.com/turnstile/plans/)
- [Tipos de widget](https://developers.cloudflare.com/turnstile/concepts/widget/)

