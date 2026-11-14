# Publica el entorno de produccion local (scripts\serve_pro.ps1, puerto 8000) en un
# subdominio propio con un tunel con nombre de Cloudflare. Ver docs\DEMO_PRO.md.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\tunnel_pro.ps1 -Hostname demo.tudominio.com
# Antes, una sola vez:  cloudflared tunnel login   (elige el dominio en el navegador)
# (Solo ASCII: Windows PowerShell 5.1 lee los .ps1 sin BOM con la pagina de codigos local.)
param(
    [Parameter(Mandatory = $true)][string]$Hostname,
    [string]$Name = "alza-pro"
)
$ErrorActionPreference = "Stop"
$cf = Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { $cf = "cloudflared" }
$home_cf = Join-Path $env:USERPROFILE ".cloudflared"
if (-not (Test-Path (Join-Path $home_cf "cert.pem"))) {
    throw "Falta iniciar sesion: ejecuta '$cf tunnel login' y elige tu dominio."
}

function Get-Tunnel {
    $all = & $cf tunnel list --output json | ConvertFrom-Json
    return $all | Where-Object { $_.name -eq $Name } | Select-Object -First 1
}

$tunnel = Get-Tunnel
if (-not $tunnel) {
    & $cf tunnel create $Name
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el tunel $Name." }
    $tunnel = Get-Tunnel
}
$id = $tunnel.id
Write-Host "Tunel $Name ($id)"

# El subdominio apunta al tunel (crea o sustituye el CNAME en Cloudflare).
& $cf tunnel route dns --overwrite-dns $Name $Hostname
if ($LASTEXITCODE -ne 0) { throw "No se pudo apuntar $Hostname al tunel." }

$config = Join-Path $home_cf "$Name.yml"
$credentials = Join-Path $home_cf "$id.json"
@(
    "tunnel: $id",
    "credentials-file: $credentials",
    "ingress:",
    "  - hostname: $Hostname",
    "    service: http://127.0.0.1:8000",
    "  - service: http_status:404"
) | Set-Content -Path $config -Encoding ascii

Write-Host "Publicando https://$Hostname  ->  http://127.0.0.1:8000  (Ctrl+C para cerrar)"
& $cf tunnel --config $config run $Name
