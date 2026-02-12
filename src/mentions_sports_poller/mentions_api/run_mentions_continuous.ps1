Set-Location "C:\Users\mgube\mentions_ktest"
$env:PYTHONPATH = "src"
$env:POLL_INTERVAL_SECONDS = "180"
& ".\.venv\Scripts\python.exe" -m mentions_sports_poller.mentions_api.main
