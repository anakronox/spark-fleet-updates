# Deployment Guide

This guide covers deploying the DGX Spark Enterprise Manageability solution to target devices.

## Overview

The deployment process involves:
1. Pre-deployment preparation
2. System requirements verification
3. Installation of management tools
4. Configuration
5. Verification and testing
6. Monitoring setup

## Prerequisites

### Target System Requirements

- **Operating System**: Ubuntu Linux Pro 22.04 LTS or later (ARM64)
- **Architecture**: ARM64 (AArch64)
- **Memory**: Minimum 2GB available RAM
- **Disk Space**: Minimum 5GB free space
- **Network**: Internet connectivity for initial setup
- **Permissions**: Root or sudo access

### Pre-Deployment Checklist

- [ ] Target device meets system requirements
- [ ] Network connectivity verified
- [ ] Backup of existing configuration (if updating)
- [ ] Change management approval obtained
- [ ] Maintenance window scheduled
- [ ] Rollback plan prepared

## Deployment Methods

### Method 1: Manual Deployment (Single Device)

Best for: Initial setup, testing, small deployments

```bash
# 1. Clone repository
git clone <repository-url>
cd DGX_spark_management

# 2. Run installation script
sudo ./scripts/install.sh

# 3. Configure
sudo ./scripts/configure.sh

# 4. Verify installation
sudo ./scripts/verify_installation.sh
```

### Method 2: Automated Deployment (Multiple Devices)

Best for: Large-scale deployments, standardization

```bash
# Using configuration management tool (e.g., Ansible)
ansible-playbook -i inventory.yml playbooks/deploy_dgx_management.yml

# Or using deployment script
./scripts/deploy_to_devices.sh --inventory devices.txt
```

### Method 3: Package-Based Deployment

Best for: Enterprise environments with package management

```bash
# Install from package repository
sudo apt update
sudo apt install dgx-spark-management

# Configure
sudo dpkg-reconfigure dgx-spark-management
```

## Installation Steps

### Step 1: Prepare Target System

```bash
# Update system packages
sudo apt update
sudo apt upgrade -y

# Install required dependencies
sudo apt install -y \
    bash \
    python3 \
    python3-pip \
    curl \
    wget \
    openssl \
    ca-certificates

# Verify ARM64 architecture
uname -m  # Should output: aarch64
```

### Step 2: Download and Verify

```bash
# Download installation package
wget https://releases.example.com/dgx-spark-management-latest.tar.gz

# Verify checksum
sha256sum -c dgx-spark-management-latest.tar.gz.sha256

# Verify GPG signature
gpg --verify dgx-spark-management-latest.tar.gz.sig

# Extract
tar -xzf dgx-spark-management-latest.tar.gz
cd dgx-spark-management
```

### Step 3: Run Installation Script

```bash
# Review installation script
less scripts/install.sh

# Run installation with options
sudo ./scripts/install.sh \
    --install-dir /opt/dgx_spark_management \
    --log-dir /var/log/dgx_spark \
    --config-dir /etc/dgx_spark

# Installation script will:
# - Create directory structure
# - Copy files to appropriate locations
# - Set permissions
# - Create systemd services
# - Enable services
```

### Step 4: Initial Configuration

```bash
# Run configuration wizard
sudo /opt/dgx_spark_management/scripts/configure.sh

# Or manually edit configuration
sudo vim /etc/dgx_spark/main.conf
```

#### Required Configuration Items

1. **Device Identity**
```bash
# /etc/dgx_spark/identity.conf
DEVICE_ID="dgx-spark-001"
DEVICE_NAME="DGX Spark Production 1"
SITE_ID="datacenter-01"
```

2. **Network Configuration**
```bash
# /etc/dgx_spark/network.conf
MANAGEMENT_SERVER="mgmt.example.com"
MANAGEMENT_PORT="8443"
USE_TLS="true"
```

3. **Security Settings**
```bash
# /etc/dgx_spark/security.conf
ENABLE_AUDIT_LOG="true"
ENCRYPTION_ENABLED="true"
CERT_PATH="/etc/dgx_spark/certs"
```

### Step 5: Certificate Setup

```bash
# Generate device certificate
sudo /opt/dgx_spark_management/tools/generate_device_cert.sh

# Or import existing certificate
sudo cp device.crt /etc/dgx_spark/certs/
sudo cp device.key /etc/dgx_spark/certs/
sudo chmod 600 /etc/dgx_spark/certs/device.key

# Verify certificate
openssl x509 -in /etc/dgx_spark/certs/device.crt -text -noout
```

### Step 6: Service Startup

```bash
# Enable services
sudo systemctl enable dgx-spark-agent
sudo systemctl enable dgx-spark-monitor

# Start services
sudo systemctl start dgx-spark-agent
sudo systemctl start dgx-spark-monitor

# Check status
sudo systemctl status dgx-spark-agent
sudo systemctl status dgx-spark-monitor
```

### Step 7: Verification

```bash
# Run verification script
sudo /opt/dgx_spark_management/scripts/verify_installation.sh

# Manual verification
# 1. Check services are running
sudo systemctl status dgx-spark-*

# 2. Check logs for errors
sudo tail -f /var/log/dgx_spark/*.log

# 3. Test connectivity to management server
sudo /opt/dgx_spark_management/tools/test_connectivity.sh

# 4. Verify device enrollment
sudo /opt/dgx_spark_management/tools/check_enrollment.sh
```

## Configuration Management

### Configuration Files

Main configuration files:

