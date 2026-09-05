# Getting Started with DGX Spark Enterprise Manageability

Welcome! This guide will help you get started with the DGX Spark Enterprise Manageability tools.

## What is DGX Spark Enterprise Manageability?

A comprehensive suite of tools for managing NVIDIA DGX Spark devices in enterprise environments, providing:
- Complete asset visibility
- Automated updates and patching
- Security and compliance enforcement
- Remote management capabilities
- Data protection and privacy controls
- Lifecycle management

## Quick Start

### For Administrators

1. **Install the Management Tools**
```bash
# From a Git clone of this cookbook repository (repository root):
git clone <repository-url>
cd <clone-directory>
bash install.sh
```

Use `bash install.sh` (not `./install.sh`) if scripts are not executable, or if you see “required file not found” (often CRLF from Windows — see `common/README.md`).

2. **Configure Your Device**
```bash
# Run configuration wizard
sudo /opt/dgx_spark_management/scripts/configure.sh
```

3. **Verify Installation**
```bash
# Check status
sudo systemctl status dgx-spark-agent
```

### For End Users

The management tools run in the background. You'll benefit from:
- Automatic security updates
- System health monitoring
- Data protection
- Compliance enforcement

## Key Concepts

### Functional Areas

The system is organized into 11 functional areas:

1. **Clear Asset Information**: Know what hardware and software is on your device
2. **Controlled SW/FW Updates**: Managed and tested updates
3. **Attestable Conformance**: Compliance with policies
4. **Enrollment & Access Control**: Secure device enrollment and access management
5. **Remote Operations**: Remote troubleshooting and remediation
6. **Resilience & Recovery**: Backup and restore capabilities
7. **Network Connectivity**: Enterprise network integration
8. **Security Posture**: Vulnerability management
9. **Data Protection**: Encryption and privacy controls
10. **Integration & Automation**: API and workflow automation
11. **Lifecycle Management**: From provisioning to decommissioning

### Key Components

- **Agent**: Background service that manages the device
- **Modules**: Individual tools for specific functions
- **Configuration**: Settings that control behavior
- **Logs**: Records of all activities

## Common Tasks

### Checking Device Status

```bash
# View overall status
sudo dgx-status

# View specific module status
sudo dgx-status --module asset_info
```

### Viewing Logs

```bash
# View recent logs
sudo dgx-logs

# View logs for specific module
sudo dgx-logs --module updates

# Follow logs in real-time
sudo dgx-logs --follow
```

### Running Manual Scans

```bash
# Run asset inventory
sudo dgx-asset-scan

# Run vulnerability scan
sudo dgx-vuln-scan

# Run compliance check
sudo dgx-compliance-check
```

### Updating Configuration

```bash
# View current configuration
sudo dgx-config --show

# Edit configuration
sudo dgx-config --edit

# Validate configuration
sudo dgx-config --validate
```

## Understanding the Interface

### Command-Line Tools

All tools follow consistent patterns:

```bash
# General format
dgx-<tool-name> [options] [arguments]

# Get help
dgx-<tool-name> --help

# Verbose output
dgx-<tool-name> --verbose

# Dry run (preview changes)
dgx-<tool-name> --dry-run
```

### Configuration Files

Configuration is stored in `/etc/dgx_spark/`:

- `main.conf` - Main configuration
- `identity.conf` - Device identity
- `network.conf` - Network settings
- `security.conf` - Security settings
- `modules/` - Module-specific configs

### Log Files

Logs are stored in `/var/log/dgx_spark/`:

- `agent.log` - Main agent log
- `[module_name]/` - Module-specific logs
- `audit.log` - Security audit log

## Understanding Operations

### Automatic vs Manual Operations

**Automatic Operations** (no action needed):
- Security updates (during maintenance windows)
- Health checks
- Log rotation
- Certificate renewal
- Compliance reporting

**Manual Operations** (requires action):
- Initial configuration
- Policy changes
- Emergency patches
- Manual scans
- Troubleshooting

### Maintenance Windows

Updates and maintenance occur during configured windows:

```bash
# View maintenance schedule
sudo dgx-config --show-maintenance

# Modify maintenance window
sudo dgx-config --set-maintenance "daily 02:00-04:00"
```

