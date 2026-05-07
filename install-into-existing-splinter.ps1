# install-into-existing-splinter.ps1
#
# Refresh toolkit-canonical files in an existing splinter project.
# PowerShell equivalent of install-into-existing-splinter.sh.
#
# Usage: .\install-into-existing-splinter.ps1 -SplinterPath C:\Claude_Code\splinter-foo

param(
    [Parameter(Mandatory=$true)]
    [string]$SplinterPath
)

$ToolkitRoot = $PSScriptRoot

if (-not (Test-Path $SplinterPath -PathType Container)) {
    Write-Error "[FAIL] splinter dir does not exist: $SplinterPath"
    exit 2
}

if (-not (Test-Path "$SplinterPath\book_config.yaml")) {
    Write-Warning "$SplinterPath\book_config.yaml does not exist."
    Write-Warning "This splinter may have been scaffolded with the pre-toolkit pattern."
    Write-Warning "After install, you'll need to write book_config.yaml manually."
    $reply = Read-Host "Continue? [y/N]"
    if ($reply -notmatch '^[Yy]$') {
        Write-Output "[abort]"
        exit 0
    }
}

New-Item -ItemType Directory -Path "$SplinterPath\orchestrator" -Force | Out-Null
New-Item -ItemType Directory -Path "$SplinterPath\references" -Force | Out-Null

Write-Output "[install] orchestrator\run-alpha-reader.py"
Copy-Item "$ToolkitRoot\orchestrator\run-alpha-reader.py" "$SplinterPath\orchestrator\run-alpha-reader.py" -Force

Write-Output "[install] orchestrator\readability_analyzer.py"
Copy-Item "$ToolkitRoot\orchestrator\readability_analyzer.py" "$SplinterPath\orchestrator\readability_analyzer.py" -Force

Write-Output "[install] orchestrator\auth_probe.py"
Copy-Item "$ToolkitRoot\orchestrator\auth_probe.py" "$SplinterPath\orchestrator\auth_probe.py" -Force

Write-Output "[install] references\personas-snapshot-v0.4.md"
Copy-Item "$ToolkitRoot\references\personas-snapshot-v0.4.md" "$SplinterPath\references\personas-snapshot-v0.4.md" -Force

Write-Output ""
Write-Output "INSTALL COMPLETE."
Write-Output ""
Write-Output "  Splinter: $SplinterPath"
Write-Output "  Toolkit:  $ToolkitRoot"
Write-Output ""
Write-Output "Next steps:"
Write-Output "  - If book_config.yaml does not exist, create it from $ToolkitRoot\templates\book_config.yaml.template"
Write-Output "  - Verify with: cd $SplinterPath; py -3.14 orchestrator\auth_probe.py"
Write-Output ""
