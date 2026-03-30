# Docker Deployment Guide for Agents

## 1. Prepare Required Files

Make sure these files exist in your project root:

- **`Dockerfile`**
- **`docker-compose.yml`**
- **`.env`** (with all required environment variables)
- **`requirements.txt`** (with all Python dependencies)

## 2. Dockerfile Template

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8051

CMD ["python", "your_agent.py"]
```

**Notes:**
- Change `EXPOSE` port to match your agent's port
- Change `CMD` to match your main entry file
- Always use a virtual environment inside the container for clean dependency isolation

## 3. docker-compose.yml Template

```yaml
services:
  agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: your-agent-name
    restart: unless-stopped
    ports:
      - "8051:8051"
    env_file:
      - .env
    networks:
      - agent-network

networks:
  agent-network:
    driver: bridge
```

**Notes:**
- Change `container_name` to something unique for your agent
- Change `ports` to match the port in your Dockerfile and `.env`

## 4. Test Locally

```bash
# Build and run (foreground — see logs directly)
docker-compose up --build

# Or run in background
docker-compose up --build -d

# Check logs (if running in background)
docker-compose logs -f

# Verify agent is running
docker ps
```

## 5. Verify

Before considering the agent ready for deployment, confirm:

- ✅ Agent starts without errors
- ✅ Registered on Almanac successfully
- ✅ Manifest published
- ✅ No missing environment variables
- ✅ No import/dependency errors
- ✅ Agent can receive and respond to messages

## 6. Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `.env` not found | Docker can't find env file | Make sure `.env` exists in the project root |
| Port already in use | Another container on the same port | Change the port in `docker-compose.yml` and `.env` |
| Module not found | Missing dependency | Add it to `requirements.txt` and rebuild |
| Agent not registering | Wrong agent seed/name/port | Check `.env` values |
| Permission denied | File permissions | Check file ownership and permissions |

## 7. Clean Up & Redeploy

```bash
# Stop the container
docker-compose down

# Rebuild from scratch (no cache)
docker-compose build --no-cache

# Start again
docker-compose up -d

# Check it's running
docker-compose logs --tail=20
```

## 8. Checklist Before Deployment

- [ ] Agent runs locally without errors
- [ ] Docker builds successfully
- [ ] All environment variables are set in `.env`
- [ ] `requirements.txt` is complete
- [ ] Container name is unique (no conflicts with other agents)
- [ ] Port is unique (no conflicts with other agents)
- [ ] `.env` is in `.gitignore` (never commit secrets)
- [ ] Agent registers and responds to messages in Docker
