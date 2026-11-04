param([ValidateSet('up','down','status')][string]$Action = 'up',[ValidateRange(1,10)][int]$Replicas = 3)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Get-Command docker -ErrorAction SilentlyContinue) {
  if ($Action -eq 'up') { docker compose up --build -d --scale "app=$Replicas" --wait }
  elseif ($Action -eq 'down') { docker compose down }
  else { docker compose ps }
  exit $LASTEXITCODE
}
$distro = 'Ubuntu-24.04'
$windowsPath = $PSScriptRoot.Replace('\','/')
$linuxPath = (& wsl -d $distro -u root --exec wslpath -a $windowsPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'No se encontró Ubuntu-24.04 en WSL 2' }
$pidFile = Join-Path $PSScriptRoot 'data/docker-wsl.pid'
if ($Action -eq 'up') {
  New-Item -ItemType Directory -Force (Split-Path $pidFile) | Out-Null
  $existingKeeper = $null
  if (Test-Path -LiteralPath $pidFile) {
    $savedId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$savedId" -ErrorAction SilentlyContinue
    if ($candidate.Name -eq 'wsl.exe' -and $candidate.CommandLine -like '*Ubuntu-24.04*sleep infinity*') { $existingKeeper = $candidate }
  }
  if (-not $existingKeeper) {
    $keeper = Start-Process -FilePath wsl.exe -ArgumentList '-d',$distro,'-u','root','--','sleep','infinity' -WindowStyle Hidden -PassThru
    $keeper.Id | Set-Content -LiteralPath $pidFile
  }
  & wsl -d $distro -u root --cd $linuxPath -- docker compose up --build -d --scale "app=$Replicas" --wait
} elseif ($Action -eq 'status') {
  & wsl -d $distro -u root --cd $linuxPath -- docker compose ps
} else {
  & wsl -d $distro -u root --cd $linuxPath -- docker compose down
  if ($LASTEXITCODE -ne 0) { throw 'No se pudieron detener los contenedores' }
  if (Test-Path -LiteralPath $pidFile) {
    $savedId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$savedId" -ErrorAction SilentlyContinue
    if ($candidate.Name -eq 'wsl.exe' -and $candidate.CommandLine -like '*Ubuntu-24.04*sleep infinity*') { Stop-Process -Id $savedId }
    Remove-Item -LiteralPath $pidFile
  }
}
if ($LASTEXITCODE -ne 0) { throw 'Falló el comando Docker' }
