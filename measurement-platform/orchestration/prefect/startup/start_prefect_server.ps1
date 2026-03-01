# Start Prefect server (for use with Task Scheduler or manually).
# Set PREFECT_API_URL so the UI is at http://127.0.0.1:4200
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$python = "C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe"
& $python -m prefect server start
