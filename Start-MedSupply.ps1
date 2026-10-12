[CmdletBinding()]
param([string]$ProjectPath = 'C:\medsupply\MedicalSupplyIntelligence')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $ProjectPath).Path
$frontendRoot = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $projectRoot 'venv\Scripts\python.exe'
$vitePath = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$logRoot = Join-Path $projectRoot 'local-server-logs'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project Python environment not found.' }
if (-not (Test-Path -LiteralPath $vitePath)) { throw 'Frontend packages are missing. Install them before starting.' }
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$runName = Get-Date -Format 'yyyyMMdd-HHmmss'
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -B -c 'from app.services.auth import keys; keys()'
    if ($LASTEXITCODE -ne 0) { throw 'Python packages or sign-in configuration are incomplete. Read the error above. Do not replace existing keys or reset the database.' }
    Write-Output 'Sign-in configuration is valid.'
} finally { Pop-Location }
function Test-LocalPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try { $task = $client.ConnectAsync('127.0.0.1', $Port); if (-not $task.Wait(700)) { return $false }; return $client.Connected }
    catch { return $false }
    finally { $client.Dispose() }
}
function Test-Api([int]$Port) {
    try { $result = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2; return ($result.status -eq 'healthy' -and $result.service -eq 'medical-supply-intelligence') }
    catch { return $false }
}
function Test-Frontend([int]$Port) {
    try { $result = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2 -UseBasicParsing; return ($result.StatusCode -eq 200 -and $result.Content -match 'Medical Supply') }
    catch { return $false }
}
function Wait-Ready([scriptblock]$Check, $Process, [string]$ErrorLog, [string]$Name) {
    for ($i = 0; $i -lt 45; $i++) {
        if (& $Check) { return }
        $Process.Refresh()
        if ($Process.HasExited) {
            if (Test-Path -LiteralPath $ErrorLog) { Get-Content -LiteralPath $ErrorLog -Tail 25 | Write-Output }
            throw "$Name stopped. Read $ErrorLog"
        }
        Start-Sleep -Milliseconds 1000
    }
    throw "$Name did not become ready. Read $ErrorLog"
}
$apiPort = 8000
if ((Test-LocalPort $apiPort) -and -not (Test-Api $apiPort)) {
    $freePort = @(8002..8010 | Where-Object { -not (Test-LocalPort $_) } | Select-Object -First 1)
    if (-not $freePort.Count) { throw 'No free API port from 8002 to 8010. No process was stopped.' }
    $apiPort = [int]$freePort[0]
    Write-Output "Port 8000 is occupied by another service. Using API port $apiPort."
}
$uiPort = 5173
if ((Test-LocalPort $uiPort) -and -not (Test-Frontend $uiPort)) {
    throw 'Port 5173 is occupied by another service. Identify it before continuing. No process was stopped.'
}
if ((Test-Frontend $uiPort) -and $apiPort -ne 8000) {
    throw 'The frontend is already running, but the API needs a different port. Stop only the frontend terminal with Ctrl+C, then run this launcher again.'
}
$originalOrigins = $env:FRONTEND_ORIGINS
$originalApiUrl = $env:VITE_API_URL
try {
    $env:FRONTEND_ORIGINS = '["http://127.0.0.1:5173","http://localhost:5173"]'
    $env:VITE_API_URL = "http://127.0.0.1:$apiPort/api/v1"
    if (-not (Test-Api $apiPort)) {
        $apiError = Join-Path $logRoot "$runName-api-error.log"
        $apiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$apiPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$runName-api-output.log") -RedirectStandardError $apiError
        Wait-Ready { Test-Api $apiPort } $apiProcess $apiError 'Backend'
        Write-Output "Backend ready. Process ID: $($apiProcess.Id)"
    } else { Write-Output 'Reusing the healthy backend.' }
    if (-not (Test-Frontend $uiPort)) {
        $uiError = Join-Path $logRoot "$runName-ui-error.log"
        $quotedVite = '"' + $vitePath + '"'
        $uiProcess = Start-Process -FilePath $nodePath -ArgumentList @($quotedVite,'--host','127.0.0.1','--port',"$uiPort",'--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$runName-ui-output.log") -RedirectStandardError $uiError
        Wait-Ready { Test-Frontend $uiPort } $uiProcess $uiError 'React interface'
        Write-Output "React ready. Process ID: $($uiProcess.Id)"
    } else { Write-Output 'Reusing the running frontend. If it still shows an API error, restart its terminal to load the API address.' }
    Write-Output "API: http://127.0.0.1:$apiPort/api/v1/health"
    Write-Output "Interface: http://127.0.0.1:$uiPort/"
    Write-Output "Logs: $logRoot"
    Write-Output 'Accounts, database, authentication, and transfer rules were not reset.'
    Write-Output 'For automatic alert updates, run the existing app.manage worker in a separate terminal. This launcher does not send external notifications.'
    Start-Process "http://127.0.0.1:$uiPort/"
} finally {
    if ($null -eq $originalOrigins) { Remove-Item Env:FRONTEND_ORIGINS -ErrorAction SilentlyContinue } else { $env:FRONTEND_ORIGINS = $originalOrigins }
    if ($null -eq $originalApiUrl) { Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue } else { $env:VITE_API_URL = $originalApiUrl }
}
