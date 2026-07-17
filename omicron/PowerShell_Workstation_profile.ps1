<#
.SYNOPSIS
    PowerShell 7.6.x engineering workstation profile.

.DESCRIPTION
    Drop this file into $PROFILE.CurrentUserAllHosts or dot-source it from an
    existing profile. It turns PowerShell into a modular control plane for local
    automation, cloud compute, simulations, rendering, documentation, tests, and
    AI-assisted workflows.

.NOTES
    Target: PowerShell 7.6.2 / 7.6.x
    Startup policy: safe by default. It creates directories, imports available
    modules, improves the interactive shell, and prints status. It does not log
    into clouds, install modules, submit jobs, prune Docker, or read secrets
    unless you explicitly call those functions.
#>

# -----------------------------------------------------------------------------
# 0. Guardrails
# -----------------------------------------------------------------------------

$script:WorkstationProfileVersion = '0.1.0'
$script:WorkstationTargetPowerShell = [version]'7.6.2'
$script:WorkstationMinimumPowerShell = [version]'7.6.0'

if ($PSVersionTable.PSVersion -lt $script:WorkstationMinimumPowerShell) {
    Write-Warning "This workstation profile targets PowerShell 7.6.x. Current version: $($PSVersionTable.PSVersion). Some features may not work."
}

# Preserve normal interactive behavior. Do not set global StrictMode from a profile.
$ErrorActionPreference = 'Continue'

if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

# -----------------------------------------------------------------------------
# 1. Deterministic paths and environment variables
# -----------------------------------------------------------------------------

function Set-WSEnvDefault {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Value
    )

    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, 'Process'))) {
        Set-Item -Path "Env:$Name" -Value $Value
    }
}

function New-WSDirectory {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -ItemType Directory -Force | Out-Null
    }

    return (Resolve-Path -LiteralPath $Path).ProviderPath
}

function Add-WSPathEntry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Path,
        [ValidateSet('Path', 'PSModulePath')] [string] $Variable = 'Path',
        [switch] $Prepend
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }

    $separator = [IO.Path]::PathSeparator
    $current = [Environment]::GetEnvironmentVariable($Variable, 'Process')
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        $parts = $current -split [regex]::Escape($separator) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }

    $resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
    if ($parts -contains $resolved) { return }

    if ($Prepend) { $parts = @($resolved) + $parts } else { $parts = $parts + @($resolved) }
    [Environment]::SetEnvironmentVariable($Variable, ($parts -join $separator), 'Process')
}

$script:WSHome = if ($HOME) { $HOME } else { [Environment]::GetFolderPath('UserProfile') }
$script:WS = [ordered]@{
    Root      = Join-Path $script:WSHome 'pwsh-workstation'
    Modules   = Join-Path $script:WSHome 'pwsh-workstation/Modules'
    Profiles  = Join-Path $script:WSHome 'pwsh-workstation/Profiles'
    Pipelines = Join-Path $script:WSHome 'pwsh-workstation/Pipelines'
    Jobs      = Join-Path $script:WSHome 'pwsh-workstation/Jobs'
    Projects  = Join-Path $script:WSHome 'Projects'
    Secrets   = Join-Path $script:WSHome 'pwsh-workstation/Secrets'
    Config    = Join-Path $script:WSHome 'pwsh-workstation/Config'
    Cache     = Join-Path $script:WSHome 'pwsh-workstation/Cache'
    Logs      = Join-Path $script:WSHome 'pwsh-workstation/Logs'
    Reports   = Join-Path $script:WSHome 'pwsh-workstation/Reports'
    Temp      = Join-Path $script:WSHome 'pwsh-workstation/Temp'
}

foreach ($path in $script:WS.Values) { New-WSDirectory -Path $path | Out-Null }

foreach ($pipeline in @('HPC', 'Simulation', 'Rendering', 'Automation', 'AI')) {
    New-WSDirectory -Path (Join-Path $script:WS.Pipelines $pipeline) | Out-Null
}

Set-WSEnvDefault -Name 'WORKSTATION_HOME' -Value $script:WS.Root
Set-WSEnvDefault -Name 'WORKSTATION_MODULES' -Value $script:WS.Modules
Set-WSEnvDefault -Name 'WORKSTATION_PIPELINES' -Value $script:WS.Pipelines
Set-WSEnvDefault -Name 'WORKSTATION_JOBS' -Value $script:WS.Jobs
Set-WSEnvDefault -Name 'WORKSTATION_PROJECTS' -Value $script:WS.Projects
Set-WSEnvDefault -Name 'WORKSTATION_CACHE' -Value $script:WS.Cache
Set-WSEnvDefault -Name 'WORKSTATION_LOGS' -Value $script:WS.Logs
Set-WSEnvDefault -Name 'WORKSTATION_PROFILE_VERSION' -Value $script:WorkstationProfileVersion
Set-WSEnvDefault -Name 'WORKSTATION_STARTUP_PROFILE' -Value 'Standard'
Set-WSEnvDefault -Name 'WORKSTATION_FAST_START' -Value '0'
Set-WSEnvDefault -Name 'WORKSTATION_AZURE_LOCATION' -Value 'uksouth'
Set-WSEnvDefault -Name 'WORKSTATION_AWS_REGION' -Value 'eu-west-2'
Set-WSEnvDefault -Name 'WORKSTATION_GCP_REGION' -Value 'europe-west2'
Set-WSEnvDefault -Name 'WORKSTATION_GCP_ZONE' -Value 'europe-west2-a'
Set-WSEnvDefault -Name 'WORKSTATION_AI_PROVIDER' -Value 'generic'
Set-WSEnvDefault -Name 'WORKSTATION_AI_MODEL' -Value 'default'
Set-WSEnvDefault -Name 'DOCKER_BUILDKIT' -Value '1'
Set-WSEnvDefault -Name 'COMPOSE_DOCKER_CLI_BUILD' -Value '1'
Set-WSEnvDefault -Name 'PYTHONUTF8' -Value '1'

Add-WSPathEntry -Path $script:WS.Modules -Variable PSModulePath -Prepend

$script:WSState = @{
    ActiveCloud  = 'Local'
    Azure        = @{}
    AWS          = @{}
    GCP          = @{}
    CloudSummary = 'local'
}

# -----------------------------------------------------------------------------
# 2. Core utilities
# -----------------------------------------------------------------------------

function Test-WSInteractive {
    [CmdletBinding()]
    param()

    if ($env:CI -eq 'true') { return $false }
    if (-not [Environment]::UserInteractive) { return $false }
    return $true
}

function ConvertTo-WSSingleQuotedString {
    [CmdletBinding()]
    param([AllowNull()] [string] $Text)

    if ($null -eq $Text) { return "''" }
    return "'" + ($Text -replace "'", "''") + "'"
}

function Resolve-WSPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Path,
        [switch] $AllowMissing
    )

    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if ($expanded.StartsWith('~')) {
        $expanded = Join-Path $script:WSHome $expanded.Substring(1).TrimStart('/','\')
    }

    try {
        return (Resolve-Path -LiteralPath $expanded -ErrorAction Stop).ProviderPath
    } catch {
        if ($AllowMissing) { return $expanded }
        throw
    }
}

