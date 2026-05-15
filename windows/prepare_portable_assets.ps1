$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$FfmpegBin = Join-Path $Root "ffmpeg\bin"
$ModelDir = Join-Path $Root "models\faster-whisper-base"
$TempRoot = Join-Path $env:TEMP "ReelsWatermarkToolAssets"

New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

Write-Host "Preparing portable FFmpeg..."
$FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
$FfprobeExe = Join-Path $FfmpegBin "ffprobe.exe"

if ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
    Write-Host "FFmpeg already exists: $FfmpegBin"
} else {
    $ZipPath = Join-Path $TempRoot "ffmpeg-release-essentials.zip"
    $ExtractDir = Join-Path $TempRoot "ffmpeg-release-essentials"
    $Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    if (Test-Path $ExtractDir) {
        Remove-Item $ExtractDir -Recurse -Force
    }

    Write-Host "Downloading FFmpeg essentials build..."
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath

    Write-Host "Extracting FFmpeg..."
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $DownloadedFfmpeg = Get-ChildItem $ExtractDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    $DownloadedFfprobe = Get-ChildItem $ExtractDir -Recurse -Filter "ffprobe.exe" | Select-Object -First 1

    if (-not $DownloadedFfmpeg -or -not $DownloadedFfprobe) {
        throw "FFmpeg archive did not contain ffmpeg.exe and ffprobe.exe."
    }

    Copy-Item $DownloadedFfmpeg.FullName $FfmpegExe -Force
    Copy-Item $DownloadedFfprobe.FullName $FfprobeExe -Force
    Write-Host "FFmpeg copied to: $FfmpegBin"
}

Write-Host "Preparing faster-whisper base model..."
$ModelBin = Join-Path $ModelDir "model.bin"
$ModelConfig = Join-Path $ModelDir "config.json"

if ((Test-Path $ModelBin) -and (Test-Path $ModelConfig)) {
    Write-Host "Base model already exists: $ModelDir"
} else {
    python -m pip install --upgrade huggingface-hub
    python (Join-Path $PSScriptRoot "download_base_model.py") $ModelDir
}

Write-Host "Portable assets are ready."
