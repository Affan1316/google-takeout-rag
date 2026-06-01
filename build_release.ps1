# Google Takeout RAG — Standalone Windows Builder Script
# This script compiles the FastAPI backend to an exe, builds the Flutter frontend,
# integrates them into a premium standalone directory, and compresses it to a ZIP archive.

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Starting Standalone Windows Release Package Builder" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Step 1: Validate dependencies and paths
Write-Host "`n[1/5] Verifying environment and tools..." -ForegroundColor Yellow
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found at .\venv. Please create it first."
}

if (-not (Test-Path ".\venv\Scripts\pyinstaller.exe")) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor DarkYellow
    & ".\venv\Scripts\pip.exe" install pyinstaller
}
Write-Host "Environment checked successfully." -ForegroundColor Green

# Step 2: Compile FastAPI backend
Write-Host "`n[2/5] Compiling Python FastAPI backend with PyInstaller..." -ForegroundColor Yellow
Write-Host "Running PyInstaller compilation (this may take a minute)..." -ForegroundColor Gray
& ".\venv\Scripts\pyinstaller.exe" --noconfirm --onefile --name "app" --clean app.py

if (-not (Test-Path "dist/app.exe")) {
    Write-Error "PyInstaller failed: dist/app.exe was not created."
}
Write-Host "FastAPI backend compiled successfully to dist/app.exe" -ForegroundColor Green

# Step 3: Build Flutter desktop frontend
Write-Host "`n[3/5] Compiling Flutter Windows desktop frontend..." -ForegroundColor Yellow
cd "frontend/flutter_application"
& flutter build windows --release
cd "../.."

$flutterBuildDir = "frontend/flutter_application/build/windows/x64/runner/Release"
if (-not (Test-Path "$flutterBuildDir/flutter_application.exe")) {
    Write-Error "Flutter build failed: executable not found."
}
Write-Host "Flutter frontend built successfully in release mode." -ForegroundColor Green

# Step 4: Assemble the premium unified release folder
Write-Host "`n[4/5] Assembling Standalone Unified Release Folder..." -ForegroundColor Yellow
$releaseParent = "release_build"
$releaseDir = "release_build/HistoryAnalyst-Windows-x64"
$backendReleaseDir = "$releaseDir/backend"
$examplesReleaseDir = "$releaseDir/examples"

# Clean old release build folders
if (Test-Path $releaseParent) {
    Write-Host "Cleaning up old release files..." -ForegroundColor Gray
    Remove-Item -Path $releaseParent -Recurse -Force
}

# Create clean release directory structure
New-Item -ItemType Directory -Force -Path $backendReleaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $examplesReleaseDir | Out-Null

# Copy Flutter binaries
Write-Host "Copying Flutter frontend runner..." -ForegroundColor Gray
Copy-Item -Path "$flutterBuildDir/*" -Destination $releaseDir -Recurse -Force -Exclude "*.pdb"

# Rename Flutter executable to user-friendly name
Write-Host "Renaming executable to HistoryAnalyst.exe..." -ForegroundColor Gray
Rename-Item -Path "$releaseDir/flutter_application.exe" -NewName "HistoryAnalyst.exe"

# Copy PyInstaller Backend Executable
Write-Host "Copying compiled Python backend..." -ForegroundColor Gray
Copy-Item -Path "dist/app.exe" -Destination "$backendReleaseDir/app.exe" -Force

# Copy example ingestion CSV files
Write-Host "Copying example CSV datasets..." -ForegroundColor Gray
if (Test-Path "test_search_sample.csv") {
    Copy-Item -Path "test_search_sample.csv" -Destination $examplesReleaseDir -Force
}
if (Test-Path "test_youtube_sample.csv") {
    Copy-Item -Path "test_youtube_sample.csv" -Destination $examplesReleaseDir -Force
}

Write-Host "Unified Standalone folder assembled successfully at: $releaseDir" -ForegroundColor Green

# Step 5: Compress Release Package into ZIP
Write-Host "`n[5/5] Creating ZIP release archive..." -ForegroundColor Yellow
$zipPath = "HistoryAnalyst-Windows-x64.zip"
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Compress-Archive -Path $releaseDir -DestinationPath $zipPath -Force
Write-Host "ZIP Archive created successfully at: $zipPath" -ForegroundColor Green

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "BUILD COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "Standalone ZIP: d:\GOOGLE_TAKEOUT_RAG\HistoryAnalyst-Windows-x64.zip" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
