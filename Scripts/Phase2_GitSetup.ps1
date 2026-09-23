<#
.SYNOPSIS
    Phase 2 - Git + Git LFS bootstrap and verification for the MyProject Unreal project.
.DESCRIPTION
    Safety-first, idempotent helper script.

    Modes (default = report only, changes NOTHING):
      (no switch)       verification report only
      -DryRun           preview every action, change nothing
      -InitRepository   create the repository (git init --separate-git-dir)
      -StageAndCommit   git add + baseline commit (aborts when something unexpected shows up)

    Guarantees
      * never deletes, moves or renames a file
      * never writes .uasset / .umap content
      * never edits Config/, Blueprints, levels or the .uproject
      * never adds a remote, never pushes
      * aborts (instead of guessing) when an unexpected file would be staged

.PARAMETER ProjectRoot
    Absolute path of the Unreal project (working tree).
.PARAMETER GitDir
    Absolute path of the repository metadata OUTSIDE OneDrive (separate git dir).
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Scripts\Phase2_GitSetup.ps1 -DryRun
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Scripts\Phase2_GitSetup.ps1 -InitRepository
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Scripts\Phase2_GitSetup.ps1 -StageAndCommit
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot   = 'C:\Users\azize\OneDrive\Belgeler\Unreal Projects\MyProject',
    [string]$GitDir        = 'C:\Dev\UnrealRepos\MyProject.git',
    [string]$Branch        = 'main',
    [string]$CommitMessage = 'chore(baseline): UE 5.8.3 First Person template + Game skeleton + Phase 1 tooling',
    [int]   $ExpectedMinFiles = 270,
    [switch]$DryRun,
    [switch]$InitRepository,
    [switch]$StageAndCommit
)

$ErrorActionPreference = 'Stop'
$script:Failures = New-Object System.Collections.ArrayList
$script:Notes    = New-Object System.Collections.ArrayList

function Say  { param($m) Write-Host ("`n== " + $m) }
function Ok   { param($m) Write-Host ("   [OK]   " + $m) }
function Info { param($m) Write-Host ("   [info] " + $m) }
function Skip { param($m) Write-Host ("   [skip] " + $m) }
function Warn { param($m) Write-Host ("   [WARN] " + $m); [void]$script:Notes.Add($m) }
function Fail { param($m) Write-Host ("   [FAIL] " + $m) -ForegroundColor Red; [void]$script:Failures.Add($m) }

function Rel { param($full) ($full.Substring($ProjectRoot.Length).TrimStart('\', '/')) -replace '\\', '/' }

# Prints and returns $true in dry-run mode so callers can skip the real work.
function DryLabel { param($what) if ($DryRun) { Skip ("DRY-RUN, not executed: " + $what); return $true } return $false }

function Invoke-Git {
    param([string[]]$Arguments, [switch]$AllowFailure)
    $output = & git -C $ProjectRoot @Arguments 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) { Fail ("git " + ($Arguments -join ' ') + " -> exit code " + $code) }
    return @{ Output = @($output); Code = $code }
}

# ----------------------------------------------------------------- preflight
Say 'Preflight'
if (-not (Test-Path -LiteralPath $ProjectRoot)) { Fail ('project root not found: ' + $ProjectRoot) }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'MyProject.uproject'))) { Fail 'MyProject.uproject not found in the project root' }
if ($script:Failures.Count -gt 0) { Write-Host ''; Write-Host 'Aborting: preflight failed.'; exit 1 }
Ok ('project root : ' + $ProjectRoot)

$editor = @(Get-Process -Name UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue)
$editorClosed = ($editor.Count -eq 0)
if ($editorClosed) { Ok 'Unreal Editor is closed' }
else {
    $ids = ($editor | ForEach-Object { $_.Id }) -join ','
    if ($InitRepository -or $StageAndCommit -or $DryRun) { Fail ("Unreal Editor is running (PID: " + $ids + "). Close it before git operations.") }
    else { Warn ("Unreal Editor is running (PID: " + $ids + "). Verification only, no git write attempted.") }
}

# ------------------------------------------------- required workspace files
Say 'Required workspace files'
$gitAttributesPath = Join-Path $ProjectRoot '.gitattributes'
$gitIgnorePath     = Join-Path $ProjectRoot '.gitignore'

