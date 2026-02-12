# C:\Users\mgube\mentions_ktest\scripts\run_mentions_continuous.ps1
Set-Location "C:\Users\mgube\mentions_ktest"
$env:PYTHONPATH = "src"
$env:SQLITE_DB_PATH = "C:\Users\mgube\mentions_ktest\data\mentions_sports.db"
& "C:\Users\mgube\mentions_ktest\.venv\Scripts\python.exe" -m mentions_sports_poller.mentions_api.main
exit $LASTEXITCODE