function Write-WSLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Message,
        [ValidateSet('DEBUG', 'INFO', 'WARN', 'ERROR')] [string] $Level = 'INFO'
    )

    $logPath = Join-Path $script:WS.Logs 'workstation-profile.log'
    $line = '{0} [{1}] {2}' -f (Get-Date -Format o), $Level, $Message
    Add-Content -Path $logPath -Value $line -Encoding utf8
}

function Test-WSCommand {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Name)

    return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Invoke-WSNative {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $FilePath,
        [string[]] $ArgumentList = @(),
        [switch] $IgnoreExitCode
    )

    $command = Get-Command -Name $FilePath -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required command '$FilePath' was not found in PATH." }

    & $command.Source @ArgumentList
    $exitCode = $LASTEXITCODE
    if (-not $IgnoreExitCode -and $null -ne $exitCode -and $exitCode -ne 0) {
        throw "Command '$FilePath' failed with exit code $exitCode. Arguments: $($ArgumentList -join ' ')"
    }
}

function Import-WSModule {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [switch] $Required,
        [switch] $Quiet
    )

    if (Get-Module -Name $Name) { return $true }

    $module = Get-Module -ListAvailable -Name $Name | Sort-Object Version -Descending | Select-Object -First 1
    if (-not $module) {
        if ($Required -and -not $Quiet) { Write-Warning "Module '$Name' is not installed." }
        return $false
    }

    try {
        Import-Module -Name $Name -ErrorAction Stop
        return $true
    } catch {
        if ($Required -and -not $Quiet) { Write-Warning "Failed to import module '$Name': $($_.Exception.Message)" }
        return $false
    }
}

function Install-WSModule {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string[]] $Name,
        [ValidateSet('CurrentUser', 'AllUsers')] [string] $Scope = 'CurrentUser',
        [switch] $Force
    )

    foreach ($moduleName in $Name) {
        $alreadyInstalled = Get-Module -ListAvailable -Name $moduleName | Select-Object -First 1
        if ($alreadyInstalled -and -not $Force) {
            Write-Host "Module already installed: $moduleName $($alreadyInstalled.Version)"
            continue
        }

        if (-not $PSCmdlet.ShouldProcess($moduleName, 'Install PowerShell module')) { continue }

        if (Get-Command -Name Install-PSResource -ErrorAction SilentlyContinue) {
            $args = @{
                Name        = $moduleName
                Scope       = $Scope
                ErrorAction = 'Stop'
            }
            if ($Force) { $args['Reinstall'] = $true }
            try {
                Install-PSResource @args
            } catch {
                $args.Remove('Reinstall') | Out-Null
                Install-PSResource @args
            }
        } elseif (Get-Command -Name Install-Module -ErrorAction SilentlyContinue) {
            $args = @{
                Name         = $moduleName
                Scope        = $Scope
                AllowClobber = $true
                Force        = $Force.IsPresent
                ErrorAction  = 'Stop'
            }
            Install-Module @args
        } else {
            throw 'Neither Install-PSResource nor Install-Module is available. Install Microsoft.PowerShell.PSResourceGet or PowerShellGet first.'
        }
    }
}

function Install-WorkstationModules {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [switch] $IncludeCloud,
        [switch] $IncludeGoogleCloudModule,
        [switch] $Force
    )

    $baseModules = @(
        'PSReadLine',
        'PSScriptAnalyzer',
        'PowerShellGet',
        'Microsoft.PowerShell.PSResourceGet',
        'Microsoft.PowerShell.SecretManagement',
        'Microsoft.PowerShell.SecretStore',
        'Pester',
        'PlatyPS',
        'PSFzf',
        'Terminal-Icons',
        'posh-git'
    )

    $cloudModules = @(
        'Az.Accounts',
        'Az.Compute',
        'Az.Batch',
        'Az.Storage',
        'AWS.Tools.Common',
        'AWS.Tools.EC2',
        'AWS.Tools.Batch',
        'AWS.Tools.S3',
        'AWS.Tools.SecurityToken'
    )

    if ($IncludeGoogleCloudModule) {
        $cloudModules += 'GoogleCloud'
    }

    $modules = if ($IncludeCloud) { $baseModules + $cloudModules } else { $baseModules }
    Install-WSModule -Name ($modules | Select-Object -Unique) -Force:$Force -WhatIf:$WhatIfPreference
}

function Initialize-WorkstationModules {
    [CmdletBinding()]
    param([switch] $Quiet)

    $startupModules = @(
        'PSReadLine',
        'Terminal-Icons',
        'posh-git',
        'PSFzf'
    )

    if ($env:WORKSTATION_FAST_START -eq '1') {
        $startupModules = @('PSReadLine')
    }

    foreach ($moduleName in $startupModules) {
        Import-WSModule -Name $moduleName -Quiet:$Quiet | Out-Null
    }
}

# -----------------------------------------------------------------------------
# 3. Secret store bindings
# -----------------------------------------------------------------------------

function Initialize-WorkstationSecretVault {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string] $VaultName = 'WorkstationVault',
        [switch] $SetDefault
    )

    if (-not (Import-WSModule -Name 'Microsoft.PowerShell.SecretManagement' -Required)) { return }
    if (-not (Import-WSModule -Name 'Microsoft.PowerShell.SecretStore' -Required)) { return }

    $vault = Get-SecretVault -Name $VaultName -ErrorAction SilentlyContinue
    if (-not $vault) {
        if ($PSCmdlet.ShouldProcess($VaultName, 'Register SecretStore vault')) {
            Register-SecretVault -Name $VaultName -ModuleName Microsoft.PowerShell.SecretStore -DefaultVault:$SetDefault -ErrorAction Stop
        }
    } elseif ($SetDefault) {
        Set-SecretVaultDefault -Name $VaultName
    }

    Get-SecretVault -Name $VaultName
}

function Get-WorkstationSecret {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [string] $VaultName = 'WorkstationVault',
        [switch] $AsPlainText
    )

    if (-not (Import-WSModule -Name 'Microsoft.PowerShell.SecretManagement' -Required)) { return $null }
    $secret = Get-Secret -Name $Name -Vault $VaultName -ErrorAction Stop

    if ($AsPlainText -and $secret -is [securestring]) {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        )
    }

    return $secret
}

function Set-WorkstationSecret {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] $Secret,
        [string] $VaultName = 'WorkstationVault'
    )

    if (-not (Import-WSModule -Name 'Microsoft.PowerShell.SecretManagement' -Required)) { return }
    Set-Secret -Name $Name -Secret $Secret -Vault $VaultName
}

# -----------------------------------------------------------------------------
# 4. UI enhancements and prompt
# -----------------------------------------------------------------------------

