# PowerShell 콘솔은 한글 출력이 깨지므로 pytest 결과를 UTF-8 파일로 저장합니다.
# 사용: powershell -File tests\run_pytest.ps1 [pytest 인자...]
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $env:TEMP "adforge_pytest.txt"
& (Join-Path $root ".venv\Scripts\python.exe") -m pytest -p no:cacheprovider @args 2>&1 |
    ForEach-Object { "$_" } | Set-Content -Encoding utf8 $out
Write-Output "pytest exit=$LASTEXITCODE  →  $out"
