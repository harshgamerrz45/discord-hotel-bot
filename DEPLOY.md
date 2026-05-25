# 24/7 Discord Bot Hosting

This folder is the deploy-ready version of your hotel Discord bot.

## Important security step

Your original file had a Discord token and database password inside the code. Before hosting, reset the Discord bot token in the Discord Developer Portal and use the new token only as an environment variable.

## Required environment variables

Add these in your hosting provider's Variables or Environment page:

```text
DISCORD_TOKEN
MYSQL_HOST
MYSQL_PORT
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
```

## Start command

Use this command for a worker/background service:

```bash
python prototype3.py --nogui
```

The `--nogui` flag is required for cloud hosting because Tkinter dashboards need a desktop screen.

## Railway

1. Create a new Railway project from this folder/repository.
2. Add the environment variables above.
3. Set the start command to:

```bash
python prototype3.py --nogui
```

## Render

1. Create a new Background Worker, not a Web Service.
2. Set the build command to:

```bash
pip install -r requirements.txt
```

3. Set the start command to:

```bash
python prototype3.py --nogui
```

4. Add the environment variables above.

## VPS

On a Linux VPS, install Python and run the bot under `systemd`, Docker, or another process manager so it restarts after crashes and server reboots.
