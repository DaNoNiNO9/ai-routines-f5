# Privacidad: notas técnicas para el abogado y para producción

Acompaña al borrador de política de privacidad (`/privacidad`, plantilla `app/templates/privacy/policy.html`). Aquí está **lo que hace el código de verdad**, para que la política diga lo mismo y para que quien despliegue sepa qué tiene que cumplir. Última revisión: 2026-11-12.

## 1. Consentimiento para datos de salud (art. 9.2.a RGPD)

| Qué | Cómo |
|---|---|
| Explícito y aparte | En el registro hay dos casillas distintas: el aviso de que Alza no sustituye a un profesional y el consentimiento para datos de salud. Ninguna viene marcada. Sin la segunda no se crea la cuenta. |
| Qué cubre | Peso, medidas, sueño, comida, entrenos, molestias y lesiones, y el tipo de dieta (halal o kosher pueden revelar creencias religiosas). |
| Prueba | `users.health_consent_at` (fecha y hora UTC) y `users.health_consent_version` (versión del texto, hoy `2026-11-12`, en `app/services/privacy.py`). Sale también en el CSV `cuenta.csv` de la exportación. |
| Cuentas anteriores | No tienen consentimiento registrado: la próxima vez que entran se les pide en `/consentimiento` antes de ver nada con datos de salud. |
| Sin consentimiento | Solo se abren cuenta, exportación, borrado, suscripción, precios, privacidad y páginas públicas. Todo lo demás redirige a `/consentimiento`. La lista está en `app/blueprints/privacy/routes.py` (`OPEN_WITHOUT_CONSENT`). |
| Retirarlo | Cuenta › Tus datos de salud › Retirar (pide la contraseña). Se borran **en el momento** cuestionario, perfiles, planes, rutinas, sesiones y series, pesajes, medidas, comida, actividad, ajustes y material. La cuenta y la suscripción siguen. Además la página siguiente borra lo guardado para usar la app sin red (`?limpiar=1`, igual que al cerrar sesión). |
| Cambiar el texto | Si cambia lo que se consiente, sube `CONSENT_VERSION`. Hoy no se vuelve a pedir automáticamente a quien ya dio una versión anterior: decidir con el abogado si hace falta. |

## 2. Qué sale de la app y hacia dónde

Revisado en el código el 2026-11-12. No hay más llamadas salientes que estas:

| Destino | Cuándo | Qué recibe | Datos de salud |
|---|---|---|---|
| Stripe (Stripe Payments Europe, Irlanda) | Al pagar, cancelar, desistir o abrir el portal | Correo, id interno de la cuenta, plan elegido y días de prueba | **No** (lo comprueba `test_stripe_never_receives_health_data`) |
| Proveedor de correo (SMTP, por elegir) | Recuperar la contraseña | Correo y el enlace | No |
| Open Food Facts (Francia) | Buscar un alimento o un código de barras | Solo el texto buscado o el código, desde el servidor, con el agente `Alza - https://alza.fit` | No; ni correo, ni id, ni IP de la persona (lo comprueba `test_open_food_facts_only_gets_the_search_text`) |

- **Sin analítica ni scripts de terceros.** La política de seguridad de contenidos (CSP) solo deja cargar scripts propios; las fuentes, iconos, gráficas y el lector de códigos (ZXing) se sirven desde el propio servidor. Un test recorre todas las plantillas buscando scripts externos y rastreadores.
- **Vídeos de ejercicios (wger)**: se descargaron una vez y se sirven desde el servidor; el navegador no llama a wger.
- **Registros del servidor**: guardan fecha, método, ruta **sin la parte de búsqueda** (así no quedan los alimentos buscados), código de respuesta e id de la cuenta. Se rotan cada noche y se conservan 30 días (`LOG_RETENTION_DAYS`).

## 3. Lo que tiene que cumplir el alojamiento (pendiente de elegir)

La política promete cosas que dependen de dónde se despliegue. Antes de abrir al público:

1. **Servidores y base de datos en la UE.** Proveedores con región europea y contrato de encargado del tratamiento (art. 28): por ejemplo Hetzner (Alemania, Finlandia), OVHcloud o Scaleway (Francia), o la región de Fráncfort, París o Madrid de un proveedor grande. Rellenar `[nombre]` y `[país]` en la política.
2. **Copias de seguridad cifradas, en la UE y que caduquen solas a los 30 días** como mucho (rotación diaria). Así un borrado desaparece también de las copias en ese plazo, que es lo que dice la política. Si se elige otro plazo, cambiar el `[30]`.
3. **Restaurar una copia**: justo después, ejecutar `flask privacy reapply-erasures`. Cada borrado de cuenta y cada retirada del consentimiento deja una fila en `erasure_log` con solo el número de cuenta, qué se borró y cuándo (ni correo ni nombre ni datos); el comando vuelve a borrar lo que la copia ha resucitado. Respeta lo posterior: no toca una cuenta creada después con el mismo número ni los datos dados con un consentimiento nuevo.
4. **Cada día**, `flask privacy purge-erasures` (cron o tarea programada): olvida los registros de más de `ERASURE_LOG_DAYS` (35), que sobreviven a cualquier copia que se pueda restaurar. Si las copias duran más de 30 días, subir ese valor.
5. **Correo**: proveedor con servidores en la UE o con cláusulas tipo. Rellenar `[nombre]`.
6. **HTTPS obligatorio**: la app ya envía HSTS en producción. La cámara para escanear solo funciona con HTTPS.

## 4. Borrado de la cuenta

- Cuenta › Borrar la cuenta (contraseña y escribir BORRAR). Si hay suscripción activa, primero se cancela en Stripe; si falla, no se borra nada.
- Se borra todo lo de la persona en la base de datos en el momento, por cascada, y se pide al navegador que borre lo guardado para usar la app sin red.
- Lo que queda fuera de la base: las copias de seguridad (hasta que caducan) y lo que Stripe conserva por obligación fiscal (facturas, que también debe conservar el responsable: 6 años por el Código de Comercio, 4 por la normativa tributaria, a confirmar por el abogado).

## 5. Para revisar con el abogado

- Rellenar los corchetes de la política: responsable, NIF, dirección, contacto, DPD si se designa, alojamiento, correo, plazo de copias y de facturas.
- Si hace falta **evaluación de impacto (EIPD, art. 35)**: se tratan datos de salud de forma sistemática; probablemente sí.
- **Registro de actividades de tratamiento** (art. 30).
- Si el tipo de dieta debe ir con un consentimiento propio, aparte del de salud (hoy van juntos, mencionados expresamente).
- Si hay que pedir de nuevo el consentimiento cuando cambie la versión del texto.
- Edad mínima: hoy 18 años (la app no genera planes a menores).
- La política está solo en castellano; la interfaz en inglés lo avisa.
