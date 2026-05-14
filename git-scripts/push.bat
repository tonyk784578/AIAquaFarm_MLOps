@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ================================================================
::  AIAquaFarm - GitHub Push 스크립트 (Windows CMD / PowerShell)
::  사용법: push.bat
:: ================================================================

set GITHUB_USER=tonyk784578
set REPO_NAME=AIAquaFarm_MLOps
set BRANCH=master

echo.
echo  ===================================
echo   AIAquaFarm GitHub Push
echo  ===================================
echo.

:: PAT 입력 (환경변수로 미리 설정해도 됨: set GITHUB_PAT=ghp_xxx)
if "%GITHUB_PAT%"=="" (
    set /p GITHUB_PAT="GitHub PAT 입력 (ghp_...): "
)

if "%GITHUB_PAT%"=="" (
    echo [오류] PAT가 입력되지 않았습니다.
    pause
    exit /b 1
)

:: 커밋 메시지 입력 여부 확인
set /p DO_COMMIT="변경사항을 커밋하고 Push하시겠습니까? (y/n): "

if /i "%DO_COMMIT%"=="y" (
    set /p COMMIT_MSG="커밋 메시지 입력: "
    if "!COMMIT_MSG!"=="" set COMMIT_MSG=update

    git add -A
    git commit -m "!COMMIT_MSG!"
    if errorlevel 1 (
        echo [알림] 커밋할 변경사항이 없거나 커밋 실패
    )
)

:: remote URL에 PAT 포함하여 설정
git remote set-url origin https://%GITHUB_USER%:%GITHUB_PAT%@github.com/%GITHUB_USER%/%REPO_NAME%.git

:: Push
echo.
echo [Push 중...] origin/%BRANCH%
git push origin %BRANCH%

if errorlevel 1 (
    echo.
    echo [실패] Push 실패. PAT 권한 또는 네트워크를 확인하세요.
) else (
    echo.
    echo [완료] Push 성공!
)

:: 보안: remote URL에서 PAT 제거
git remote set-url origin https://github.com/%GITHUB_USER%/%REPO_NAME%.git

echo.
pause
endlocal