function Initialize-WSReadLine {
    [CmdletBinding()]
    param()

    if (-not (Import-WSModule -Name 'PSReadLine')) { return }

    $editMode = if ($IsWindows) { 'Windows' } else { 'Emacs' }
    $options = @{
        EditMode                      = $editMode
        HistoryNoDuplicates           = $true
        HistorySearchCursorMovesToEnd = $true
        BellStyle                     = 'None'
        PredictionViewStyle           = 'ListView'
    }

    try {
        $options['PredictionSource'] = 'HistoryAndPlugin'
        Set-PSReadLineOption @options
    } catch {
        $options['PredictionSource'] = 'History'
        try { Set-PSReadLineOption @options } catch { }
    }

    try { Set-PSReadLineKeyHandler -Chord 'Ctrl+r' -Function ReverseSearchHistory } catch { }
    try { Set-PSReadLineKeyHandler -Chord 'Ctrl+Spacebar' -Function MenuComplete } catch { }
    try { Set-PSReadLineKeyHandler -Chord 'Ctrl+l' -ScriptBlock { Clear-Host } } catch { }

    if (Get-Command -Name Set-PsFzfOption -ErrorAction SilentlyContinue) {
        try {
            Set-PsFzfOption -PSReadlineChordProvider 'Ctrl+f' -PSReadlineChordReverseHistory 'Ctrl+r'
        } catch { }
    }
}

function Get-WSGitBranch {
    [CmdletBinding()]
    param()

    if (-not (Test-WSCommand -Name 'git')) { return $null }

    try {
        $inside = & git rev-parse --is-inside-work-tree 2>$null
        if ($LASTEXITCODE -ne 0 -or $inside -ne 'true') { return $null }
        $branch = & git branch --show-current 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($branch)) { return $branch.Trim() }
    } catch { }

    return $null
}

function Update-WSCloudSummary {
    [CmdletBinding()]
    param()

    $parts = @("active:$($script:WSState.ActiveCloud)")

    if ($script:WSState.Azure.SubscriptionId) {
        $parts += "az:$($script:WSState.Azure.SubscriptionId)"
    }
    if ($script:WSState.AWS.Profile) {
        $parts += "aws:$($script:WSState.AWS.Profile)"
    }
    if ($script:WSState.GCP.Project) {
        $parts += "gcp:$($script:WSState.GCP.Project)"
    }

    $script:WSState.CloudSummary = $parts -join ' '
}

function Set-WSActiveCloud {
    [CmdletBinding()]
    param([ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider)

    $script:WSState.ActiveCloud = $Provider
    Update-WSCloudSummary
    return $script:WSState.CloudSummary
}

function Initialize-WSUI {
    [CmdletBinding()]
    param()

    Initialize-WSReadLine

    if (Get-Variable -Name PSStyle -Scope Global -ErrorAction SilentlyContinue) {
        $PSStyle.OutputRendering = 'Ansi'
    }

    function global:prompt {
        $lastSuccess = $?
        $location = (Get-Location).Path
        $homeResolved = try { (Resolve-Path -LiteralPath $script:WSHome).ProviderPath } catch { $script:WSHome }
        if ($location.StartsWith($homeResolved)) {
            $displayPath = '~' + $location.Substring($homeResolved.Length)
        } else {
            $displayPath = $location
        }

        $branch = Get-WSGitBranch
        $cloud = $script:WSState.CloudSummary
        $symbol = if ($lastSuccess) { 'PS' } else { 'PS!' }

        Write-Host ''
        Write-Host $symbol -NoNewline -ForegroundColor Cyan
        Write-Host ' ' -NoNewline
        Write-Host $displayPath -NoNewline -ForegroundColor Yellow

        if ($branch) {
            Write-Host ' [' -NoNewline -ForegroundColor DarkGray
            Write-Host $branch -NoNewline -ForegroundColor Green
            Write-Host ']' -NoNewline -ForegroundColor DarkGray
        }

        if ($cloud) {
            Write-Host ' {' -NoNewline -ForegroundColor DarkGray
            Write-Host $cloud -NoNewline -ForegroundColor Magenta
            Write-Host '}' -NoNewline -ForegroundColor DarkGray
        }

        return "`n> "
    }
}

function Show-WorkstationBanner {
    [CmdletBinding()]
    param()

    if (-not (Test-WSInteractive)) { return }
    if ($env:WORKSTATION_SUPPRESS_BANNER -eq '1') { return }

    $moduleStatus = foreach ($name in @('PSReadLine', 'PSScriptAnalyzer', 'Pester', 'PlatyPS', 'Az.Accounts', 'AWS.Tools.Common', 'GoogleCloud')) {
        [pscustomobject]@{
            Name      = $name
            Installed = [bool](Get-Module -ListAvailable -Name $name | Select-Object -First 1)
        }
    }

    $cliStatus = foreach ($name in @('git', 'docker', 'az', 'aws', 'gcloud', 'kubectl', 'code')) {
        [pscustomobject]@{
            Name      = $name
            Available = Test-WSCommand -Name $name
        }
    }

    Write-Host ''
    Write-Host 'PowerShell Engineering Workstation' -ForegroundColor Cyan
    Write-Host ('Profile {0} | PowerShell {1} | Root {2}' -f $script:WorkstationProfileVersion, $PSVersionTable.PSVersion, $script:WS.Root) -ForegroundColor DarkGray
    Write-Host ('Cloud: {0}' -f $script:WSState.CloudSummary) -ForegroundColor DarkGray

    $missingModules = ($moduleStatus | Where-Object { -not $_.Installed }).Name
    $missingCli = ($cliStatus | Where-Object { -not $_.Available }).Name

    if ($missingModules.Count -gt 0) {
        Write-Host ('Missing optional modules: {0}' -f ($missingModules -join ', ')) -ForegroundColor DarkYellow
    }
    if ($missingCli.Count -gt 0) {
        Write-Host ('Missing optional CLI tools: {0}' -f ($missingCli -join ', ')) -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# 5. Cloud bindings
# -----------------------------------------------------------------------------

function Connect-WSAzure {
    [CmdletBinding()]
    param(
        [string] $TenantId,
        [string] $SubscriptionId,
        [string] $Environment = 'AzureCloud',
        [switch] $DeviceCode
    )

    $script:WSState.ActiveCloud = 'Azure'

    if (Import-WSModule -Name 'Az.Accounts') {
        $args = @{ ErrorAction = 'Stop' }
        if ($TenantId) { $args['Tenant'] = $TenantId }
        if ($SubscriptionId) { $args['Subscription'] = $SubscriptionId }
        if ($Environment) { $args['Environment'] = $Environment }
        if ($DeviceCode) { $args['UseDeviceAuthentication'] = $true }

        Connect-AzAccount @args | Out-Null
        if ($SubscriptionId) { Set-AzContext -Subscription $SubscriptionId -ErrorAction Stop | Out-Null }
        $ctx = Get-AzContext
        $script:WSState.Azure = @{
            Account          = $ctx.Account.Id
            SubscriptionName = $ctx.Subscription.Name
            SubscriptionId   = $ctx.Subscription.Id
            TenantId         = $ctx.Tenant.Id
            Environment      = $ctx.Environment.Name
        }
    } elseif (Test-WSCommand -Name 'az') {
        $args = @('login')
        if ($TenantId) { $args += @('--tenant', $TenantId) }
        Invoke-WSNative -FilePath 'az' -ArgumentList $args
        if ($SubscriptionId) { Invoke-WSNative -FilePath 'az' -ArgumentList @('account', 'set', '--subscription', $SubscriptionId) }

        $json = & az account show --output json 2>$null | ConvertFrom-Json
        $script:WSState.Azure = @{
            Account          = $json.user.name
            SubscriptionName = $json.name
            SubscriptionId   = $json.id
            TenantId         = $json.tenantId
            Environment      = $json.environmentName
        }
    } else {
        throw 'Neither Az.Accounts nor the Azure CLI was found. Install one of them before connecting to Azure.'
    }

    Update-WSCloudSummary
    Get-WSAzureContext
}

function Get-WSAzureContext {
    [CmdletBinding()]
    param()

    if ($script:WSState.Azure.Count -gt 0) { return [pscustomobject]$script:WSState.Azure }

    if (Get-Command -Name Get-AzContext -ErrorAction SilentlyContinue) {
        $ctx = Get-AzContext -ErrorAction SilentlyContinue
        if ($ctx) {
            return [pscustomobject]@{
                Account          = $ctx.Account.Id
                SubscriptionName = $ctx.Subscription.Name
                SubscriptionId   = $ctx.Subscription.Id
                TenantId         = $ctx.Tenant.Id
                Environment      = $ctx.Environment.Name
            }
        }
    }

    if (Test-WSCommand -Name 'az') {
        try { return (& az account show --output json 2>$null | ConvertFrom-Json) } catch { }
    }

    return $null
}

function Connect-WSAws {
    [CmdletBinding()]
    param(
        [string] $ProfileName = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { 'default' }),
        [string] $Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { $env:WORKSTATION_AWS_REGION })
    )

    $script:WSState.ActiveCloud = 'AWS'
    $env:AWS_PROFILE = $ProfileName
    if ($Region) {
        $env:AWS_REGION = $Region
        $env:AWS_DEFAULT_REGION = $Region
    }

    if (Import-WSModule -Name 'AWS.Tools.Common') {
        try {
            Set-AWSCredential -ProfileName $ProfileName -ErrorAction Stop
            if ($Region) { Set-DefaultAWSRegion -Region $Region -ErrorAction Stop }
        } catch {
            Write-Warning "AWS module context was not fully initialized: $($_.Exception.Message)"
        }
    }

    $identity = $null
    if (Import-WSModule -Name 'AWS.Tools.SecurityToken' -Quiet) {
        try { $identity = Get-STSCallerIdentity -ErrorAction Stop } catch { }
    }
    if (-not $identity -and (Test-WSCommand -Name 'aws')) {
        try { $identity = & aws sts get-caller-identity --output json 2>$null | ConvertFrom-Json } catch { }
    }

    $script:WSState.AWS = @{
        Profile = $ProfileName
        Region  = $Region
        Account = if ($identity.Account) { $identity.Account } else { $null }
        Arn     = if ($identity.Arn) { $identity.Arn } else { $null }
        UserId  = if ($identity.UserId) { $identity.UserId } else { $null }
    }

    Update-WSCloudSummary
    Get-WSAwsContext
}

function Get-WSAwsContext {
    [CmdletBinding()]
    param()

    if ($script:WSState.AWS.Count -gt 0) { return [pscustomobject]$script:WSState.AWS }
    return [pscustomobject]@{
        Profile = $env:AWS_PROFILE
        Region  = if ($env:AWS_REGION) { $env:AWS_REGION } else { $env:AWS_DEFAULT_REGION }
    }
}

function Connect-WSGcp {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Project,
        [string] $Region = $env:WORKSTATION_GCP_REGION,
        [string] $Zone = $env:WORKSTATION_GCP_ZONE,
        [switch] $Login
    )

    $script:WSState.ActiveCloud = 'GCP'
    Import-WSModule -Name 'GoogleCloud' -Quiet | Out-Null

    if (-not (Test-WSCommand -Name 'gcloud')) {
        throw 'The gcloud CLI was not found. Install Google Cloud CLI before connecting to GCP.'
    }

    if ($Login) { Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('auth', 'login') }
    Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('config', 'set', 'project', $Project)
    if ($Region) { Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('config', 'set', 'compute/region', $Region) }
    if ($Zone) { Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('config', 'set', 'compute/zone', $Zone) }

    $script:WSState.GCP = @{
        Project = $Project
        Region  = $Region
        Zone    = $Zone
    }

    Update-WSCloudSummary
    Get-WSGcpContext
}

