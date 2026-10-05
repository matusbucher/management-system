#!/usr/bin/env powershell
"""
Automated Neo4j Docker Setup Script

Run this once Docker Desktop is fully running:
    powershell -ExecutionPolicy Bypass -File docker-setup/setup_neo4j_docker.ps1

This will:
1. Check Docker is running
2. Create Neo4j container with persistent storage
3. Wait for container to be healthy
4. Test the connection
"""

param(
    [switch]$Force = $false,
    [string]$Port = "7687",
    [string]$WebPort = "7474",
    [string]$Password = "password"
)

Write-Host "`n" + "="*70
Write-Host "NEO4J DOCKER SETUP"
Write-Host "="*70 + "`n"

# Step 1: Check Docker
Write-Host "Step 1: Checking Docker..."
try {
    $dockerVersion = docker --version 2>$null
    Write-Host "[OK] Docker found: $dockerVersion`n"
} catch {
    Write-Host "[ERROR] Docker not found. Please install Docker Desktop first."
    Write-Host "   Download from: https://www.docker.com/products/docker-desktop`n"
    exit 1
}

# Step 2: Check Docker daemon
Write-Host "Step 2: Checking Docker daemon..."
$dockerReady = $false
for ($i = 1; $i -le 12; $i++) {
    $result = docker ps 2>&1
    if ($result -notmatch "error" -and $result -notmatch "refused") {
        Write-Host "[OK] Docker daemon is running`n"
        $dockerReady = $true
        break
    }
    Write-Host "  Waiting... ($i/12)"
    Start-Sleep -Seconds 5
}

if (-not $dockerReady) {
    Write-Host "[ERROR] Docker daemon not responding. Please start Docker Desktop manually."
    Write-Host "   1. Press Windows key"
    Write-Host "   2. Type 'Docker'"
    Write-Host "   3. Click 'Docker Desktop'"
    Write-Host "   4. Wait 2-3 minutes for startup"
    Write-Host "   5. Run this script again`n"
    exit 1
}

# Step 3: Check existing container
Write-Host "Step 3: Checking for existing container..."
$containerExists = docker ps -a --filter "name=eurlex-neo4j" --quiet 2>$null
if ($containerExists) {
    Write-Host "Found existing container: $containerExists"
    if ($Force) {
        Write-Host "Removing existing container (--Force flag)..."
        docker rm -f eurlex-neo4j | Out-Null
        Write-Host "[OK] Removed`n"
    } else {
        Write-Host "[OK] Container already exists`n"
        Write-Host "Checking if it's running..."
        $running = docker ps --filter "name=eurlex-neo4j" --quiet 2>$null
        if ($running) {
            Write-Host "[OK] Container is already running`n"
            docker ps --filter "name=eurlex-neo4j"
            Write-Host "`nSkipping creation..."
            goto TestConnection
        } else {
            Write-Host "[WAIT] Container exists but stopped. Starting it..."
            docker start eurlex-neo4j | Out-Null
            Start-Sleep -Seconds 5
            goto TestConnection
        }
    }
}

# Step 4: Create container
Write-Host "Step 4: Creating Neo4j container..."
Write-Host "  Name: eurlex-neo4j"
Write-Host "  Bolt Port: $Port"
Write-Host "  Web Port: $WebPort"
Write-Host "  Storage: Persistent volume 'eurlex-data'"
Write-Host "  Auth: neo4j / $Password`n"

docker run -d `
    --name eurlex-neo4j `
    --publish "${Port}:7687" `
    --publish "${WebPort}:7474" `
    --env NEO4J_AUTH="neo4j/${Password}" `
    --env NEO4J_server_jvm_additional="-Xmx4g" `
    --volume eurlex-data:/data `
    neo4j:latest 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Container created`n"
} else {
    Write-Host "[ERROR] Failed to create container`n"
    exit 1
}

Write-Host "Step 5: Waiting for Neo4j to be ready..."
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    $logs = docker logs eurlex-neo4j 2>$null
    if ($logs -match "Started") {
        Write-Host "[OK] Neo4j is ready`n"
        $ready = $true
        break
    }
    Write-Host "  Waiting... ($i/30 seconds)"
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Host "[WARNING] Neo4j startup taking longer than expected"
    Write-Host "   But container should be ready soon. Proceeding with tests..`n"
}

:TestConnection
# Step 6: Test connection
Write-Host "Step 6: Testing connection..."
Write-Host "  Connecting to bolt://localhost:${Port}...`n"

$testScript = @"
import sys
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

try:
    driver = GraphDatabase.driver(
        'bolt://localhost:$Port',
        auth=('neo4j', '$Password'),
        connection_acquire_timeout=10
    )
    with driver.session() as session:
        result = session.run('MATCH (n) RETURN COUNT(n) as count')
        count = result.single()[0]
    driver.close()
    
    print(f"[OK] Connection successful!")
    print(f"   Nodes: {count}")
    print(f"   Web UI: http://localhost:$WebPort")
    
except ServiceUnavailable:
    print("[ERROR] Neo4j not responding yet. It may still be starting.")
    print("   Try connecting in 10-15 seconds.")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Error: {e}")
    sys.exit(1)
"@

python -c $testScript
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[OK] SETUP COMPLETE!"
    Write-Host "`nDatabase Details:"
    Write-Host "  Connection String: bolt://localhost:${Port}"
    Write-Host "  Username: neo4j"
    Write-Host "  Password: $Password"
    Write-Host "  Web UI: http://localhost:${WebPort}"
    Write-Host "  Storage: Persistent (eurlex-data volume)`n"
    Write-Host "Useful Docker commands:"
    Write-Host "  docker logs eurlex-neo4j          # View logs"
    Write-Host "  docker stop eurlex-neo4j          # Stop database"
    Write-Host "  docker start eurlex-neo4j         # Start database"
    Write-Host "  docker rm eurlex-neo4j            # Delete container"
    Write-Host "  docker volume rm eurlex-data      # Delete data`n"
    Write-Host "Next steps:"
    Write-Host "  1. Run verification: python test\verify_neo4j.py"
    Write-Host "  2. Run module tests: python test\test_modules.py`n"
} else {
    Write-Host "`n[WARNING] Connection test failed. Neo4j may still be starting."
    Write-Host "Verify with: python test\verify_neo4j.py"
    Write-Host "Or check Docker logs: docker logs eurlex-neo4j`n"
}
