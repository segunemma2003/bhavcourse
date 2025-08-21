# Pipeline Commands for MySQL and Migration Fix

## Quick One-Liner for Pipeline

Add this to your pipeline before migrations:

```bash
# Install MySQL client and fix migrations
sudo apt-get update && sudo apt-get install -y default-libmysqlclient-dev build-essential pkg-config python3-dev && pip install mysqlclient && python manage.py check --database default && python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected" && python manage.py makemigrations --merge || true && python manage.py migrate
```

## Step-by-Step Pipeline Commands

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y default-libmysqlclient-dev build-essential pkg-config python3-dev
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
pip install mysqlclient  # Ensure MySQL client is installed
```

### 3. Verify MySQL Client

```bash
python -c "import MySQLdb; print('✅ MySQL client working')"
```

### 4. Check Database Connection

```bash
python manage.py check --database default
```

### 5. Fix Migration Conflicts

```bash
# Check for conflicts
python manage.py showmigrations core

# If conflicts detected, merge them
python manage.py makemigrations --merge

# Apply migrations
python manage.py migrate
```

## GitHub Actions Workflow

Your `.github/workflows/deploy.yml` is already configured with these fixes.

## Manual Server Fix

If you need to fix the server manually:

```bash
# SSH into your server
ssh user@your-server

# Navigate to your project
cd /path/to/your/project

# Activate virtual environment
source venv/bin/activate

# Install MySQL client if missing
pip install mysqlclient

# Check database
python manage.py check --database default

# Fix migrations if needed
python manage.py makemigrations --merge
python manage.py migrate
```

## Troubleshooting

### If MySQL client installation fails:

```bash
# Try alternative installation
sudo apt-get install -y python3-dev default-libmysqlclient-dev
pip install --only-binary=all mysqlclient
```

### If migrations still fail:

```bash
# Check migration status
python manage.py showmigrations

# Reset migrations (DANGEROUS - backup first!)
python manage.py migrate core zero
python manage.py makemigrations core
python manage.py migrate
```