function Get-WSGcpContext {
    [CmdletBinding()]
    param()

    if (Test-WSCommand -Name 'gcloud') {
        try {
            $config = & gcloud config list --format=json 2>$null | ConvertFrom-Json
            return [pscustomobject]@{
                Project = $config.core.project
                Region  = $config.compute.region
                Zone    = $config.compute.zone
                Account = $config.core.account
            }
        } catch { }
    }

    if ($script:WSState.GCP.Count -gt 0) { return [pscustomobject]$script:WSState.GCP }
    return $null
}

# -----------------------------------------------------------------------------
# 6. HPC and cloud job orchestration
# -----------------------------------------------------------------------------

function New-WSJobManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider,
        [Parameter(Mandatory)] [string] $Script,
        [int] $Nodes = 1,
        [string] $Gpu = 'none',
        [int] $CpuPerNode = 1,
        [int] $MemoryGB = 4,
        [string] $Queue,
        [string] $ContainerImage,
        [hashtable] $BackendConfig = @{},
        [hashtable] $Metadata = @{}
    )

    $safeName = ($Name -replace '[^A-Za-z0-9_.-]', '-')
    $jobId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $safeName
    $jobDir = New-WSDirectory -Path (Join-Path $script:WS.Jobs $jobId)
    $scriptPath = Resolve-WSPath -Path $Script
    $manifestPath = Join-Path $jobDir 'job.json'

    $manifest = [ordered]@{
        JobId          = $jobId
        Name           = $Name
        Provider       = $Provider
        Script         = $scriptPath
        Nodes          = $Nodes
        Gpu            = $Gpu
        CpuPerNode     = $CpuPerNode
        MemoryGB       = $MemoryGB
        Queue          = $Queue
        ContainerImage = $ContainerImage
        BackendConfig  = $BackendConfig
        Metadata       = $Metadata
        CreatedAt      = (Get-Date).ToString('o')
        JobDirectory   = $jobDir
    }

    $manifest | ConvertTo-Json -Depth 12 | Set-Content -Path $manifestPath -Encoding utf8

    [pscustomobject]@{
        JobId        = $jobId
        JobDirectory = $jobDir
        ManifestPath = $manifestPath
        Manifest     = [pscustomobject]$manifest
    }
}

function Start-WSLocalJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $ManifestPath
    )

    $manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json
    if (-not $PSCmdlet.ShouldProcess($manifest.Script, 'Start local PowerShell background job')) { return }

    $job = Start-Job -FilePath $manifest.Script -Name $manifest.JobId
    [pscustomobject]@{
        Provider     = 'Local'
        JobId        = $manifest.JobId
        PowerShellId = $job.Id
        State        = $job.State
        ManifestPath = $ManifestPath
    }
}

