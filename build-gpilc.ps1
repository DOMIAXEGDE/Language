[CmdletBinding()]
param(
    [string] $BuildDirectory = (Join-Path $PSScriptRoot 'build/compiler')
)

$ErrorActionPreference = 'Stop'
$sourceDirectory = Join-Path $PSScriptRoot 'compiler'

& cmake --fresh -S $sourceDirectory -B $BuildDirectory -G Ninja -DCMAKE_CXX_COMPILER=g++
if ($LASTEXITCODE -ne 0) {
    throw "CMake configuration failed with exit code $LASTEXITCODE."
}

& cmake --build $BuildDirectory
if ($LASTEXITCODE -ne 0) {
    throw "GPILC build failed with exit code $LASTEXITCODE."
}

& ctest --test-dir $BuildDirectory --output-on-failure
if ($LASTEXITCODE -ne 0) {
    throw "GPILC tests failed with exit code $LASTEXITCODE."
}

$executable = Join-Path $BuildDirectory 'gpilc.exe'
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Expected compiler output was not found at $executable."
}

Write-Host "GPILC is ready: $executable"
