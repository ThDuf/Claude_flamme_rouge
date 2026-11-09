@echo off
rem Flamme Rouge en ligne : demarre le serveur de jeu sur ce PC, puis le tunnel Cloudflare qui le rend
rem joignable depuis Internet. Le lien a envoyer a tes amis s'affiche plus bas (https://....trycloudflare.com).
rem Ferme cette fenetre (ou Ctrl+C) pour arreter : le site disparait.
cd /d "%~dp0"
chcp 65001 >nul

rem Ou est cloudflared ? Dans le PATH, sinon a l'emplacement de l'installation (PATH pas encore a jour).
set "CLOUDFLARED="
where cloudflared >nul 2>nul && set "CLOUDFLARED=cloudflared"
if not defined CLOUDFLARED if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CLOUDFLARED if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles%\cloudflared\cloudflared.exe"
if defined CLOUDFLARED goto :tunnel

echo.
echo cloudflared n'est pas installe. Pour l'installer, une seule fois :
echo     winget install --id Cloudflare.cloudflared
echo puis relance ce fichier.
echo.
echo En attendant, le serveur demarre seulement pour ce PC : http://127.0.0.1:8770
python -m online.server
goto :eof

:tunnel
start "Serveur Flamme Rouge" /min python -m online.server
timeout /t 2 /nobreak >nul
echo.
echo ================================================================================
echo   Le lien a envoyer a tes amis apparait ci-dessous (ligne https://....trycloudflare.com).
echo   Toi, tu peux jouer sur http://127.0.0.1:8770
echo ================================================================================
echo.
"%CLOUDFLARED%" tunnel --no-autoupdate --url http://127.0.0.1:8770
taskkill /fi "WINDOWTITLE eq Serveur Flamme Rouge*" >nul 2>nul
