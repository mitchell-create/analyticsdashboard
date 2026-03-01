# Start Prefect worker (for use with Task Scheduler or manually).
# Set env vars so the daily_pipeline flow can run dbt and record to Supabase.
$RepoRoot = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:DBT_PROJECT_DIR = "$RepoRoot\dbt"
# Set SUPABASE_URL and SUPABASE_SERVICE_KEY in your environment or .env — do not hardcode here
if (-not $env:SUPABASE_URL) { $env:SUPABASE_URL = "YOUR_SUPABASE_URL" }
if (-not $env:SUPABASE_SERVICE_KEY) { $env:SUPABASE_SERVICE_KEY = "YOUR_SUPABASE_SERVICE_KEY" }
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"

$python = "C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe"
& $python -m prefect worker start --pool default-agent-pool