function Start-WSAwsBatchJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $ManifestPath,
        [hashtable] $BackendConfig = @{}
    )

    if (-not (Test-WSCommand -Name 'aws')) { throw 'AWS CLI is required for AWS Batch submission from this profile.' }
    $manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json

    foreach ($required in @('JobQueue', 'JobDefinition')) {
        if (-not $BackendConfig.ContainsKey($required)) {
            throw "AWS backend config missing '$required'. Example: -BackendConfig @{ JobQueue='queue'; JobDefinition='definition:1'; Command=@('pwsh','-File','s3://...') }"
        }
    }

    $remoteCommand = if ($BackendConfig.ContainsKey('Command')) { [string[]]$BackendConfig.Command } else { @('pwsh', '-NoLogo', '-NoProfile', '-File', $manifest.Script) }
    $overrides = @{ command = $remoteCommand } | ConvertTo-Json -Compress

    $args = @(
        'batch', 'submit-job',
        '--job-name', $manifest.JobId,
        '--job-queue', [string]$BackendConfig.JobQueue,
        '--job-definition', [string]$BackendConfig.JobDefinition,
        '--container-overrides', $overrides,
        '--output', 'json'
    )

    if ($PSCmdlet.ShouldProcess($manifest.JobId, 'Submit AWS Batch job')) {
        Invoke-WSNative -FilePath 'aws' -ArgumentList $args
    }
}

