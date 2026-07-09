<#
Build Sports.vk2ale Admin Manager for Windows.

Run this on a Windows build machine. PyInstaller is not a cross-compiler.
The output bundle includes Python and the app dependencies, so users do not
need to install Python, boto3, or PyInstaller.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $AppDir

$AppName = "SportsAdminManager"
$ReleaseDir = Join-Path $AppDir "release"
$VenvDir = Join-Path $AppDir ".venv-build"

Write-Host "==> Building $AppName for Windows from $AppDir"

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

$PythonLauncher = (Get-Command py -ErrorAction SilentlyContinue)
if ($PythonLauncher) {
    py -3 -m venv $VenvDir
} else {
    python -m venv $VenvDir
}

$Py = Join-Path $VenvDir "Scripts\python.exe"
& $Py -m pip install --upgrade pip wheel
& $Py -m pip install -r requirements.txt -r packaging\requirements-build.txt

& $Py -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name $AppName `
  --add-data "VERSION;." `
  --collect-all boto3 `
  --collect-all botocore `
  --collect-all s3transfer `
  --collect-all jmespath `
  --collect-all dateutil `
  --collect-all urllib3 `
  sports_admin_manager.py

$ZipPath = Join-Path $ReleaseDir "$AppName-windows-x64.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path "dist\$AppName\*" -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Built Windows package: $ZipPath"
Write-Host "Users can unzip it and run $AppName.exe."