## Security Best Practices

### Access Control

```bash
# Only authorized administrators should have access
# Use sudo for privileged operations
# Never run as root unless necessary
sudo dgx-tool [options]
```

### Configuration Security

```bash
# Configuration files contain sensitive data
# Ensure proper permissions
sudo chmod 600 /etc/dgx_spark/*.conf
```

### Monitoring

```bash
# Regularly check logs for anomalies
sudo dgx-logs --errors

# Review audit log
sudo cat /var/log/dgx_spark/audit.log
```

## Troubleshooting

### Agent Not Running

```bash
# Check status
sudo systemctl status dgx-spark-agent

# Start agent
sudo systemctl start dgx-spark-agent

# View recent errors
sudo journalctl -u dgx-spark-agent -n 50
```

### Connection Issues

```bash
# Test connectivity
sudo dgx-test-connection

# Check network configuration
sudo dgx-config --show network
```

### Module Not Working

```bash
# Check module status
sudo dgx-status --module [module_name]

# Restart module
sudo dgx-restart-module [module_name]

# View module logs
sudo dgx-logs --module [module_name]
```

## Getting Help

### Built-in Help

```bash
# General help
dgx-help

# Tool-specific help
dgx-<tool-name> --help

# List all available tools
dgx-help --list-tools
```

### Documentation

- User Guides: `/opt/dgx_spark_management/docs/user_guides/`
- Troubleshooting: `/opt/dgx_spark_management/docs/troubleshooting/`
- FAQ: See [FAQ](faq.md)

### Support

1. Check documentation
2. Review logs
3. Contact your system administrator
4. Submit support ticket (if available)

## Best Practices

### Daily Operations

- Monitor system notifications
- Review error logs weekly
- Keep configurations backed up
- Document any custom settings

### Security

- Use strong passwords
- Protect certificates and keys
- Review access logs regularly
- Report suspicious activity

### Performance

- Monitor disk space
- Keep logs rotated
- Schedule intensive operations during off-hours
- Archive old logs

## Next Steps

### For Administrators

1. Review [Deployment Guide](../deployment/deployment_guide.md)
2. Configure [Monitoring](../operations/monitoring.md)
3. Set up [Backup](../operations/backup_restore.md)
4. Review [Security Policy](../operations/security_policy.md)

### For Developers

1. Review [Development Setup](../development/setup.md)
2. Read [Contributing Guidelines](../development/contributing.md)
3. Study [Architecture](../architecture/system_overview.md)
4. Explore existing modules

### For End Users

1. Familiarize with [FAQ](faq.md)
2. Understand maintenance windows
3. Know how to report issues
4. Review data privacy policy

## Frequently Used Commands

```bash
# Check overall system status
sudo dgx-status

# View recent activity
sudo dgx-logs --recent

# Run health check
sudo dgx-health-check

# Update configuration
sudo dgx-config --edit

# Test connectivity
sudo dgx-test-connection

# View help
dgx-help
```

## Important Notes

- **Permissions**: Most commands require sudo/root access
- **Backups**: Configuration is backed up automatically
- **Updates**: Applied during maintenance windows
- **Logs**: Rotated automatically, check retention policy
- **Support**: Contact your administrator for assistance

## Quick Reference Card

```
┌─────────────────────────────────────────────────────┐
│             DGX Spark Quick Reference               │
├─────────────────────────────────────────────────────┤
│ Status:           sudo dgx-status                   │
│ Logs:             sudo dgx-logs [--follow]          │
│ Health Check:     sudo dgx-health-check             │
│ Configuration:    sudo dgx-config --show            │
│ Test Connection:  sudo dgx-test-connection          │
│ Help:             dgx-help                          │
├─────────────────────────────────────────────────────┤
│ Config Location:  /etc/dgx_spark/                   │
│ Log Location:     /var/log/dgx_spark/               │
│ Install Location: /opt/dgx_spark_management/        │
└─────────────────────────────────────────────────────┘
```

---

**Last Updated**: January 2026  
**For Additional Help**: See [FAQ](faq.md) or contact your administrator
