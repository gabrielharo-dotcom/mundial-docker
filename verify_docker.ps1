$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$nativeDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
$linuxPath = $null
if (-not $nativeDocker) {
  $windowsPath = $PSScriptRoot.Replace('\','/')
  $linuxPath = (& wsl -d Ubuntu-24.04 -u root --exec wslpath -a $windowsPath).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Docker no está disponible en Windows ni en Ubuntu-24.04' }
}
function Invoke-LabDocker {
  if ($nativeDocker) { & docker @args }
  else { & wsl -d Ubuntu-24.04 -u root --cd $linuxPath -- docker @args }
  if ($LASTEXITCODE -ne 0) { throw 'Falló Docker; revisar el registro' }
}
New-Item -ItemType Directory -Force evidence | Out-Null
Start-Transcript -Path evidence/docker-verification.txt -Force
try {
  Invoke-LabDocker version
  Invoke-LabDocker compose config
  & (Join-Path $PSScriptRoot 'DOCKER_LAB.ps1') -Action up -Replicas 3
  Invoke-LabDocker compose exec -T gateway nginx -s reload
  Start-Sleep -Seconds 6
  Invoke-LabDocker compose ps
  1..30 | ForEach-Object { (Invoke-RestMethod http://127.0.0.1:8080/health).instance } | Group-Object | Select-Object Name,Count
  python stress.py --out evidence/stress-docker.json
  if ($LASTEXITCODE -ne 0) { throw 'Fallo del generador de carga' }
  $results = Get-Content evidence/stress-docker.json -Raw | ConvertFrom-Json
  if (($results | Measure-Object errors -Sum).Sum -gt 0) { throw 'Hubo errores HTTP en la prueba de carga; revisar JSON' }
  Invoke-LabDocker compose logs --no-color
} finally { Stop-Transcript }
