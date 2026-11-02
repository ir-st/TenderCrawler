# TenderCrawler launcher
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

if ($Host.UI.RawUI) {
    try {
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        $OutputEncoding = [Text.UTF8Encoding]::new($false)
    } catch {}
}

Set-Location $PSScriptRoot
Set-Location ..

$script:PythonExe = $null
$script:PythonPrefix = @()

function Initialize-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $script:PythonExe = "py"
            $script:PythonPrefix = @("-3")
            return $true
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $script:PythonExe = "python"
            $script:PythonPrefix = @()
            return $true
        }
    }
    return $false
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs)
    & $script:PythonExe @script:PythonPrefix @ScriptArgs
}

function Wait-Exit {
    Write-Host ""
    Read-Host "Press Enter to exit"
}

function Get-AppVersion {
    # 从 version.py 动态读取版本号，避免发版时漏改启动脚本
    $versionFile = Join-Path (Get-Location) "version.py"
    if (Test-Path $versionFile) {
        $line = Get-Content $versionFile -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '__version__' } | Select-Object -First 1
        if ($line -and $line -match '__version__\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
    }
    return $null
}

try {
    $appVersion = Get-AppVersion
    $bannerTitle = "  TenderCrawler Web Console"
    if ($appVersion) {
        $bannerTitle += " v" + $appVersion
    }
    Write-Host "========================================"
    Write-Host $bannerTitle
    Write-Host "========================================"
    Write-Host ""
    Write-Host "Sites: cebpub | ccgp (ccgp delay >= 4s recommended)"
    Write-Host "Features: crawl / compare / tender schedule times"
    Write-Host ""

    if (-not (Initialize-Python)) {
        Write-Host "[ERROR] Python 3.10+ not found. Install from https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "        Enable 'Add python.exe to PATH' during setup."
        exit 1
    }

    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"

    $pyLabel = $script:PythonExe
    if ($script:PythonPrefix.Count -gt 0) {
        $pyLabel += " " + ($script:PythonPrefix -join " ")
    }
    Write-Host ("Python: " + $pyLabel)
    Write-Host "Installing dependencies..."
    Invoke-Python -m pip install -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] pip install failed." -ForegroundColor Red
        exit 1
    }

    if (-not (Test-Path "output")) {
        New-Item -ItemType Directory -Path "output" | Out-Null
    }

    Write-Host "Checking port 5000..."
    netstat -ano 2>$null | Select-String ':5000' | Select-String 'LISTENING' | ForEach-Object {
        $line = ($_.Line -replace '\s+', ' ').Trim()
        $procId = ($line -split ' ')[-1]
        if ($procId -match '^\d+$') {
            Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host ""
    Write-Host "URL: http://127.0.0.1:5000"
    Write-Host "Tabs: All results | Compare | Tender times"
    Write-Host "Close this window to stop the server."
    Write-Host ""

    Start-Process cmd.exe -ArgumentList '/c timeout /t 2 /nobreak >nul & start http://127.0.0.1:5000/' -WindowStyle Hidden

    # Do not use Stop on stderr from Flask/pip (would close the window immediately)
    Invoke-Python app.py 2>&1 | ForEach-Object { Write-Host $_ }
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host ("[ERROR] app.py exited with code " + $code) -ForegroundColor Red
        exit $code
    }
}
catch {
    Write-Host ("[ERROR] " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    Wait-Exit
}
