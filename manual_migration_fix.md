# Manual Migration Fix Guide

## The Problem

The error shows that table `core_appleiapproduct` already exists, but Django is trying to create it again. This is a migration state mismatch.

## Quick Fix Steps

### Option 1: Mark Migration as Applied (Recommended)

1. **SSH into your server:**

   ```bash
   ssh your_username@your_server_ip
   cd /var/www/bhavani
   source venv/bin/activate
   ```

2. **Check which tables already exist:**

   ```bash
   python manage.py dbshell
   ```

   Then in MySQL:

   ```sql
   SHOW TABLES LIKE 'core_appleiapproduct';
   SHOW TABLES LIKE 'core_appleiapreceipt';
   SHOW TABLES LIKE 'core_paymentlinkrequest';
   SHOW TABLES LIKE 'core_paymentorder';
   EXIT;
   ```

3. **If tables exist, mark the migration as applied:**

   ```bash
   python manage.py migrate core 0017_appleiapproduct_appleiapproduct_paymentlinkrequest_and_more --fake
   ```

4. **Run remaining migrations:**
   ```bash
   python manage.py migrate
   ```

### Option 2: Use the Fix Script

1. **Upload the fix script to your server:**

   ```bash
   # From your local machine
   scp fix_migration_conflict.py your_username@your_server_ip:/var/www/bhavani/
   ```

2. **Run the fix script:**
   ```bash
   # On your server
   cd /var/www/bhavani
   source venv/bin/activate
   python fix_migration_conflict.py
   ```

### Option 3: Reset Migration State (Nuclear Option)

⚠️ **WARNING: This will lose migration history. Only use if other options fail.**

1. **Backup your database first:**

   ```bash
   mysqldump -u your_db_user -p your_db_name > backup_before_migration_fix.sql
   ```

2. **Reset migration state:**

   ```bash
   python manage.py migrate core zero --fake
   python manage.py migrate core --fake-initial
   ```

3. **Run migrations normally:**
   ```bash
   python manage.py migrate
   ```

## Verification

After fixing, verify everything works:

```bash
python manage.py check
python manage.py showmigrations core
python manage.py migrate --plan
```

## Common Issues

- **Permission denied**: Use `sudo` for system commands
- **Database connection error**: Check your `.env` file
- **Virtual environment not found**: Make sure you're in `/var/www/bhavani` and the venv exists

## Next Time

To avoid this in the future:

1. Always backup before migrations
2. Test migrations on a staging environment first
3. Use `--fake` flag when you know tables already exist