foreach ($file in @($gitAttributesPath, $gitIgnorePath)) {
    if (Test-Path -LiteralPath $file) { Ok ('present: ' + (Split-Path $file -Leaf)) }
    else { Fail ('missing: ' + $file) }
}
if (Test-Path -LiteralPath $gitAttributesPath) {
    $lfsRules = @(Select-String -LiteralPath $gitAttributesPath -Pattern 'filter=lfs' -SimpleMatch)
    if ($lfsRules.Count -ge 2) { Ok ('.gitattributes declares ' + $lfsRules.Count + ' Git LFS rules') }
    else { Fail '.gitattributes does not declare the expected Git LFS rules' }
}
if (Test-Path -LiteralPath $gitIgnorePath) {
    foreach ($pattern in @('Binaries/', 'DerivedDataCache/', 'Intermediate/', 'Saved/')) {
        $hit = @(Select-String -LiteralPath $gitIgnorePath -Pattern ("^" + [regex]::Escape($pattern)))
        if ($hit.Count -eq 1) { Ok ('ignore rule present: ' + $pattern) }
        else { Fail ('ignore rule missing or duplicated: ' + $pattern) }
    }
}

# ------------------------------------------------------ .gitkeep placeholders
Say 'Empty folder placeholders (.gitkeep)'
$gameRoot = Join-Path $ProjectRoot 'Content\Game'
if (Test-Path -LiteralPath $gameRoot) {
    $folders = @(Get-ChildItem -LiteralPath $gameRoot -Recurse -Force -Directory)
    $missing = @($folders | Where-Object { -not (Test-Path -LiteralPath (Join-Path $_.FullName '.gitkeep')) })
    if ($missing.Count -eq 0) { Ok ($folders.Count.ToString() + ' /Game/Game folders already contain .gitkeep') }
    elseif (DryLabel ($missing.Count.ToString() + ' .gitkeep files')) { }
    else {
        foreach ($folder in $missing) {
            Set-Content -LiteralPath (Join-Path $folder.FullName '.gitkeep') -Encoding ASCII `
                -Value 'Placeholder so this empty /Game/Game folder is tracked by Git. Safe to delete once real assets exist here.'
        }
        Ok ($missing.Count.ToString() + ' .gitkeep files created')
    }
}
else { Fail ('folder not found: ' + $gameRoot) }

# -------------------------------------------------------------- inventory
Say 'Project inventory'
$allFiles = @(Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Force -File)
$assets   = @($allFiles | Where-Object { $_.Extension -in @('.uasset', '.umap') })
Ok ('files total   : ' + $allFiles.Count)
Ok ('uasset + umap : ' + $assets.Count + '  (' + [math]::Round((($assets | Measure-Object Length -Sum).Sum / 1MB), 2) + ' MB)')

# --------------------------------------------------------------- repository
Say 'Repository'
$gitEntry    = Join-Path $ProjectRoot '.git'
$initialised = (Test-Path -LiteralPath $gitEntry)
if ($initialised) {
    $isDirectory = (Get-Item -LiteralPath $gitEntry -Force).PSIsContainer
    if ($isDirectory) { Info '.git is a DIRECTORY (repository metadata inside the project folder)' }
    else {
        $pointer = (Get-Content -LiteralPath $gitEntry -TotalCount 1)
        Info ('.git is a FILE (gitdir pointer): ' + $pointer)
        if ($pointer -match '^gitdir:') { Ok 'gitdir pointer file is valid' }
        else { Fail '.git pointer file does not start with "gitdir:"' }
    }
    $resolved = Invoke-Git @('rev-parse', '--git-dir') -AllowFailure
    if ($resolved.Code -eq 0) { Ok ('resolved git dir: ' + ($resolved.Output -join ' ')) }
    else { Fail 'git rev-parse --git-dir failed - repository is not usable' }
    if (Test-Path -LiteralPath $GitDir) { Ok ('external git dir exists: ' + $GitDir) }
    else { Warn ('external git dir not found: ' + $GitDir) }
}
else {
    Info 'repository is not initialised yet'
    if ($InitRepository) {
        if (DryLabel ('git init --separate-git-dir="' + $GitDir + '" -b ' + $Branch)) { }
        elseif (-not $editorClosed) { Fail 'Unreal Editor is running - refusing to create the repository' }
        else {
            $parent = Split-Path $GitDir -Parent
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
                Ok ('created parent folder: ' + $parent)
            }
            $init = Invoke-Git @('init', ('--separate-git-dir=' + $GitDir), '-b', $Branch)
            if ($init.Code -eq 0) { Ok 'repository initialised (working tree in OneDrive, metadata outside)' }
            $initialised = (Test-Path -LiteralPath $gitEntry)
        }
    }
    else { Skip 'use -InitRepository to create the repository' }
}

# ----------------------------------------------------------------- git lfs
Say 'Git LFS (repository scope)'
$lfsVersion = ((& git lfs version 2>&1) -join ' ')
Ok ('installed: ' + $lfsVersion)
if ($initialised) {
    if (DryLabel 'git lfs install --local') { }
    else {
        $lfsInstall = Invoke-Git @('lfs', 'install', '--local')
        if ($lfsInstall.Code -eq 0) { Ok 'LFS filters/hooks enabled for this repository' }
    }
    if (DryLabel 'git config --local core.longpaths true') { }
    else {
        $longPaths = Invoke-Git @('config', '--local', 'core.longpaths', 'true')
        if ($longPaths.Code -eq 0) { Ok 'core.longpaths=true (repository scope)' }
    }
}
else { Skip 'repository not available yet' }

# ----------------------------------------------------- attribute verification
Say 'Attribute verification (.uasset / .umap must resolve to LFS)'
if ($initialised) {
    $samples = @()
    $umapSample  = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'Content') -Recurse -Force -File -Filter '*.umap' | Select-Object -First 1)
    $assetSample = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'Content') -Recurse -Force -File -Filter '*.uasset' | Select-Object -First 1)
    if ($umapSample.Count -gt 0)  { $samples += $umapSample[0].FullName }
    if ($assetSample.Count -gt 0) { $samples += $assetSample[0].FullName }
    $samples += (Join-Path $ProjectRoot 'MyProject.uproject')
    foreach ($sample in $samples) {
        $relPath = Rel $sample
        $attrs = ((& git -C $ProjectRoot check-attr filter diff merge text -- $relPath 2>&1) -join ' ')
        Info ($relPath + '  =>  ' + $attrs)
        if ($relPath -match '\.(uasset|umap)$') {
            if ($attrs -notmatch 'filter: lfs') { Fail ('LFS filter NOT applied to ' + $relPath) }
            if ($attrs -notmatch 'text: unset') { Fail ('text conversion NOT disabled for ' + $relPath) }
        }
    }
}
else { Skip 'repository not initialised' }

# -------------------------------------------------------- ignore verification
Say 'Ignore verification'
if ($initialised) {
    foreach ($directory in @('Binaries', 'DerivedDataCache', 'Intermediate', 'Saved')) {
        $probe = $directory + '/probe.txt'
        $result = ((& git -C $ProjectRoot check-ignore -v $probe 2>&1) -join ' ')
        if ($LASTEXITCODE -eq 0) { Ok ('ignored: ' + $result) }
        else { Warn ('NOT ignored: ' + $probe) }
    }
    $statusLines = @(& git -C $ProjectRoot status --porcelain --ignored 2>&1)
    $ignoredEntries   = @($statusLines | Where-Object { $_ -match '^!! ' })
    $untrackedEntries = @($statusLines | Where-Object { $_ -match '^\?\? ' })
    Info ('ignored entries: ' + $ignoredEntries.Count + '   untracked entries: ' + $untrackedEntries.Count)
}
else { Skip 'repository not initialised' }

# ------------------------------------------------------------ staging preview
Say 'Staging preview'
if ($initialised) {
    $dryOutput = @(& git -C $ProjectRoot add --dry-run . 2>&1)
    $wouldAdd  = @($dryOutput | Where-Object { $_ -match "^add '" })
    Info ('git add --dry-run -> ' + $wouldAdd.Count + ' file(s) would be staged')
    $forbidden = @($wouldAdd | Where-Object { $_ -match '(Binaries|DerivedDataCache|Intermediate|Saved)/' })
    if ($forbidden.Count -gt 0) {
        Fail ('FORBIDDEN paths would be staged: ' + $forbidden.Count)
        $forbidden | Select-Object -First 10 | ForEach-Object { Write-Host ('      ! ' + $_) }
    }
    else { Ok 'no Binaries / DerivedDataCache / Intermediate / Saved path in the preview' }

    $bytes = 0
    foreach ($line in $wouldAdd) {
        $relPath = ($line -replace "^add '", '') -replace "'$", ''
        $fullPath = Join-Path $ProjectRoot ($relPath -replace '/', '\')
        if (Test-Path -LiteralPath $fullPath) { $bytes += (Get-Item -LiteralPath $fullPath).Length }
    }
    Info ('total size of the files to be staged: ' + [math]::Round($bytes / 1MB, 2) + ' MB')
}
else { Skip 'repository not initialised' }

# ------------------------------------------------------------ stage + commit
Say 'Stage and commit'
if (-not $StageAndCommit) { Skip 'use -StageAndCommit to create the baseline commit' }
elseif ($DryRun) { Skip 'DRY-RUN: stage/commit not executed' }
elseif (-not $editorClosed) { Fail 'Unreal Editor is running - refusing to commit' }
elseif (-not $initialised) { Fail 'repository not initialised - nothing to commit' }
else {
    $add = Invoke-Git @('add', '.')
    if ($add.Code -eq 0) {
        $staged = @(& git -C $ProjectRoot diff --cached --name-only 2>&1 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        Ok ('staged files: ' + $staged.Count)
        $badDirectory = @($staged | Where-Object { $_ -match '^(Binaries|DerivedDataCache|Intermediate|Saved)/' })
        $badExtension = @($staged | Where-Object {
            $_ -notmatch '\.(uasset|umap|ini|py|ps1|uproject)$' -and
            $_ -notmatch '(^|/)\.git(attributes|ignore)$' -and
            $_ -notmatch '\.gitkeep$' })
        if ($badDirectory.Count -gt 0) { Fail ('GUARD: excluded folders are staged -> ' + ($badDirectory -join ', ')) }
        if ($badExtension.Count -gt 0) { Fail ('GUARD: unexpected file type staged -> ' + (($badExtension | Select-Object -First 10) -join ', ')) }
        if ($staged.Count -lt $ExpectedMinFiles) { Fail ('GUARD: staged count ' + $staged.Count + ' is below the expected minimum ' + $ExpectedMinFiles) }
        if ($script:Failures.Count -gt 0) {
            Warn 'COMMIT SKIPPED. Review the guard failures above, then run: git reset'
        }
        else {
            $commit = Invoke-Git @('commit', '-m', $CommitMessage)
            if ($commit.Code -eq 0) { Ok 'baseline commit created' }
        }
    }
}

# ---------------------------------------------------------------- post checks
Say 'Post checks'
if ($initialised) {
    $lfsFiles  = @(& git -C $ProjectRoot lfs ls-files 2>&1 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $lfsAssets = @($lfsFiles | Where-Object { $_ -match '\.uasset$' })
    $lfsMaps   = @($lfsFiles | Where-Object { $_ -match '\.umap$' })
    Ok ('git lfs ls-files total: ' + $lfsFiles.Count + '   .uasset: ' + $lfsAssets.Count + '   .umap: ' + $lfsMaps.Count)
    $worktreeStatus = @(& git -C $ProjectRoot status --short 2>&1 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($worktreeStatus.Count -eq 0) { Ok 'working tree is clean' }
    else { Info ('git status --short: ' + $worktreeStatus.Count + ' line(s)') }
    $head = ((& git -C $ProjectRoot log -1 --oneline 2>&1) -join ' ')
    if ($head) { Info ('HEAD: ' + $head) }
    @(& git -C $ProjectRoot count-objects -vH 2>&1) | ForEach-Object { Info ([string]$_) }
}

# --------------------------------------------------------------------- report
Say 'Report'
if (-not $DryRun) {
    try {
        $reportDir = Join-Path $ProjectRoot 'Saved\Phase2'
        if (-not (Test-Path -LiteralPath $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $reportPath = Join-Path $reportDir ('phase2_git_setup_' + $stamp + '.txt')
        $lines = New-Object System.Collections.ArrayList
        [void]$lines.Add('Phase 2 - Git + Git LFS setup report')
        [void]$lines.Add('================================================================')
        [void]$lines.Add('timestamp        : ' + (Get-Date -Format 's'))
        [void]$lines.Add('project root     : ' + $ProjectRoot)
        [void]$lines.Add('git dir          : ' + $GitDir)
        [void]$lines.Add('repository ready : ' + $initialised)
        [void]$lines.Add('dry run          : ' + $DryRun)
        [void]$lines.Add('stage and commit : ' + $StageAndCommit)
        [void]$lines.Add('failures         : ' + $script:Failures.Count)
        [void]$lines.Add('warnings         : ' + $script:Notes.Count)
        foreach ($note in $script:Notes) { [void]$lines.Add('  WARN: ' + $note) }
        foreach ($failure in $script:Failures) { [void]$lines.Add('  FAIL: ' + $failure) }
        Set-Content -LiteralPath $reportPath -Value $lines -Encoding ASCII
        Ok ('report written: ' + $reportPath)
    }
    catch { Warn ('could not write report file: ' + $_.Exception.Message) }
}
else { Skip 'DRY-RUN: no report file written' }

Write-Host ''
if ($script:Failures.Count -eq 0) { Write-Host 'PHASE2_RESULT: OK'; exit 0 }
Write-Host ('PHASE2_RESULT: FAILED (' + $script:Failures.Count + ' failure(s))')
exit 1
