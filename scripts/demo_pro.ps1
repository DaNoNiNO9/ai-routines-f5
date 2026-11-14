# Levanta la demo de Alza en produccion y la publica con un enlace temporal de Cloudflare.
#   1. Arranca scripts\serve_pro.ps1 (si no esta ya en marcha) en una ventana minimizada.
#   2. Abre el tunel rapido (https://...trycloudflare.com), sin dominio ni cuenta.
#   3. Copia la URL al portapapeles y la muestra en una ventana.
#   4. Al cerrar esta ventana (o Ctrl+C) cierra el tunel y, si lo arranco el, el servidor.
# Uso: doble clic en scripts\demo_pro.cmd
#   o:  powershell -ExecutionPolicy Bypass -File scripts\demo_pro.ps1 [-Quiet]   (-Quiet: sin ventana ni portapapeles)
# (Solo ASCII: Windows PowerShell 5.1 lee los .ps1 sin BOM con la pagina de codigos local.)
param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$cf = Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { throw "No encuentro cloudflared en $cf (ver docs\DEMO_PRO.md)." }
$health = "http://127.0.0.1:8000/health"

function Test-Server {
    try { return (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}

function Stop-Tree([int]$ProcessId) {
    # waitress y flask cuelgan del powershell del servidor: hay que cerrar el arbol entero.
    & taskkill.exe /PID $ProcessId /T /F *> $null
}

$server = $null
$tunnel = $null
try {
    if (Test-Server) {
        Write-Host "El servidor de produccion ya estaba en marcha en el puerto 8000."
    }
    else {
        Write-Host "Arrancando el servidor de produccion (migraciones y catalogo incluidos)..."
        $server = Start-Process powershell.exe -PassThru -WindowStyle Minimized -ArgumentList @(
            "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "scripts\serve_pro.ps1"))
        $deadline = (Get-Date).AddSeconds(120)
        while (-not (Test-Server)) {
            if ($server.HasExited) { throw "El servidor se ha cerrado al arrancar: revisa .env.pro y la ventana minimizada." }
            if ((Get-Date) -gt $deadline) { throw "El servidor no responde tras 2 minutos." }
            Start-Sleep -Seconds 1
        }
    }

    Write-Host "Abriendo el tunel de Cloudflare..."
    $log = Join-Path $env:TEMP "alza-tunel.log"
    $out = Join-Path $env:TEMP "alza-tunel.out"
    Remove-Item $log, $out -ErrorAction SilentlyContinue
    $tunnel = Start-Process $cf -PassThru -WindowStyle Hidden -RedirectStandardError $log -RedirectStandardOutput $out `
        -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000")
    $url = $null
    $deadline = (Get-Date).AddSeconds(60)
    while (-not $url) {
        if ($tunnel.HasExited) { throw "cloudflared se ha cerrado. Mira $log" }
        if ((Get-Date) -gt $deadline) { throw "Cloudflare no ha dado la URL en 1 minuto. Mira $log" }
        Start-Sleep -Milliseconds 500
        $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
        if ($text -and $text -match "Registered tunnel connection" -and $text -match "https://[a-z0-9-]+\.trycloudflare\.com") {
            $url = $Matches[0]
        }
    }

    if (-not $Quiet) { Set-Clipboard -Value $url }
    Write-Host ""
    Write-Host "  Alza (produccion) publicada en:  $url" -ForegroundColor Green
    if (-not $Quiet) { Write-Host "  La URL ya esta copiada en el portapapeles." -ForegroundColor Green }
    Write-Host "  Deja esta ventana abierta mientras se use. Ctrl+C o cerrarla = se acaba la demo."
    Write-Host ""
    if (-not $Quiet) {
        Add-Type -AssemblyName PresentationFramework
        [void][System.Windows.MessageBox]::Show(
            "La demo de Alza esta publicada en:`n`n$url`n`nYa esta copiada en el portapapeles: pegala donde quieras.`n`nFunciona mientras la ventana del script siga abierta.",
            "Alza - demo publicada", "OK", "Information")
    }
    Wait-Process -Id $tunnel.Id
}
finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Tree $tunnel.Id }
    if ($server -and -not $server.HasExited) { Stop-Tree $server.Id }
    Write-Host "Demo cerrada."
}
