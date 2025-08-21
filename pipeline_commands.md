# Pipeline Migration Fix Commands

## 🔧 **Add these commands to your existing pipeline:**

### **First, install MySQL client dependencies:**

```bash
# Install MySQL client dependencies
sudo apt-get update && sudo apt-get install -y default-libmysqlclient-dev build-essential pkg-config
pip install mysqlclient
```

### **Then, before `python manage.py migrate`, add:**

### **Before `python manage.py migrate`, add:**

```bash
# Check and fix migration conflicts
python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected" && python manage.py makemigrations --merge || echo "No conflicts found"
```

### **Or use this more robust version:**

```bash
# Migration conflict fix
if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
    echo "⚠️ Migration conflicts detected. Running merge..."
    python manage.py makemigrations --merge
    echo "✅ Migration conflicts resolved"
else
    echo "✅ No migration conflicts found"
fi
```

## 🚀 **Complete Pipeline Steps:**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment (if needed)
# ... your environment setup ...

# 3. Fix migration conflicts (ADD THIS)
if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
    echo "⚠️ Migration conflicts detected. Running merge..."
    python manage.py makemigrations --merge
    echo "✅ Migration conflicts resolved"
else
    echo "✅ No migration conflicts found"
fi

# 4. Apply migrations
python manage.py migrate

# 5. Collect static files
python manage.py collectstatic --noinput

# 6. Restart services
# ... your service restart commands ...
```

## 📋 **For Different CI/CD Platforms:**

### **GitHub Actions:**

```yaml
- name: Fix migration conflicts
  run: |
    if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
      echo "⚠️ Migration conflicts detected. Running merge..."
      python manage.py makemigrations --merge
      echo "✅ Migration conflicts resolved"
    else
      echo "✅ No migration conflicts found"
    fi
```

### **GitLab CI:**

```yaml
fix_migrations:
  script:
    - if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
      echo "⚠️ Migration conflicts detected. Running merge..."
      python manage.py makemigrations --merge
      echo "✅ Migration conflicts resolved"
      else
      echo "✅ No migration conflicts found"
      fi
```

### **Jenkins:**

```bash
# Add to your Jenkins pipeline script
if python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected"; then
    echo "⚠️ Migration conflicts detected. Running merge..."
    python manage.py makemigrations --merge
    echo "✅ Migration conflicts resolved"
else
    echo "✅ No migration conflicts found"
fi
```

## 🎯 **Quick One-Liner (Recommended):**

Add this single line to your pipeline before `python manage.py migrate`:

```bash
python manage.py showmigrations core 2>&1 | grep -q "Conflicting migrations detected" && python manage.py makemigrations --merge || true
```

This will:

- ✅ Check for migration conflicts
- ✅ Merge them if they exist
- ✅ Continue if no conflicts (won't fail the pipeline)
- ✅ Handle the payment link migration issue automatically

## ⚠️ **Important Notes:**

1. **Backup your database** before running this in production
2. **Test in staging** first
3. **Monitor the deployment** to ensure it works correctly
4. This is a **one-time fix** - once the conflicts are resolved, future deployments won't need this step
