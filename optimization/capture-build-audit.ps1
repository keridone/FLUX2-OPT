param(
    [string]$Root = "E:\flux",
    [string]$Output = "E:\flux\profiling\build-audit"
)

$ErrorActionPreference = "Stop"
$sdRoot = Join-Path $Root "sdcpp"
$runtime = Join-Path $sdRoot "runtime\sd-cli.exe"
$source = Join-Path $sdRoot "source"
$outputPath = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

& $runtime --version *> (Join-Path $outputPath "version.txt")
& $runtime --help *> (Join-Path $outputPath "help.txt")
Get-ChildItem (Join-Path $sdRoot "runtime") -File |
    Select-Object Name, Length, LastWriteTimeUtc |
    ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 (Join-Path $outputPath "runtime-files.json")
Get-ChildItem (Join-Path $sdRoot "runtime") -File |
    Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash |
    ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 (Join-Path $outputPath "runtime-hashes.json")
nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader |
    Set-Content -Encoding utf8 (Join-Path $outputPath "gpu.txt")

if (Test-Path (Join-Path $source ".git")) {
    git -C $source rev-parse HEAD | Set-Content -Encoding utf8 (Join-Path $outputPath "source-commit.txt")
    git -C $source submodule status --recursive | Set-Content -Encoding utf8 (Join-Path $outputPath "submodules.txt")
    git -C $source status --short | Set-Content -Encoding utf8 (Join-Path $outputPath "source-status.txt")
    Get-ChildItem $source -Filter CMakeCache.txt -Recurse -File |
        ForEach-Object {
            Select-String -Path $_.FullName -Pattern "CUDA|CUBLAS|ARCHITECT|CMAKE_BUILD_TYPE|FLASH|GRAPH|GGML" |
                ForEach-Object { "{0}:{1}" -f $_.Path, $_.Line }
        } | Set-Content -Encoding utf8 (Join-Path $outputPath "cmake-cache-filtered.txt")
}

Write-Output "Build audit saved to $outputPath"
