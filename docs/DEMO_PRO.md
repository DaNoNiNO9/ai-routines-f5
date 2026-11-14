# Enseñar Alza en producción por un túnel de Cloudflare

Para que alguien de fuera pruebe Alza tal como funcionará en producción, desde este ordenador y con un subdominio propio (por ejemplo `demo.alza.fit`), sin abrir puertos ni contratar un servidor.

```
navegador ──https──▶ Cloudflare ──túnel──▶ cloudflared (este PC) ──▶ waitress 127.0.0.1:8000 (ALZA_ENV=production)
```

## Qué es «producción» aquí

`scripts/serve_pro.ps1` arranca la app con `ALZA_ENV=production` y la configuración de `.env.pro` (fuera de git; plantilla en `.env.pro.example`):

| Ajuste | Valor | Por qué |
|---|---|---|
| Servidor | waitress, 8 hilos, solo en 127.0.0.1 | Solo se llega a él por el túnel |
| Base de datos | `instance/alza-pro.db`, aparte de la de desarrollo | Lo que hagan los probadores no se mezcla con tus pruebas |
| Seguridad | cookies `Secure`, HSTS, CSP, sin rutas de depuración | Igual que en el despliegue real |
| `BEHIND_PROXY=true` | Fiarse de `X-Forwarded-*` de un salto | Enlaces con `https://` y el dominio público; límite de intentos por IP real |
| `PAYWALL_ENABLED=false` | Todo abierto | Quien lo pruebe ve también lo de Pro. Con el muro activo, producción exige Stripe real |
| Correo | SMTP a `localhost` | No hay servidor de correo: «He olvidado mi contraseña» avisa de que no pudo enviarlo |

Cada arranque aplica las migraciones y carga el catálogo (las dos cosas son idempotentes).

## Pasos

Una sola vez:

1. `cloudflared` ya está en `%LOCALAPPDATA%\cloudflared\cloudflared.exe` (versión 2026.11.0, suma SHA-256 comprobada con la publicada).
2. Inicia sesión y elige el dominio (abre el navegador):

   ```powershell
   & "$env:LOCALAPPDATA\cloudflared\cloudflared.exe" tunnel login
   ```

   El dominio tiene que estar en tu cuenta de Cloudflare (sus DNS gestionados por Cloudflare).

Cada vez que quieras enseñarlo, en dos terminales:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\serve_pro.ps1
powershell -ExecutionPolicy Bypass -File scripts\tunnel_pro.ps1 -Hostname demo.alza.fit
```

`tunnel_pro.ps1` crea el túnel `alza-pro` la primera vez, apunta el subdominio a él (CNAME en Cloudflare) y lo publica. Al cerrar las terminales, el subdominio deja de responder (Cloudflare da un error 1033) hasta la próxima vez.

## Cuidado

- Mientras el túnel está abierto, cualquiera con el enlace puede registrarse. Para limitarlo a tu colega, añade en Cloudflare Zero Trust › Access una aplicación para el subdominio con su correo (código de un solo uso), sin tocar nada de la app.
- Los datos que meta son datos de salud reales: la base `instance/alza-pro.db` está en este PC. Bórrala al terminar las pruebas si no la necesitas.
- Si cambias el código, para y vuelve a lanzar `serve_pro.ps1`.
