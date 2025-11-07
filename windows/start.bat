@echo off
echo Starting Hyperliquid Copy Trader with Docker...
docker-compose up -d
echo.
echo Bot started! Use 'docker-compose logs -f' to view logs
echo Use 'docker-compose down' to stop the bot
pause
