# Arranca Alza en modo produccion en http://127.0.0.1:8000 para el tunel de Cloudflare.
# Lee .env.pro, aplica las migraciones, carga el catalogo (idempotente) y sirve con waitress.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\serve_pro.ps1
# (Solo ASCII: Windows PowerShell 5.1 lee los .ps1 sin BOM con la pagina de codigos local.)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$envFile = Join-Path $root ".env.pro"
if (-not (Test-Path $envFile)) { throw "Falta .env.pro: copia .env.pro.example y pon un SECRET_KEY." }
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), "Process")
    }
}
# SQLite relativo: se resuelve contra la carpeta del proyecto.
if ($env:DATABASE_URL -like "sqlite:///instance/*") {
    $file = Join-Path $root $env:DATABASE_URL.Substring(10)
    $env:DATABASE_URL = "sqlite:///" + $file.Replace([char]92, [char]47)
}
$venv = Join-Path $root ".venv\Scripts"
& "$venv\flask.exe" --app wsgi db upgrade
if ($LASTEXITCODE -ne 0) { throw "Las migraciones han fallado." }
& "$venv\flask.exe" --app wsgi seed all
if ($LASTEXITCODE -ne 0) { throw "La carga del catalogo ha fallado." }
Write-Host "Alza (produccion) en http://127.0.0.1:8000  -  Ctrl+C para parar"
& "$venv\waitress-serve.exe" --host 127.0.0.1 --port 8000 --threads 8 wsgi:app