function Start-WSAzureBatchJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $ManifestPath,
        [hashtable] $BackendConfig = @{}
    )

    if (-not (Test-WSCommand -Name 'az')) { throw 'Azure CLI is required for Azure Batch submission from this profile.' }
    $manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json

    foreach ($required in @('PoolId')) {
        if (-not $BackendConfig.ContainsKey($required)) {
            throw "Azure backend config missing '$required'. Example: -BackendConfig @{ PoolId='pool'; CommandLine='pwsh -File startup.ps1' }"
        }
    }

    if ($BackendConfig.ContainsKey('BatchAccount') -and $BackendConfig.ContainsKey('ResourceGroup')) {
        Invoke-WSNative -FilePath 'az' -ArgumentList @('batch', 'account', 'login', '--name', [string]$BackendConfig.BatchAccount, '--resource-group', [string]$BackendConfig.ResourceGroup)
    }

    $commandLine = if ($BackendConfig.ContainsKey('CommandLine')) { [string]$BackendConfig.CommandLine } else { "pwsh -NoLogo -NoProfile -File `"$($manifest.Script)`"" }

    if ($PSCmdlet.ShouldProcess($manifest.JobId, 'Submit Azure Batch job')) {
        Invoke-WSNative -FilePath 'az' -ArgumentList @('batch', 'job', 'create', '--id', $manifest.JobId, '--pool-id', [string]$BackendConfig.PoolId)
        Invoke-WSNative -FilePath 'az' -ArgumentList @('batch', 'task', 'create', '--job-id', $manifest.JobId, '--task-id', 'task-001', '--command-line', $commandLine)
        [pscustomobject]@{ Provider = 'Azure'; JobId = $manifest.JobId; ManifestPath = $ManifestPath }
    }
}

function Start-WSGcpBatchJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $ManifestPath,
        [hashtable] $BackendConfig = @{}
    )

    if (-not (Test-WSCommand -Name 'gcloud')) { throw 'gcloud CLI is required for GCP Batch submission from this profile.' }
    $manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json
    $region = if ($BackendConfig.ContainsKey('Region')) { [string]$BackendConfig.Region } else { $env:WORKSTATION_GCP_REGION }
    if (-not $region) { throw 'GCP region is required. Set WORKSTATION_GCP_REGION or pass -BackendConfig @{ Region = "..." }.' }

    $commandLine = if ($BackendConfig.ContainsKey('CommandLine')) { [string]$BackendConfig.CommandLine } else { "pwsh -NoLogo -NoProfile -File '$($manifest.Script)'" }
    $configPath = Join-Path $manifest.JobDirectory 'gcp-batch.json'

    $config = @{
        taskGroups = @(
            @{
                taskCount = $manifest.Nodes
                parallelism = $manifest.Nodes
                taskSpec = @{
                    runnables = @(@{ script = @{ text = $commandLine } })
                    computeResource = @{
                        cpuMilli  = [int]($manifest.CpuPerNode * 1000)
                        memoryMib = [int]($manifest.MemoryGB * 1024)
                    }
                    maxRetryCount = 0
                }
            }
        )
        logsPolicy = @{ destination = 'CLOUD_LOGGING' }
    }

    $config | ConvertTo-Json -Depth 12 | Set-Content -Path $configPath -Encoding utf8

    if ($PSCmdlet.ShouldProcess($manifest.JobId, 'Submit GCP Batch job')) {
        Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('batch', 'jobs', 'submit', $manifest.JobId, '--location', $region, '--config', $configPath)
        [pscustomobject]@{ Provider = 'GCP'; JobId = $manifest.JobId; ManifestPath = $ManifestPath; ConfigPath = $configPath }
    }
}

function Start-HPCJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $Script,
        [string] $Name = $(Split-Path -LeafBase $Script),
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [int] $Nodes = 1,
        [string] $Gpu = 'none',
        [int] $CpuPerNode = 1,
        [int] $MemoryGB = 4,
        [string] $Queue,
        [string] $ContainerImage,
        [hashtable] $BackendConfig = @{},
        [hashtable] $Metadata = @{},
        [switch] $Submit
    )

    $manifestInfo = New-WSJobManifest -Name $Name -Provider $Provider -Script $Script -Nodes $Nodes -Gpu $Gpu -CpuPerNode $CpuPerNode -MemoryGB $MemoryGB -Queue $Queue -ContainerImage $ContainerImage -BackendConfig $BackendConfig -Metadata $Metadata

    if (-not $Submit) {
        Write-Host "Created job manifest: $($manifestInfo.ManifestPath)" -ForegroundColor DarkGray
        return $manifestInfo
    }

    switch ($Provider) {
        'Local' { return Start-WSLocalJob -ManifestPath $manifestInfo.ManifestPath -WhatIf:$WhatIfPreference }
        'AWS'   { return Start-WSAwsBatchJob -ManifestPath $manifestInfo.ManifestPath -BackendConfig $BackendConfig -WhatIf:$WhatIfPreference }
        'Azure' { return Start-WSAzureBatchJob -ManifestPath $manifestInfo.ManifestPath -BackendConfig $BackendConfig -WhatIf:$WhatIfPreference }
        'GCP'   { return Start-WSGcpBatchJob -ManifestPath $manifestInfo.ManifestPath -BackendConfig $BackendConfig -WhatIf:$WhatIfPreference }
    }
}

function Get-HPCJobStatus {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $JobId,
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [hashtable] $BackendConfig = @{}
    )

    switch ($Provider) {
        'Local' {
            Get-Job -Name $JobId -ErrorAction SilentlyContinue
        }
        'AWS' {
            if (-not (Test-WSCommand -Name 'aws')) { throw 'AWS CLI not found.' }
            Invoke-WSNative -FilePath 'aws' -ArgumentList @('batch', 'describe-jobs', '--jobs', $JobId, '--output', 'json')
        }
        'Azure' {
            if (-not (Test-WSCommand -Name 'az')) { throw 'Azure CLI not found.' }
            Invoke-WSNative -FilePath 'az' -ArgumentList @('batch', 'job', 'show', '--job-id', $JobId)
        }
        'GCP' {
            if (-not (Test-WSCommand -Name 'gcloud')) { throw 'gcloud CLI not found.' }
            $region = if ($BackendConfig.ContainsKey('Region')) { [string]$BackendConfig.Region } else { $env:WORKSTATION_GCP_REGION }
            Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('batch', 'jobs', 'describe', $JobId, '--location', $region)
        }
    }
}

function Stop-HPCJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $JobId,
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [hashtable] $BackendConfig = @{}
    )

    if (-not $PSCmdlet.ShouldProcess($JobId, "Stop $Provider job")) { return }

    switch ($Provider) {
        'Local' {
            Get-Job -Name $JobId -ErrorAction SilentlyContinue | Stop-Job
        }
        'AWS' {
            Invoke-WSNative -FilePath 'aws' -ArgumentList @('batch', 'terminate-job', '--job-id', $JobId, '--reason', 'Stopped from PowerShell workstation')
        }
        'Azure' {
            Invoke-WSNative -FilePath 'az' -ArgumentList @('batch', 'job', 'terminate', '--job-id', $JobId)
        }
        'GCP' {
            $region = if ($BackendConfig.ContainsKey('Region')) { [string]$BackendConfig.Region } else { $env:WORKSTATION_GCP_REGION }
            Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('batch', 'jobs', 'delete', $JobId, '--location', $region, '--quiet')
        }
    }
}

# -----------------------------------------------------------------------------
# 7. Simulation, rendering, and scientific pipeline functions
# -----------------------------------------------------------------------------

function Submit-Simulation {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $InputPath,
        [Parameter(Mandatory)] [string] $Solver,
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [string] $Name = $(Split-Path -LeafBase $InputPath),
        [int] $Nodes = 1,
        [string] $Gpu = 'none',
        [int] $CpuPerNode = 1,
        [int] $MemoryGB = 4,
        [hashtable] $Parameters = @{},
        [hashtable] $BackendConfig = @{},
        [switch] $Submit
    )

    $resolvedInput = Resolve-WSPath -Path $InputPath
    $simulationDir = New-WSDirectory -Path (Join-Path $script:WS.Pipelines "Simulation/$Name")
    $paramPath = Join-Path $simulationDir 'parameters.json'
    $wrapperPath = Join-Path $simulationDir 'run-simulation.ps1'

    $Parameters | ConvertTo-Json -Depth 12 | Set-Content -Path $paramPath -Encoding utf8

    $lines = @(
        'Set-StrictMode -Version Latest',
        '$ErrorActionPreference = ''Stop''',
        "Write-Host 'Simulation started: $Name'",
        "Write-Host 'Input: $resolvedInput'",
        "Write-Host 'Parameters: $paramPath'",
        "& $(ConvertTo-WSSingleQuotedString $Solver) $(ConvertTo-WSSingleQuotedString $resolvedInput)"
    )
    $lines | Set-Content -Path $wrapperPath -Encoding utf8

    Start-HPCJob -Script $wrapperPath -Name "sim-$Name" -Provider $Provider -Nodes $Nodes -Gpu $Gpu -CpuPerNode $CpuPerNode -MemoryGB $MemoryGB -BackendConfig $BackendConfig -Metadata @{ Type = 'Simulation'; InputPath = $resolvedInput; ParameterPath = $paramPath } -Submit:$Submit -WhatIf:$WhatIfPreference
}

function Start-RenderJob {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $Scene,
        [ValidateSet('Blender', 'Unreal', 'Omniverse')] [string] $Renderer = 'Blender',
        [int[]] $Frames = @(1),
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [string] $Gpu = 'auto',
        [string] $ContainerImage,
        [hashtable] $BackendConfig = @{},
        [switch] $Submit
    )

    $scenePath = Resolve-WSPath -Path $Scene
    $name = Split-Path -LeafBase $Scene
    $renderDir = New-WSDirectory -Path (Join-Path $script:WS.Pipelines "Rendering/$name")
    $wrapperPath = Join-Path $renderDir 'run-render.ps1'

    $frameList = ($Frames | Sort-Object -Unique)
    $rendererCommand = switch ($Renderer) {
        'Blender' {
            $blender = if ($BackendConfig.ContainsKey('BlenderPath')) { [string]$BackendConfig.BlenderPath } else { 'blender' }
            $commands = foreach ($frame in $frameList) {
                "& $(ConvertTo-WSSingleQuotedString $blender) -b $(ConvertTo-WSSingleQuotedString $scenePath) -f $frame"
            }
            $commands -join [Environment]::NewLine
        }
        'Unreal' {
            "throw 'Define Unreal render command in -BackendConfig @{ CommandLine = ... } or customize $wrapperPath.'"
        }
        'Omniverse' {
            "throw 'Define Omniverse render command in -BackendConfig @{ CommandLine = ... } or customize $wrapperPath.'"
        }
    }

    if ($BackendConfig.ContainsKey('CommandLine')) {
        $rendererCommand = [string]$BackendConfig.CommandLine
    }

    $lines = @(
        'Set-StrictMode -Version Latest',
        '$ErrorActionPreference = ''Stop''',
        "Write-Host 'Render started: $name'",
        "Write-Host 'Renderer: $Renderer'",
        "Write-Host 'Scene: $scenePath'",
        $rendererCommand
    )
    $lines | Set-Content -Path $wrapperPath -Encoding utf8

    Start-HPCJob -Script $wrapperPath -Name "render-$name" -Provider $Provider -Nodes 1 -Gpu $Gpu -CpuPerNode 4 -MemoryGB 16 -ContainerImage $ContainerImage -BackendConfig $BackendConfig -Metadata @{ Type = 'Render'; Renderer = $Renderer; Scene = $scenePath; Frames = $frameList } -Submit:$Submit -WhatIf:$WhatIfPreference
}

function Start-RenderFarm {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [string] $Name = 'render-farm',
        [int] $Workers = 2,
        [string] $Gpu = 'auto',
        [string] $ContainerImage,
        [hashtable] $BackendConfig = @{},
        [switch] $Submit
    )

    $farmDir = New-WSDirectory -Path (Join-Path $script:WS.Pipelines "Rendering/$Name")
    $bootstrapPath = Join-Path $farmDir 'start-render-farm.ps1'

    $lines = @(
        'Set-StrictMode -Version Latest',
        '$ErrorActionPreference = ''Stop''',
        "Write-Host 'Render farm bootstrap: $Name'",
        "Write-Host 'Workers: $Workers'",
        "Write-Host 'GPU: $Gpu'",
        "Write-Host 'Customize this bootstrap script for Blender, Unreal, or Omniverse worker registration.'"
    )
    $lines | Set-Content -Path $bootstrapPath -Encoding utf8

    Start-HPCJob -Script $bootstrapPath -Name $Name -Provider $Provider -Nodes $Workers -Gpu $Gpu -CpuPerNode 4 -MemoryGB 16 -ContainerImage $ContainerImage -BackendConfig $BackendConfig -Metadata @{ Type = 'RenderFarm'; Workers = $Workers } -Submit:$Submit -WhatIf:$WhatIfPreference
}

function Invoke-ScientificPipeline {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $Path,
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [string] $Stage = 'default',
        [int] $Nodes = 1,
        [string] $Gpu = 'none',
        [hashtable] $BackendConfig = @{},
        [switch] $Submit
    )

    $pipelinePath = Resolve-WSPath -Path $Path
    $scriptPath = if ((Get-Item -LiteralPath $pipelinePath).PSIsContainer) {
        Join-Path $pipelinePath 'pipeline.ps1'
    } else {
        $pipelinePath
    }

    if (-not (Test-Path -LiteralPath $scriptPath)) { throw "Pipeline script not found: $scriptPath" }

    Start-HPCJob -Script $scriptPath -Name "pipeline-$Stage" -Provider $Provider -Nodes $Nodes -Gpu $Gpu -BackendConfig $BackendConfig -Metadata @{ Type = 'ScientificPipeline'; Stage = $Stage; Path = $pipelinePath } -Submit:$Submit -WhatIf:$WhatIfPreference
}

function Get-GPUClusterStatus {
    [CmdletBinding()]
    param(
        [ValidateSet('Azure', 'AWS', 'GCP', 'Local')] [string] $Provider = $script:WSState.ActiveCloud,
        [hashtable] $BackendConfig = @{}
    )

    switch ($Provider) {
        'Local' {
            [pscustomobject]@{
                Provider = 'Local'
                Hostname = $env:COMPUTERNAME
                GPUInfo = if (Test-WSCommand -Name 'nvidia-smi') { (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>$null) } else { 'nvidia-smi not available' }
            }
        }
        'Azure' {
            if (-not (Test-WSCommand -Name 'az')) { throw 'Azure CLI not found.' }
            if ($BackendConfig.ContainsKey('ResourceGroup')) {
                Invoke-WSNative -FilePath 'az' -ArgumentList @('vm', 'list', '--resource-group', [string]$BackendConfig.ResourceGroup, '--show-details', '--output', 'table')
            } else {
                throw 'Azure status requires -BackendConfig @{ ResourceGroup = "..." }.'
            }
        }
        'AWS' {
            if (-not (Test-WSCommand -Name 'aws')) { throw 'AWS CLI not found.' }
            Invoke-WSNative -FilePath 'aws' -ArgumentList @('ec2', 'describe-instances', '--filters', 'Name=instance-state-name,Values=running', '--output', 'table')
        }
        'GCP' {
            if (-not (Test-WSCommand -Name 'gcloud')) { throw 'gcloud CLI not found.' }
            Invoke-WSNative -FilePath 'gcloud' -ArgumentList @('compute', 'instances', 'list')
        }
    }
}

# -----------------------------------------------------------------------------
# 8. Daily automation and development session functions
# -----------------------------------------------------------------------------

function Test-Workstation {
    [CmdletBinding()]
    param()

    $moduleNames = @(
        'PSReadLine', 'PSScriptAnalyzer', 'PowerShellGet', 'Microsoft.PowerShell.PSResourceGet',
        'Microsoft.PowerShell.SecretManagement', 'Microsoft.PowerShell.SecretStore', 'Pester', 'PlatyPS',
        'PSFzf', 'Terminal-Icons', 'posh-git', 'Az.Accounts', 'AWS.Tools.Common', 'GoogleCloud'
    )

    $cliNames = @('git', 'docker', 'az', 'aws', 'gcloud', 'kubectl', 'code', 'python', 'pwsh')

    $modules = foreach ($name in $moduleNames) {
        $module = Get-Module -ListAvailable -Name $name | Sort-Object Version -Descending | Select-Object -First 1
        [pscustomobject]@{
            Type      = 'Module'
            Name      = $name
            Available = [bool]$module
            Version   = if ($module) { [string]$module.Version } else { $null }
            Path      = if ($module) { $module.Path } else { $null }
        }
    }

    $commands = foreach ($name in $cliNames) {
        $command = Get-Command -Name $name -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Type      = 'Command'
            Name      = $name
            Available = [bool]$command
            Version   = $null
            Path      = if ($command) { $command.Source } else { $null }
        }
    }

    $runtime = [pscustomobject]@{
        Type      = 'Runtime'
        Name      = 'PowerShell'
        Available = $true
        Version   = [string]$PSVersionTable.PSVersion
        Path      = $PSHOME
    }

    @($runtime) + $modules + $commands
}

function Invoke-WorkstationLint {
    [CmdletBinding()]
    param([string] $Path = $script:WS.Root)

    if (-not (Import-WSModule -Name 'PSScriptAnalyzer' -Required)) { return }
    Invoke-ScriptAnalyzer -Path $Path -Recurse
}

function Invoke-WorkstationTests {
    [CmdletBinding()]
    param([string] $Path = $script:WS.Root)

    if (-not (Import-WSModule -Name 'Pester' -Required)) { return }
    Invoke-Pester -Path $Path
}

function Generate-ModuleDocs {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Module,
        [string] $OutputPath = $(Join-Path $script:WS.Reports "Docs/$Module")
    )

    if (-not (Import-WSModule -Name 'PlatyPS' -Required)) { return }
    New-WSDirectory -Path $OutputPath | Out-Null
    New-MarkdownHelp -Module $Module -OutputFolder $OutputPath -Force
}

function Sync-Projects {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string] $Root = $script:WS.Projects,
        [switch] $IncludeSubmodules
    )

    if (-not (Test-WSCommand -Name 'git')) { throw 'git was not found in PATH.' }
    if (-not (Test-Path -LiteralPath $Root)) { throw "Project root not found: $Root" }

    $repos = Get-ChildItem -Path $Root -Directory -Force | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '.git') }
    foreach ($repo in $repos) {
        if ($PSCmdlet.ShouldProcess($repo.FullName, 'git pull --ff-only')) {
            & git -C $repo.FullName pull --ff-only
            if ($IncludeSubmodules) { & git -C $repo.FullName submodule update --init --recursive }
        }
    }
}

function Backup-Workspace {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string] $Destination = $(Join-Path $script:WSHome ('pwsh-workstation-backup-{0}.zip' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))),
        [switch] $IncludeSecrets
    )

    $root = Resolve-WSPath -Path $script:WS.Root
    $secretRoot = Resolve-WSPath -Path $script:WS.Secrets
    $items = Get-ChildItem -Path $root -Recurse -Force | Where-Object {
        $IncludeSecrets -or -not $_.FullName.StartsWith($secretRoot)
    }

    if ($PSCmdlet.ShouldProcess($Destination, 'Create workstation backup archive')) {
        Compress-Archive -Path $items.FullName -DestinationPath $Destination -Force
        Get-Item -LiteralPath $Destination
    }
}

function Generate-Reports {
    [CmdletBinding()]
    param([string] $OutputPath = $(Join-Path $script:WS.Reports ('workstation-report-{0}.md' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))))

    $report = New-Object System.Collections.Generic.List[string]
    $report.Add('# PowerShell Workstation Report')
    $report.Add('')
    $report.Add(('Generated: {0}' -f (Get-Date).ToString('o')))
    $report.Add(('PowerShell: {0}' -f $PSVersionTable.PSVersion))
    $report.Add(('Root: {0}' -f $script:WS.Root))
    $report.Add(('Cloud: {0}' -f $script:WSState.CloudSummary))
    $report.Add('')
    $report.Add('## Components')
    $report.Add('')
    $report.Add('| Type | Name | Available | Version | Path |')
    $report.Add('|---|---|---:|---|---|')

    foreach ($component in Test-Workstation) {
        $report.Add('| {0} | {1} | {2} | {3} | {4} |' -f $component.Type, $component.Name, $component.Available, $component.Version, ($component.Path -replace '\|', '\|'))
    }

    $report | Set-Content -Path $OutputPath -Encoding utf8
    Get-Item -LiteralPath $OutputPath
}

function Invoke-DailyMaintenance {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [switch] $UpdateModules,
        [switch] $RunTests,
        [switch] $RunLint,
        [switch] $PruneDocker,
        [switch] $GenerateReport
    )

    Write-Host 'Workstation health:' -ForegroundColor Cyan
    Test-Workstation | Format-Table -AutoSize

    if ($RunLint) { Invoke-WorkstationLint }
    if ($RunTests) { Invoke-WorkstationTests }

    if ($UpdateModules) {
        if ($PSCmdlet.ShouldProcess('Installed modules', 'Update-Module')) {
            Get-Module -ListAvailable | Select-Object -ExpandProperty Name -Unique | ForEach-Object {
                try { Update-Module -Name $_ -ErrorAction Stop } catch { }
            }
        }
    }

    if ($PruneDocker) {
        if (-not (Test-WSCommand -Name 'docker')) { Write-Warning 'docker was not found.' }
        elseif ($PSCmdlet.ShouldProcess('Docker system', 'docker system prune --force')) {
            Invoke-WSNative -FilePath 'docker' -ArgumentList @('system', 'prune', '--force')
        }
    }

    if ($GenerateReport) { Generate-Reports }
}

function Start-DevSession {
    [CmdletBinding()]
    param(
        [string] $Project = $script:WS.Projects,
        [switch] $OpenVSCode
    )

    New-WSDirectory -Path $Project | Out-Null
    Set-Location -LiteralPath $Project
    Test-Workstation | Where-Object { $_.Type -eq 'Command' -and $_.Name -in @('git', 'docker', 'code') } | Format-Table -AutoSize

    if ($OpenVSCode -and (Test-WSCommand -Name 'code')) {
        & code $Project
    }
}

function Start-EngineeringSession {
    [CmdletBinding()]
    param(
        [ValidateSet('Local', 'Azure', 'AWS', 'GCP')] [string] $Provider = 'Local',
        [string] $Project = $script:WS.Projects
    )

    Set-WSActiveCloud -Provider $Provider | Out-Null
    Start-DevSession -Project $Project
    Write-Host 'Engineering commands: Start-HPCJob, Submit-Simulation, Start-RenderJob, Invoke-ScientificPipeline, Get-GPUClusterStatus' -ForegroundColor Cyan
}

# -----------------------------------------------------------------------------
# 9. Container and AI helper layer
# -----------------------------------------------------------------------------

function Invoke-ContainerTask {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] [string] $Image,
        [string[]] $Command = @(),
        [string] $Workdir = $PWD.Path,
        [string[]] $Volume = @(),
        [switch] $Remove
    )

    if (-not (Test-WSCommand -Name 'docker')) { throw 'docker was not found in PATH.' }

    $args = @('run')
    if ($Remove) { $args += '--rm' }
    $args += @('-v', "${Workdir}:/workspace", '-w', '/workspace')
    foreach ($volumeSpec in $Volume) { $args += @('-v', $volumeSpec) }
    $args += $Image
    $args += $Command

    if ($PSCmdlet.ShouldProcess($Image, 'Run container task')) {
        Invoke-WSNative -FilePath 'docker' -ArgumentList $args
    }
}

function Get-ContainerStatus {
    [CmdletBinding()]
    param()

    if (-not (Test-WSCommand -Name 'docker')) { throw 'docker was not found in PATH.' }
    Invoke-WSNative -FilePath 'docker' -ArgumentList @('ps', '--format', 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}')
}

function Invoke-AICompletion {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromPipeline, Mandatory)] [string] $Prompt,
        [string] $Endpoint = $env:WORKSTATION_AI_ENDPOINT,
        [string] $Model = $env:WORKSTATION_AI_MODEL,
        [string] $ApiKeySecretName = $env:WORKSTATION_AI_SECRET_NAME,
        [hashtable] $ExtraBody = @{}
    )

    begin { $chunks = New-Object System.Collections.Generic.List[string] }
    process { $chunks.Add($Prompt) }
    end {
        if ([string]::IsNullOrWhiteSpace($Endpoint)) {
            throw 'Set WORKSTATION_AI_ENDPOINT to your AI gateway endpoint before calling Invoke-AICompletion.'
        }

        $text = $chunks -join [Environment]::NewLine
        $apiKey = $env:WORKSTATION_AI_API_KEY
        if (-not $apiKey -and $ApiKeySecretName) {
            $apiKey = Get-WorkstationSecret -Name $ApiKeySecretName -AsPlainText
        }

        $headers = @{}
        if ($apiKey) { $headers['Authorization'] = "Bearer $apiKey" }

        $body = @{
            model = $Model
            input = $text
        }
        foreach ($key in $ExtraBody.Keys) { $body[$key] = $ExtraBody[$key] }

        Invoke-RestMethod -Uri $Endpoint -Method Post -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 12)
    }
}

function Invoke-AIExplain {
    [CmdletBinding()]
    param([Parameter(Mandatory, ValueFromPipeline)] [string] $Text)

    process {
        "Explain the following clearly and practically:`n`n$Text" | Invoke-AICompletion
    }
}

function Invoke-AIPlan {
    [CmdletBinding()]
    param([Parameter(Mandatory, ValueFromPipeline)] [string] $Goal)

    process {
        "Create a deterministic, testable engineering plan for this goal:`n`n$Goal" | Invoke-AICompletion
    }
}

function Invoke-AIRefactor {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)

    $resolved = Resolve-WSPath -Path $Path
    $content = Get-Content -Raw -Path $resolved
    "Refactor this PowerShell code. Preserve behavior and explain the changes:`n`n$content" | Invoke-AICompletion
}

# -----------------------------------------------------------------------------
# 10. Startup pipeline and local overlay
# -----------------------------------------------------------------------------

function Initialize-WorkstationStartup {
    [CmdletBinding()]
    param([switch] $Quiet)

    Initialize-WorkstationModules -Quiet:$Quiet
    Initialize-WSUI
    Update-WSCloudSummary

    $overlay = Join-Path $script:WS.Profiles 'PowerShell_workstation_profile.local.ps1'
    if (Test-Path -LiteralPath $overlay) {
        try { . $overlay } catch { Write-Warning "Local overlay failed: $($_.Exception.Message)" }
    }

    if (-not $Quiet) { Show-WorkstationBanner }
}

# Aliases: short cockpit commands.
Set-Alias -Name ws-test -Value Test-Workstation -Scope Global
Set-Alias -Name ws-report -Value Generate-Reports -Scope Global
Set-Alias -Name ws-maintain -Value Invoke-DailyMaintenance -Scope Global
Set-Alias -Name hpc -Value Start-HPCJob -Scope Global
Set-Alias -Name sim -Value Submit-Simulation -Scope Global
Set-Alias -Name render -Value Start-RenderJob -Scope Global
Set-Alias -Name gpu-status -Value Get-GPUClusterStatus -Scope Global

Initialize-WorkstationStartup -Quiet:($env:WORKSTATION_QUIET_STARTUP -eq '1')
