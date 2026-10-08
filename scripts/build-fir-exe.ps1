$ErrorActionPreference = 'Stop'
$firRepo = Split-Path $PSScriptRoot -Parent
$firPython = Join-Path $firRepo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $firPython)) { throw 'Prepare .venv and install requirements.txt and build-requirements.txt.' }
Push-Location $firRepo
try {
    # Console handles are needed for EXE --mcp stdio. Hide the standalone GUI console.
    & $firPython -m PyInstaller --noconfirm --onefile --console --hide-console hide-late --name fir-tuner `
        --distpath docs/downloads --workpath build/fir --specpath build `
        --hidden-import mcp.server.fastmcp --hidden-import fir_mcp --collect-data customtkinter workshop/fir_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    Get-Item -LiteralPath 'docs/downloads/fir-tuner.exe' | Select-Object Name, Length
} finally { Pop-Location }
