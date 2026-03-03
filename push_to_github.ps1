# GitHub にプッシュするスクリプト
# 使い方: Git をインストール後、このフォルダで PowerShell を開き実行
#   .\push_to_github.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Git が使えるか確認
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "エラー: Git がインストールされていません。" -ForegroundColor Red
    Write-Host "https://gitforwindows.org/ からインストールし、ターミナルを再起動してください。" -ForegroundColor Yellow
    exit 1
}

# 初回: init と commit
if (-not (Test-Path .git)) {
    Write-Host "git init ..." -ForegroundColor Cyan
    git init
    git add .
    git commit -m "Initial commit: DHP 駐車場マスタ 緯度経度抽出"
}

# リモートがなければ追加
$ErrorActionPreference = "Continue"
$null = git remote get-url origin 2>&1
$needRemote = ($LASTEXITCODE -ne 0)
$ErrorActionPreference = "Stop"
if ($needRemote) {
    Write-Host "git remote add origin ..." -ForegroundColor Cyan
    git remote add origin https://github.com/kakerusuzuki-arch/DHP.git
}

# ブランチを main に
git branch -M main

# 変更があればコミット
$status = git status --porcelain
if ($status) {
    Write-Host "git add . && git commit ..." -ForegroundColor Cyan
    git add .
    git commit -m "Update: DHP 駐車場マスタ 緯度経度抽出"
}

# プッシュ
Write-Host "git push ..." -ForegroundColor Cyan
git push -u origin main

Write-Host "完了: https://github.com/kakerusuzuki-arch/DHP" -ForegroundColor Green
