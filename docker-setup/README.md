# Neo4j Docker Setup

This directory contains scripts to automatically set up Neo4j in Docker for the EU Cybersecurity Management System.

## Quick Start

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File setup_neo4j_docker.ps1
```

### Linux / macOS (Bash)

```bash
bash setup_neo4j_docker.sh
```

## Options

### Windows (PowerShell)

```powershell
# Custom port
powershell -ExecutionPolicy Bypass -File setup_neo4j_docker.ps1 -Port 7688

# Custom password
powershell -ExecutionPolicy Bypass -File setup_neo4j_docker.ps1 -Password "mypassword"

# Force recreate container
powershell -ExecutionPolicy Bypass -File setup_neo4j_docker.ps1 -Force

# Custom web port
powershell -ExecutionPolicy Bypass -File setup_neo4j_docker.ps1 -WebPort 7475
```

### Linux / macOS (Bash)

```bash
# Custom port
bash setup_neo4j_docker.sh 7688

# Custom port and password
bash setup_neo4j_docker.sh 7688 7475 "mypassword"

# Force recreate container
bash setup_neo4j_docker.sh "" "" "" true
```

## Default Configuration

- **Container Name:** eurlex-neo4j
- **Bolt Port:** 7687
- **Web UI Port:** 7474
- **Username:** neo4j
- **Password:** password
- **Storage:** Persistent volume (eurlex-data)
- **Memory:** 4GB max heap

## What the Scripts Do

1. Check Docker is installed and running
2. Check for existing Neo4j container
3. Create new container with persistent storage
4. Wait for Neo4j to be ready
5. Test the connection
6. Display connection details and useful commands

## After Setup

### Verify Connection

```bash
python test/verify_neo4j.py
```

### View Logs

```bash
docker logs eurlex-neo4j
```

### Access Web UI

Open your browser to: `http://localhost:7474`

### Docker Commands

```bash
# Stop database
docker stop eurlex-neo4j

# Start database
docker start eurlex-neo4j

# View logs
docker logs eurlex-neo4j

# Delete container
docker rm eurlex-neo4j

# Delete data volume
docker volume rm eurlex-data

# Recreate from scratch
docker volume rm eurlex-data  # Optional: delete old data
bash setup_neo4j_docker.sh --force
```

## Troubleshooting

### Docker not running
- Windows: Start Docker Desktop
- Linux: `sudo systemctl start docker`
- macOS: Open Docker Desktop app

### Connection refused
- Wait 10-15 seconds, Neo4j may still be starting
- Check logs: `docker logs eurlex-neo4j`
- Verify port is correct (default 7687)

### Authentication failed
- Verify password matches (default: password)
- Check username is "neo4j"

### Port already in use
- Use custom port: `bash setup_neo4j_docker.sh 7688`
- Or stop existing container: `docker stop eurlex-neo4j`

## Files

- `setup_neo4j_docker.ps1` - Windows PowerShell setup script
- `setup_neo4j_docker.sh` - Linux/macOS bash setup script
- `README.md` - This file