```
/etc/dgx_spark/
├── main.conf                 # Main configuration
├── identity.conf             # Device identity
├── network.conf              # Network settings
├── security.conf             # Security settings
├── modules/                  # Module-specific configs
│   ├── asset_info.conf
│   ├── updates.conf
│   └── ...
└── certs/                    # Certificates
    ├── device.crt
    ├── device.key
    └── ca.crt
```

### Environment-Specific Configuration

```bash
# Development
export DGX_ENV=development
export DGX_LOG_LEVEL=DEBUG

# Production
export DGX_ENV=production
export DGX_LOG_LEVEL=INFO
```

## Functional Area Deployment

Each functional area can be deployed independently:

### Example: Deploying Asset Information Module

```bash
# Install module
sudo /opt/dgx_spark_management/scripts/install_module.sh \
    --module clear_asset_information

# Configure module
sudo vim /etc/dgx_spark/modules/asset_info.conf

# Enable module
sudo /opt/dgx_spark_management/scripts/enable_module.sh \
    --module clear_asset_information

# Verify module
sudo /opt/dgx_spark_management/scripts/test_module.sh \
    --module clear_asset_information
```

## High Availability Setup

For critical deployments:

### Redundant Network Paths

```bash
# Configure primary and backup management servers
PRIMARY_SERVER="mgmt1.example.com"
BACKUP_SERVER="mgmt2.example.com"
```

### Automatic Failover

```bash
# Enable failover
sudo vim /etc/dgx_spark/network.conf
# Set ENABLE_FAILOVER=true
# Set FAILOVER_TIMEOUT=30
```

## Security Hardening

### Post-Deployment Security

```bash
# 1. Secure file permissions
sudo chmod 700 /etc/dgx_spark
sudo chmod 600 /etc/dgx_spark/*.conf
sudo chmod 600 /etc/dgx_spark/certs/*.key

# 2. Enable AppArmor profile
sudo aa-enforce /etc/apparmor.d/dgx-spark-agent

# 3. Configure firewall
sudo ufw allow 8443/tcp comment 'DGX Spark Management'
sudo ufw enable

# 4. Enable audit logging
sudo auditctl -w /etc/dgx_spark/ -p wa -k dgx_spark_config
```

## Monitoring Setup

### Log Monitoring

```bash
# Configure log rotation
sudo vim /etc/logrotate.d/dgx-spark

# Content:
/var/log/dgx_spark/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 root adm
    sharedscripts
    postrotate
        systemctl reload dgx-spark-agent > /dev/null 2>&1 || true
    endscript
}
```

### Health Monitoring

```bash
# Enable health monitoring
sudo systemctl enable dgx-spark-healthcheck.timer
sudo systemctl start dgx-spark-healthcheck.timer

# View health status
sudo /opt/dgx_spark_management/tools/health_check.sh
```

## Troubleshooting Deployment Issues

### Common Issues

#### Issue 1: Service Fails to Start

```bash
# Check logs
sudo journalctl -u dgx-spark-agent -n 50

# Check configuration
sudo /opt/dgx_spark_management/scripts/validate_config.sh

# Verify dependencies
sudo /opt/dgx_spark_management/scripts/check_dependencies.sh
```

#### Issue 2: Connection to Management Server Fails

```bash
# Test connectivity
ping mgmt.example.com
telnet mgmt.example.com 8443

# Check DNS resolution
nslookup mgmt.example.com

# Verify certificates
sudo openssl s_client -connect mgmt.example.com:8443
```

#### Issue 3: Permission Denied Errors

```bash
# Check file permissions
ls -la /etc/dgx_spark/

# Verify service user
id dgx-spark

# Fix permissions
sudo /opt/dgx_spark_management/scripts/fix_permissions.sh
```

## Rollback Procedures

### Rollback to Previous Version

```bash
# Stop services
sudo systemctl stop dgx-spark-*

# Restore from backup
sudo tar -xzf /var/backups/dgx_spark_backup_YYYYMMDD.tar.gz -C /

# Restart services
sudo systemctl start dgx-spark-*

# Verify
sudo /opt/dgx_spark_management/scripts/verify_installation.sh
```

### Emergency Rollback

```bash
# Use emergency rollback script
sudo /opt/dgx_spark_management/scripts/emergency_rollback.sh

# This will:
# - Stop all services
# - Restore last known good configuration
# - Restart services
# - Generate rollback report
```

## Post-Deployment Tasks

### 1. Documentation

- [ ] Document deployed configuration
- [ ] Update inventory
- [ ] Record certificate details
- [ ] Note any customizations

### 2. Validation

- [ ] All services running
- [ ] Device enrolled successfully
- [ ] All modules functional
- [ ] Logs showing normal operation

### 3. Monitoring

- [ ] Alerts configured
- [ ] Dashboards updated
- [ ] Health checks passing
- [ ] Audit logging enabled

### 4. Team Handoff

- [ ] Operations team notified
- [ ] Documentation provided
- [ ] Access credentials shared (securely)
- [ ] Support contacts established

## Maintenance

### Regular Maintenance Tasks

```bash
# Weekly
- Review logs for errors
- Check disk space
- Verify connectivity

# Monthly
- Update packages (if approved)
- Review and rotate logs
- Test backup/restore

# Quarterly
- Security audit
- Performance review
- Capacity planning
```

## Additional Resources

- [Operations Guide](../operations/runbooks/daily_operations.md)
- [Troubleshooting Guide](../troubleshooting/common_issues.md)
- [Security Policy](../operations/security_policy.md)

---

**Last Updated**: January 2026  
**Maintained By**: Operations Team
