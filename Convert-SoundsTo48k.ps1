# ============================================================================
# Convert-SoundsTo48k.ps1 -- oneDiversified World Cup Colour sACN
#
# Resamples every audio file under "Sound Files" (including the Anthems
# subfolder) to a 48 kHz sample rate so playback matches the Dante Virtual
# Soundcard clock that the pygame mixer now opens at (see src/tabs/sounds.py).
#
# - Files already at 48 kHz are skipped.
# - Each file's codec is preserved (mp3 -> mp3, wav -> 16-bit PCM, ogg -> ogg)
#   and the original mp3/ogg bitrate is carried over where possible.
# - Originals are copied to "Sound Files\_pre48k_backup\..." before being
#   overwritten (disable with -NoBackup).
# - The .peak waveform caches do not need touching: the app invalidates them
#   automatically because the rewritten audio file gets a newer timestamp.
#
# Requires ffmpeg + ffprobe on PATH. Install on Windows with:
#     winget install Gyan.FFmpeg
# then open a new terminal so PATH refreshes.
#
# Usage:
#     ./Convert-SoundsTo48k.ps1            # convert in place, keep backups
#     ./Convert-SoundsTo48k.ps1 -WhatIf    # list what would change, do nothing
#     ./Convert-SoundsTo48k.ps1 -NoBackup  # convert without keeping originals
# ============================================================================

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $SoundDir = (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "Sound Files"),
    [int]    $TargetRate = 48000,
    [switch] $NoBackup
)

$ErrorActionPreference = "Stop"

function Write-Section($text) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " $text" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

# ── Locate ffmpeg / ffprobe ──────────────────────────────────────────────────
$ffmpeg  = (Get-Command ffmpeg  -ErrorAction SilentlyContinue).Source
$ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source

if (-not $ffmpeg -or -not $ffprobe) {
    Write-Host ""
    Write-Host "ERROR: ffmpeg/ffprobe not found on PATH." -ForegroundColor Red
    Write-Host "Install it, then re-run this script:" -ForegroundColor Yellow
    Write-Host "    winget install Gyan.FFmpeg" -ForegroundColor White
    Write-Host "    (open a new terminal afterwards so PATH refreshes)" -ForegroundColor DarkGray
    exit 1
}

if (-not (Test-Path $SoundDir)) {
    Write-Host "ERROR: sound folder not found: $SoundDir" -ForegroundColor Red
    exit 1
}

Write-Section "Resample audio to ${TargetRate} Hz"
Write-Host "  Folder : $SoundDir" -ForegroundColor White
Write-Host "  ffmpeg : $ffmpeg"   -ForegroundColor DarkGray
Write-Host "  Backups: $(if ($NoBackup) { 'disabled' } else { 'Sound Files\_pre48k_backup' })" -ForegroundColor DarkGray

$backupRoot = Join-Path $SoundDir "_pre48k_backup"

# ── Gather audio files (skip the backup folder itself) ───────────────────────
$files = Get-ChildItem -Path $SoundDir -Recurse -File -Include *.mp3, *.wav, *.ogg |
    Where-Object { $_.FullName -notlike "$backupRoot*" }

$total     = $files.Count
$converted = 0
$skipped   = 0
$failed    = 0
$i         = 0

Write-Host "  Files  : $total" -ForegroundColor White
Write-Host ""

foreach ($file in $files) {
    $i++
    $rel = $file.FullName.Substring($SoundDir.Length).TrimStart('\', '/')

    # Probe current sample rate
    $rate = (& $ffprobe -v error -select_streams a:0 `
        -show_entries stream=sample_rate -of csv=p=0 "$($file.FullName)") | Select-Object -First 1
    $rate = "$rate".Trim()

    if ($rate -eq "$TargetRate") {
        $skipped++
        Write-Host ("  [{0}/{1}] SKIP  {2}  (already {3} Hz)" -f $i, $total, $rel, $TargetRate) -ForegroundColor DarkGray
        continue
    }

    if (-not $PSCmdlet.ShouldProcess($rel, "resample $rate Hz -> $TargetRate Hz")) {
        continue
    }

    # Probe bitrate so we can preserve it for lossy formats
    $bitrate = (& $ffprobe -v error -select_streams a:0 `
        -show_entries stream=bit_rate -of csv=p=0 "$($file.FullName)") | Select-Object -First 1
    $bitrate = "$bitrate".Trim()

    # Codec-specific encode args
    $ext = $file.Extension.ToLower()
    switch ($ext) {
        ".mp3" {
            $codecArgs = @("-c:a", "libmp3lame")
            if ($bitrate -match '^\d+$') { $codecArgs += @("-b:a", $bitrate) } else { $codecArgs += @("-q:a", "0") }
        }
        ".wav" { $codecArgs = @("-c:a", "pcm_s16le") }
        ".ogg" {
            $codecArgs = @("-c:a", "libvorbis")
            if ($bitrate -match '^\d+$') { $codecArgs += @("-b:a", $bitrate) } else { $codecArgs += @("-q:a", "6") }
        }
        default { $codecArgs = @() }
    }

    $tmp = "$($file.FullName).48k_tmp$ext"

    try {
        & $ffmpeg -hide_banner -loglevel error -y -i "$($file.FullName)" `
            -ar $TargetRate @codecArgs "$tmp"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tmp)) {
            throw "ffmpeg failed (exit $LASTEXITCODE)"
        }

        # Back up the original before overwriting
        if (-not $NoBackup) {
            $backupPath = Join-Path $backupRoot $rel
            $backupDir = Split-Path -Parent $backupPath
            if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }
            Copy-Item -LiteralPath $file.FullName -Destination $backupPath -Force
        }

        # Atomically replace the original with the resampled temp file
        Move-Item -LiteralPath $tmp -Destination $file.FullName -Force
        $converted++
        Write-Host ("  [{0}/{1}] OK    {2}  ({3} Hz -> {4} Hz)" -f $i, $total, $rel, $rate, $TargetRate) -ForegroundColor Green
    }
    catch {
        $failed++
        if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
        Write-Host ("  [{0}/{1}] FAIL  {2}  ({3})" -f $i, $total, $rel, $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Section "Done"
Write-Host "  Converted : $converted" -ForegroundColor Green
Write-Host "  Skipped   : $skipped (already $TargetRate Hz)" -ForegroundColor DarkGray
Write-Host "  Failed    : $failed" -ForegroundColor $(if ($failed) { "Red" } else { "DarkGray" })
if (-not $NoBackup -and $converted -gt 0) {
    Write-Host "  Originals backed up to: $backupRoot" -ForegroundColor White
}
Write-Host ""
