# RouteMQ Installation Guide

This legacy guide describes the old template workflow. For new projects, prefer the PyPI package:

```bash
uv add "routemq[cli]"
routemq new my-mqtt-project
cd my-mqtt-project
routemq run
```

## Table of Contents

- [Using as a Project Template](#using-as-a-project-template)
- [Method 1: GitHub Template (Recommended)](#method-1-github-template-recommended)
- [Method 2: Manual Setup with Clean Git](#method-2-manual-setup-with-clean-git)
- [Method 3: Direct Clone](#method-3-direct-clone)
- [Post-Installation Setup](#post-installation-setup)
- [Troubleshooting](#troubleshooting)

---

## Using as a Project Template

RouteMQ is designed to be used as a **template** for your own MQTT routing projects. This means you can start with a clean git history and customize it for your needs.

### Why Use as Template?

- ✅ **Clean git history** - Start with your own first commit
- ✅ **No upstream conflicts** - Your repository is independent
- ✅ **Easy customization** - Make it yours from day one
- ✅ **Your own remote** - Push to your own GitHub/GitLab/etc.

---

## Method 1: GitHub Template (Recommended)

This is the easiest way to create a new project based on RouteMQ.

### Steps:

1. **On GitHub**, navigate to the RouteMQ repository
2. Click the **"Use this template"** button (green button near the top)
3. Choose a name for your new repository
4. Select public or private
5. Click **"Create repository from template"**

6. **Clone your new repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   cd YOUR_REPO_NAME
   ```

7. **Install dependencies:**
   ```bash
   uv sync
   ```

8. **Initialize project structure:**
   ```bash
   uv run routemq new .
   ```

9. **Configure environment:**
   ```bash
   # Edit .env file with your MQTT broker details
   nano .env  # or use your preferred editor
   ```

10. **Run the application:**
    ```bash
     uv run routemq run
    ```

### Advantages:
- ✅ Cleanest approach
- ✅ Automatic setup on GitHub
- ✅ No manual git operations needed
- ✅ GitHub will track it as derived from RouteMQ

---

## Method 2: Manual Setup with Clean Git

Use this method if you want to download RouteMQ and initialize it with a fresh git repository.

### Option A: Using Setup Script (Easiest)

1. **Download or clone RouteMQ:**
   ```bash
   # Clone to a new directory
   git clone https://github.com/ardzz/RouteMQ.git my-mqtt-project
   cd my-mqtt-project
   ```

   Or download as ZIP and extract.

2. **Run the setup script:**

   **Linux/Mac:**
   ```bash
   bash setup-project.sh
   ```

   **Windows PowerShell:**
   ```powershell
   .\setup-project.ps1
   ```

   The script will:
   - Remove existing git history
   - Initialize a fresh repository
   - Ask if you want to add a remote
   - Set up your .env file

3. **Install dependencies:**
   ```bash
   uv sync
   ```

4. **Initialize project structure:**
   ```bash
   routemq new .
   ```

5. **Run the application:**
   ```bash
   uv run routemq run
   ```

### Option B: Manual Git Reinitialization

1. **Clone or download:**
   ```bash
   git clone https://github.com/ardzz/RouteMQ.git my-mqtt-project
   cd my-mqtt-project
   ```

2. **Remove existing git history:**
   ```bash
   # Linux/Mac
   rm -rf .git

   # Windows (PowerShell)
   Remove-Item -Recurse -Force .git

   # Windows (CMD)
   rmdir /s /q .git
   ```

3. **Initialize fresh repository:**
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit from RouteMQ template"
   ```

4. **Add your remote (optional):**
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

5. **Continue with installation:**
   ```bash
   uv sync
    routemq new .
    uv run routemq run
   ```

---

## Method 3: Direct Clone

Use this method if you want to contribute to RouteMQ or just explore the framework.

**⚠️ Note:** This preserves the original git history and remote.

```bash
# Clone the repository
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ

# Install dependencies
uv sync

# Initialize project
routemq new .

# Configure .env
# Edit the .env file with your configuration

# Run the application
uv run routemq run
```

---

## Post-Installation Setup

After installing using any method, you should:

### 1. Configure Environment Variables

Edit your `.env` file:

```bash
# MQTT Configuration
MQTT_BROKER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password

# Optional: Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Optional: MySQL Configuration
DATABASE_URL=mysql://user:password@localhost/database
```

### 2. Create Your First Router

```python
# app/routers/example.py
from routemq.router import Router
from app.controllers.example_controller import ExampleController

router = Router()

router.on("home/temperature", ExampleController.handle_temperature)
router.on("home/humidity", ExampleController.handle_humidity)
router.on("devices/{device_id}/status", ExampleController.handle_device_status)
```

### 3. Customize for Your Needs

- Add your controllers in `app/controllers/`
- Create middleware in `app/middleware/`
- Define background jobs in `app/jobs/`
- Add database models in `app/models/`

---

## Troubleshooting

### Issue: Git already initialized

If you see "already a git repository" error:
```bash
rm -rf .git
git init
```

### Issue: Permission denied on setup script

Make the script executable:
```bash
chmod +x setup-project.sh
bash setup-project.sh
```

### Issue: uv command not found

Install uv first:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Issue: Python version error

Ensure you have Python 3.12 or higher:
```bash
python --version
# Should show 3.12 or higher
```

### Issue: MQTT connection failed

Check your `.env` configuration:
- Verify broker hostname and port
- Check username/password if authentication is required
- Ensure firewall allows MQTT connections

---

## Next Steps

After successful installation:

1. **Read the documentation** in the `docs/` folder
2. **Run the tests** to verify everything works:
   ```bash
   uv run pytest
   ```
3. **Try the examples** in `docs/examples/`
4. **Join the community** and get help if needed

---

## Getting Help

- 📖 **Documentation:** See the [docs](./docs) folder
- 🐛 **Issues:** Report bugs on GitHub Issues
- 💬 **Questions:** Check the [FAQ](./docs/faq.md)

---

**Happy routing! 🚀**
