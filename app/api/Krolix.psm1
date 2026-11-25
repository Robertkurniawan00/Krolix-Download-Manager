<#
.SYNOPSIS
    Krolix Download Manager - Official PowerShell Automation Module
.DESCRIPTION
    Provides high-performance native cmdlets for integrating, automating, and controlling
    Krolix Download Manager via COM and REST endpoints from PowerShell.
.EXAMPLE
    Start-KrolixDownload -Url "https://fsn1-speed.hetzner.com/100MB.bin"
.EXAMPLE
    Start-KrolixDownload -Url "https://example.com/video.mp4" -Silent -Path "D:\Videos"
.EXAMPLE
    Get-KrolixStatus
#>

function Start-KrolixDownload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0, ValueFromPipeline = $true)]
        [string]$Url,

        [Parameter(Mandatory = $false)]
        [string]$Path = "",

        [Parameter(Mandatory = $false)]
        [string]$Filename = "",

        [Parameter(Mandatory = $false)]
        [string]$Referer = "",

        [Parameter(Mandatory = $false)]
        [string]$Cookies = "",

        [Parameter(Mandatory = $false)]
        [string]$UserAgent = "",

        [Parameter(Mandatory = $false)]
        [switch]$Silent,

        [Parameter(Mandatory = $false)]
        [switch]$QueueOnly
    )

    process {
        Write-Verbose "Dispatching download request for: $Url"

        # 1. Try COM Automation (Krolix COM Interface)
        try {
            $comObj = $null
            try { $comObj = New-Object -ComObject 'Krolix.LinkTransmitter' -ErrorAction Stop }
            catch { $comObj = New-Object -ComObject 'Zero.LinkTransmitter' -ErrorAction Stop }

            if ($comObj) {
                $flags = 0
                if ($Silent.IsPresent) { $flags = $flags -bor 1 }
                if ($QueueOnly.IsPresent) { $flags = $flags -bor 2 }

                $res = $comObj.SendLink2(
                    $Url,
                    $Referer,
                    $Cookies,
                    "", # PostData
                    "", # User
                    "", # Password
                    $Path,
                    $Filename,
                    $flags,
                    $UserAgent,
                    $null
                )

                if ($res -eq 0) {
                    Write-Host "[Krolix PowerShell] Dispatched via COM Automation successfully: $Url" -ForegroundColor Green
                    return [PSCustomObject]@{
                        Success = $true
                        Method  = "COM"
                        Url     = $Url
                    }
                }
            }
        }
        catch {
            Write-Verbose "COM Automation not active, falling back to HTTP REST API: $_"
        }

        # 2. Try Local HTTP REST API (Port 9666)
        try {
            $payload = @{
                url        = $Url
                save_dir   = $Path
                filename   = $Filename
                referer    = $Referer
                cookies    = $Cookies
                user_agent = $UserAgent
                silent     = $Silent.IsPresent
                queue_only = $QueueOnly.IsPresent
            } | ConvertTo-Json -Compress

            $response = Invoke-RestMethod -Uri "http://127.0.0.1:9666/download" `
                -Method Post `
                -ContentType "application/json; charset=utf-8" `
                -Body $payload `
                -Headers @{ "X-Krolix-Client" = "powershell-module" } `
                -TimeoutSec 3 `
                -ErrorAction Stop

            Write-Host "[Krolix PowerShell] Dispatched via REST API successfully: $Url" -ForegroundColor Green
            return [PSCustomObject]@{
                Success  = $true
                Method   = "REST"
                Url      = $Url
                Response = $response
            }
        }
        catch {
            Write-Verbose "Could not communicate with running Krolix instance. Attempting CLI launch..."
        }

        # 3. Fallback: Launch Krolix executable directly via CLI
        $localExe = [System.IO.Path]::Combine($env:LOCALAPPDATA, "Programs", "Krolix Download Manager", "Krolix.exe")
        $rootExe = [System.IO.Path]::Combine((Split-Path (Split-Path $PSScriptRoot -Parent) -Parent), "Krolix.exe")

        $targetExe = $null
        if (Test-Path $localExe) { $targetExe = $localExe }
        elseif (Test-Path $rootExe) { $targetExe = $rootExe }

        if ($targetExe) {
            $esc = { param($v) ($v -replace '"', '\"').TrimEnd('\') }
            $argsList = @("/d", "`"$(& $esc $Url)`"")
            if ($Path) { $argsList += @("/p", "`"$(& $esc $Path)`"") }
            if ($Filename) { $argsList += @("/f", "`"$(& $esc $Filename)`"") }
            if ($Silent.IsPresent) { $argsList += "/n" }
            if ($QueueOnly.IsPresent) { $argsList += "/a" }

            Start-Process -FilePath $targetExe -ArgumentList $argsList
            Write-Host "[Krolix PowerShell] Started Krolix process via CLI: $Url" -ForegroundColor Cyan
            return [PSCustomObject]@{
                Success = $true
                Method  = "CLI"
                Url     = $Url
            }
        }

        Write-Error "Failed to dispatch download to Krolix Download Manager."
        return [PSCustomObject]@{
            Success = $false
            Url     = $Url
        }
    }
}

function Add-KrolixQueue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0, ValueFromPipeline = $true)]
        [string]$Url,
        [Parameter(Mandatory = $false)]
        [string]$Path = "",
        [Parameter(Mandatory = $false)]
        [string]$Filename = ""
    )
    process {
        Start-KrolixDownload -Url $Url -Path $Path -Filename $Filename -QueueOnly
    }
}

function Get-KrolixStatus {
    [CmdletBinding()]
    param()
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:9666/status" -TimeoutSec 2 -ErrorAction Stop
        return [PSCustomObject]@{
            Online  = $true
            App     = $resp.app
            Version = $resp.version
            Port    = $resp.port
        }
    }
    catch {
        return [PSCustomObject]@{
            Online  = $false
            Message = "Krolix is not currently running or HTTP API port 9666 is closed."
        }
    }
}

# Aliases for backward compatibility
Set-Alias -Name Start-ZeroDownload -Value Start-KrolixDownload
Set-Alias -Name Add-ZeroQueue -Value Add-KrolixQueue
Set-Alias -Name Get-ZeroStatus -Value Get-KrolixStatus

Export-ModuleMember -Function Start-KrolixDownload, Add-KrolixQueue, Get-KrolixStatus -Alias Start-ZeroDownload, Add-ZeroQueue, Get-ZeroStatus
