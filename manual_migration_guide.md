# Manual Migration Guide

## 🚀 **Pipeline Now Skips Migrations**

Your pipeline will now:

- ✅ Install dependencies
- ✅ Collect static files
- ✅ Run tests
- ✅ Deploy code
- ❌ **Skip migrations** (you handle manually)

## 📋 **Manual Migration Commands**

### **On Your Server:**

```bash
# SSH into your server
ssh user@your-server

# Navigate to your project
cd /path/to/your/project

# Activate virtual environment
source venv/bin/activate

# Check migration status
python manage.py showmigrations

# Create migrations (if needed)
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check for conflicts
python manage.py showmigrations core | grep -q "Conflicting migrations detected" && python manage.py makemigrations --merge || echo "No conflicts"
```

### **Quick One-Liner:**

```bash
# SSH and run migrations in one command
ssh user@your-server "cd /path/to/your/project && source venv/bin/activate && python manage.py migrate"
```

## 🔧 **If You Have Migration Conflicts:**

```bash
# Check for conflicts
python manage.py showmigrations core

# If conflicts detected, merge them
python manage.py makemigrations --merge

# Apply all migrations
python manage.py migrate
```

## 📝 **Deployment Workflow:**

1. **Pipeline deploys code** (no migrations)
2. **SSH to server** and run migrations manually
3. **Restart services** if needed

## ⚠️ **Important Notes:**

- **Always backup** your database before migrations
- **Test migrations** in staging first
- **Monitor** the migration process
- **Check logs** if something goes wrong

## 🎯 **Benefits of Manual Migrations:**

- ✅ **Full control** over when migrations run
- ✅ **Can review** migration files before applying
- ✅ **Can backup** database before migrations
- ✅ **Can rollback** if needed
- ✅ **No pipeline failures** due to migration issues
