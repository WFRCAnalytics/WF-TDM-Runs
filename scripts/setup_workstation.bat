@echo off
setlocal enabledelayedexpansion

:: ===========================================================================
:: scripts\setup_workstation.bat
::
:: One-shot setup for a new Cube Voyager workstation: clones WF-TDM-Runs (and
:: the TDM submodule), installs Python deps via uv, and creates this
:: machine's own config\local.yaml from the example.
::
:: Run this from wherever you want the repo folder created (it creates
:: .\WF-TDM-Runs in the current directory) -- e.g. double-click it after
:: saving it somewhere, or run it from a Command Prompt.
::
:: Requires git and uv already installed on this machine:
::   git: https://git-scm.com/download/win
::   uv:  https://docs.astral.sh/uv/getting-started/installation/
:: (Cube Voyager itself is not installed by this script -- that has its own
:: per-machine license/installer, separate from this repo.)
:: ===========================================================================

set REPO_URL=https://github.com/WFRCAnalytics/WF-TDM-Runs.git
set BRANCH=shorten-lengthen-all-work-trips

where git >nul 2>nul
if errorlevel 1 (
    echo [FAILED] git is not on PATH. Install it first: https://git-scm.com/download/win
    pause
    exit /b 1
)

where uv >nul 2>nul
if errorlevel 1 (
    echo [FAILED] uv is not on PATH. Install it first: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo === Cloning WF-TDM-Runs (branch: %BRANCH%) ===
git clone --branch %BRANCH% %REPO_URL%
if errorlevel 1 (
    echo.
    echo [FAILED] git clone failed -- see the error above.
    pause
    exit /b 1
)

cd WF-TDM-Runs

echo.
echo === Initializing TDM submodule (this can take a while over VPN) ===
git submodule update --init --recursive
if errorlevel 1 (
    echo.
    echo [FAILED] Submodule init failed. If the TDM repo is private, make sure
    echo your git credentials ^(SSH key or credential manager^) are set up on
    echo this machine before re-running: git submodule update --init --recursive
    pause
    exit /b 1
)

echo.
echo === Installing Python dependencies ^(uv sync^) ===
uv sync --extra reports --extra dev
if errorlevel 1 (
    echo.
    echo [FAILED] uv sync failed -- see the error above.
    pause
    exit /b 1
)

echo.
echo === Setting up this machine's local config ===
if not exist config\local.yaml (
    copy config\local.example.yaml config\local.yaml >nul
    echo Created config\local.yaml from the example.
    echo.
    echo *** EDIT config\local.yaml NOW before running anything -- it needs
    echo *** this machine's own Voyager_EXE path ^(and UserName/UserCompany^).
) else (
    echo config\local.yaml already exists here -- leaving it alone.
)

echo.
echo === Done ===
echo Repo cloned to: %cd%
echo.
echo Next steps:
echo   1. Edit config\local.yaml ^(Voyager_EXE path for this machine^)
echo   2. uv run tdmruns validate-config --run-set shorten-lengthen-all-work-trips
echo   3. uv run tdmruns run-set --run-set shorten-lengthen-all-work-trips
echo.
pause
