$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Quick Repackager - Skipping PyInstaller Recompilation" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$flutterBuildDir = "frontend/flutter_application/build/windows/x64/runner/Release"
$releaseParent = "release_build"
$releaseDir = "release_build/google-takeout-rag"
$backendReleaseDir = "$releaseDir/backend"
$examplesReleaseDir = "$releaseDir/examples"

# Clean old release build folders
if (Test-Path $releaseParent) {
    Write-Host "Terminating any locked processes..." -ForegroundColor Gray
    Stop-Process -Name "app" -Force -ErrorAction SilentlyContinue
    Stop-Process -Name "google-takeout-rag" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    
    Write-Host "Cleaning up old release files..." -ForegroundColor Gray
    Remove-Item -Path $releaseParent -Recurse -Force
}

# Create clean release directory structure
New-Item -ItemType Directory -Force -Path $backendReleaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $examplesReleaseDir | Out-Null

# Copy Flutter binaries
Write-Host "Copying Flutter frontend..." -ForegroundColor Gray
Copy-Item -Path "$flutterBuildDir/*" -Destination $releaseDir -Recurse -Force -Exclude "*.pdb"

# Rename Flutter executable
Write-Host "Renaming executable to google-takeout-rag.exe..." -ForegroundColor Gray
Rename-Item -Path "$releaseDir/flutter_application.exe" -NewName "google-takeout-rag.exe"

# Copy PyInstaller Backend Executable (already compiled in dist/app.exe)
Write-Host "Copying compiled Python backend..." -ForegroundColor Gray
Copy-Item -Path "dist/app.exe" -Destination "$backendReleaseDir/app.exe" -Force

# Copy example CSVs
Write-Host "Copying example CSV datasets..." -ForegroundColor Gray
if (Test-Path "test_search_sample.csv") {
    Copy-Item -Path "test_search_sample.csv" -Destination $examplesReleaseDir -Force
}
if (Test-Path "test_youtube_sample.csv") {
    Copy-Item -Path "test_youtube_sample.csv" -Destination $examplesReleaseDir -Force
}

# Compress to ZIP
$zipPath = "google-takeout-rag.zip"
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Write-Host "Waiting for anti-virus scan (sleeping 5 seconds)..." -ForegroundColor Gray
Start-Sleep -Seconds 5

$maxZipRetries = 6
for ($attempt = 1; $attempt -le $maxZipRetries; $attempt++) {
    try {
        Write-Host "Archiving release files (Attempt $attempt/$maxZipRetries)..." -ForegroundColor Gray
        Compress-Archive -Path $releaseDir -DestinationPath $zipPath -Force
        Write-Host "ZIP Archive created successfully at: $zipPath" -ForegroundColor Green
        break
    }
    catch {
        if ($attempt -eq $maxZipRetries) {
            Write-Error "Failed to archive release files after $maxZipRetries attempts: $_"
        }
        Write-Host "⚠️ Archive failed due to lock. Retrying in 10 seconds..." -ForegroundColor DarkYellow
        Start-Sleep -Seconds 10
    }
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "REPACKAGING COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "Standalone ZIP: d:\GOOGLE_TAKEOUT_RAG\google-takeout-rag.zip" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
