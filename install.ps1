# install.ps1 - robust installer (resolve real python.exe first)
$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$log  = Join-Path $base 'install.log'
function Log([string]$m){ $ts=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; Add-Content $log "[${ts}] $m"; Write-Host $m }

try { Clear-Content $log -ErrorAction SilentlyContinue } catch {}
Log "== Kassensystem Basic - install started =="; Log "Base: $base"

function TryGetPyExe([string]$cmd,[string[]]$args){
  try{ $p=& $cmd @args 2>$null; if($LASTEXITCODE -eq 0 -and $p){ return $p.Trim() } }catch{}
  return $null
}

$pythonExe = $null
if(-not $pythonExe){ $pythonExe = TryGetPyExe "py" @("-3","-c","import sys; print(sys.executable)") }
if(-not $pythonExe){ $pythonExe = TryGetPyExe "python"  @("-c","import sys; print(sys.executable)") }
if(-not $pythonExe){ $pythonExe = TryGetPyExe "python3" @("-c","import sys; print(sys.executable)") }
if(-not $pythonExe){
  $local = Join-Path $base "python.exe"
  if(Test-Path $local){ $pythonExe = $local }
}

if(-not $pythonExe){ Log "ERROR: Python 3 not found."; exit 1 }
Log "Using python: $pythonExe"

$venv   = Join-Path $base "venv"
$pyvenv = Join-Path $venv "Scripts\python.exe"

if(Test-Path $pyvenv){ Log "venv already exists - OK" }
else{
  Log "creating venv ..."
  & "$pythonExe" -m venv "$venv"
  if(-not (Test-Path $pyvenv)){ Log "ERROR: venv not created."; exit 1 }
}

Log "upgrade pip ..."; & "$pyvenv" -m pip install --upgrade pip
$req = Join-Path $base "requirements.txt"
if(Test-Path $req){
  Log "install requirements ..."; & "$pyvenv" -m pip install -r "$req"
}else{ Log "NOTE: requirements.txt not found - skipping deps" }

Log "== install finished OK =="; exit 0
