$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11+ first.' }
& .\.venv\Scripts\python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Install Visual Studio Build Tools with Desktop development with C++, or use Docker.' }
& .\.venv\Scripts\geofolio.exe init
& .\.venv\Scripts\geofolio.exe serve @args
