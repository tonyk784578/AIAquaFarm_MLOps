@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: ================================================================
::  AIAquaFarm - GitHub Push 스크립트 (Windows CMD / PowerShell)
::  사용법: push.bat 더블클릭 또는 CMD에서 실행
:: ================================================================

set REPO_OWNER=tonyk784578
set REPO_NAME=AIAquaFarm_MLOps
set BRANCH=master

echo.
echo  ===================================
echo   AIAquaFarm GitHub Push
echo  ===================================
echo.

:: PAT 소유자 계정명 (PAT를 발급한 GitHub 계정)
for /f "tokens=*" %%i in ('git config user.name 2^>nul') do set AUTH_USER=%%i
if "%AUTH_USER%"=="" (
    set /p AUTH_USER="GitHub 계정명 (PAT 발급 계정): "
)
echo   계정: %AUTH_USER%
echo   저장소: %REPO_OWNER%/%REPO_NAME%
echo.

:: PAT 입력 (미리 환경변수로 설정해도 됨: set GITHUB_PAT=ghp_xxx)
if "%GITHUB_PAT%"=="" (
    set /p GITHUB_PAT="GitHub PAT 입력 (ghp_...): "
)

if "%GITHUB_PAT%"=="" (
    echo [오류] PAT가 입력되지 않았습니다.
    pause
    exit /b 1
)

:: 커밋 여부 확인
set /p DO_COMMIT="변경사항을 커밋하고 Push하시겠습니까? (y/n): "

if /i "!DO_COMMIT!"=="y" (
    set /p COMMIT_MSG="커밋 메시지 입력 (엔터 = update): "
    if "!COMMIT_MSG!"=="" set COMMIT_MSG=update

    git add -A
    git commit -m "!COMMIT_MSG!"
    if errorlevel 1 echo [알림] 커밋할 변경사항이 없습니다.
)

:: remote URL에 PAT 포함하여 설정
git remote set-url origin https://!AUTH_USER!:!GITHUB_PAT!@github.com/%REPO_OWNER%/%REPO_NAME%.git

:: Push
echo.
echo [Push 중...] origin/%BRANCH%
git push origin %BRANCH%

if errorlevel 1 (
    echo.
    echo [실패] Push 실패. PAT 권한 또는 네트워크를 확인하세요.
    echo        GitHub ^> Settings ^> Developer settings ^> Personal access tokens
) else (
    echo.
    echo [완료] Push 성공!
)

:: 보안: remote URL에서 PAT 제거
git remote set-url origin https://github.com/%REPO_OWNER%/%REPO_NAME%.git

echo.
pause
endlocal
