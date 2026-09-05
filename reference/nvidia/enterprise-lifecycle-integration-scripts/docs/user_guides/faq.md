# Frequently Asked Questions (FAQ)

## General Questions

### What is DGX Spark Enterprise Manageability?

A management solution for NVIDIA DGX Spark devices that provides enterprise-grade device management, security, compliance, and operational capabilities.

### Who should use these tools?

- **IT Administrators**: For device management and maintenance
- **Security Teams**: For security monitoring and compliance
- **DevOps Engineers**: For automation and integration
- **End Users**: Tools run automatically in the background

### What devices are supported?

- NVIDIA DGX Spark devices
- ARM64 architecture (AArch64)
- Ubuntu Linux Pro 22.04 LTS or later

### Is there a cost?

Please contact your organization's IT department for licensing information.

## Installation & Setup

### How do I install the management tools?

See the [Getting Started Guide](getting_started.md) for installation instructions.

### What are the system requirements?

- Ubuntu Linux Pro (ARM64)
- Minimum 2GB RAM
- 5GB free disk space
- Network connectivity
- Root/sudo access

### Can I install on a non-DGX device for testing?

The tools are designed for DGX Spark devices. Testing on other ARM64 Ubuntu systems may work but is not officially supported.

### Do I need to install all functional areas?

No, you can install only the modules you need. However, core components are required for basic functionality.

### How long does installation take?

Typically 5-15 minutes depending on network speed and system configuration.

## Configuration

### Where are configuration files located?

Main configuration: `/etc/dgx_spark/`
- `main.conf` - Primary configuration
- `identity.conf` - Device identity
- `network.conf` - Network settings
- `modules/` - Module-specific configs

### How do I change configuration?

```bash
# Using configuration tool
sudo dgx-config --edit

# Or manually
sudo vim /etc/dgx_spark/main.conf
sudo dgx-config --validate
sudo systemctl restart dgx-spark-agent
```

### What happens if I misconfigure something?

- Configuration is validated before applying
- Automatic backups are created
- You can roll back to previous configuration
- System logs capture configuration changes

### Can I have different configurations for different environments?

Yes, you can use environment-specific configuration files and environment variables.

## Operations

### How do I check if the system is running correctly?

```bash
# Check status
sudo dgx-status

# View health
sudo dgx-health-check

# Check logs
sudo dgx-logs --recent
```

### When do updates happen?

Updates occur during configured maintenance windows (default: 2-4 AM). You can view/modify the schedule:

```bash
sudo dgx-config --show-maintenance
sudo dgx-config --set-maintenance "daily 03:00-05:00"
```

### Will updates interrupt my work?

Most updates happen in the background. Some updates may require a reboot, which is scheduled during maintenance windows.

### How do I trigger a manual update check?

```bash
sudo dgx-check-updates
sudo dgx-apply-updates --interactive
```

### How do I view logs?

```bash
# Recent logs
sudo dgx-logs --recent

# Specific module
sudo dgx-logs --module updates

# Follow in real-time
sudo dgx-logs --follow

# Errors only
sudo dgx-logs --errors
```

### How long are logs kept?

- Standard logs: 30 days
- Audit logs: 90 days (configurable)
- Compressed archives: 1 year
- See: `sudo dgx-config --show logging`

## Security

### Is my data secure?

Yes. The system implements:
- Encryption at rest and in transit
- Certificate-based authentication
- Audit logging
- Access control
- Compliance with security standards

### Who can access the management system?

Only users with sudo/root access and proper authentication credentials.

### Are credentials stored securely?

Yes. Credentials are:
- Encrypted at rest
- Never logged in plain text
- Stored with appropriate file permissions (600)
- Rotated according to policy

### How do I report a security issue?

Contact your security team immediately. Do not post security issues publicly.

### Does the system phone home?

The system communicates with configured management servers within your enterprise. No data is sent to external parties without explicit configuration.

## Troubleshooting

### The agent service won't start

```bash
# Check status
sudo systemctl status dgx-spark-agent

# View errors
sudo journalctl -u dgx-spark-agent -n 50

# Validate configuration
sudo dgx-config --validate

# Check dependencies
sudo dgx-check-dependencies
```

### I'm seeing connection errors

```bash
# Test connectivity
sudo dgx-test-connection

# Check network configuration
sudo dgx-config --show network

# Verify certificates
sudo dgx-verify-certs

# Check firewall
sudo ufw status
```

### A module is not working

```bash
# Check module status
sudo dgx-status --module [name]

# View module logs
sudo dgx-logs --module [name]

# Restart module
sudo dgx-restart-module [name]

# Reinstall module
sudo dgx-install-module [name] --force
```

### System is running slow

```bash
# Check resource usage
sudo dgx-resource-usage

# View active processes
sudo dgx-process-list

# Check disk space
df -h /var/log/dgx_spark/

# Review large log files
sudo du -sh /var/log/dgx_spark/*
```

### I need to rollback a change

```bash
# View configuration history
sudo dgx-config --history

# Rollback to previous configuration
sudo dgx-config --rollback

# Restore from specific backup
sudo dgx-config --restore [timestamp]
```

## Performance

### Does this impact system performance?

Minimal impact during normal operations. Resource-intensive tasks are scheduled during maintenance windows.

### How much disk space does it use?

- Installation: ~500MB
- Logs (before rotation): ~200MB
- State data: ~100MB
- Total: ~1GB (approximate)

### Can I change resource limits?

Yes, edit `/etc/dgx_spark/main.conf`:

```bash
# CPU priority (nice value)
CPU_PRIORITY=10

# Maximum memory usage
MAX_MEMORY_MB=512

# Disk I/O priority
IO_PRIORITY=low
```

### What network bandwidth is required?

- Normal operations: <1 Mbps
- During updates: 5-10 Mbps
- Log shipping: <100 Kbps

## Compliance & Auditing

### What compliance standards are supported?

- GDPR (Data Protection)
- SOC 2 (Security Controls)
- ISO 27001 (Information Security)
- HIPAA (Healthcare, if configured)
- Custom policies

### Where are audit logs stored?

`/var/log/dgx_spark/audit.log` (tamper-evident)

### How do I generate a compliance report?

```bash
sudo dgx-compliance-report --format pdf --output report.pdf
```

### Can I export audit logs?

```bash
sudo dgx-export-logs --type audit --format json --output audit_export.json
```

## Integration

### Does it integrate with existing tools?

Yes, through:
- RESTful APIs
- Log forwarding (syslog)
- SNMP traps
- Webhooks
- Custom scripts

### Can I automate tasks?

Yes, all tools have command-line interfaces and can be scripted or integrated with configuration management tools (Ansible, Puppet, etc.).

### How do I call the API?

```bash
# Example API call
curl -X GET \
  https://localhost:8443/api/v1/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

See [API Documentation](../api/api_reference.md) for details.

## Updates & Maintenance

### How do I update the management tools themselves?

```bash
# Check for tool updates
sudo dgx-self-update --check

# Apply updates
sudo dgx-self-update --apply
```

### What if an update fails?

Updates include automatic rollback on failure. You can also manually rollback:

```bash
sudo dgx-rollback-update
```

### How do I know what changed in an update?

```bash
# View changelog
sudo dgx-changelog

# View update history
sudo dgx-update-history
```

### Can I skip an update?

Not recommended for security updates. For feature updates:

```bash
sudo dgx-config --set update_policy manual
```

## Backup & Recovery

### What gets backed up?

- Configuration files
- Device state
- Certificates and keys
- Custom scripts

### Where are backups stored?

Default: `/var/backups/dgx_spark/`
Can be configured to remote storage.

### How do I restore from backup?

```bash
# List available backups
sudo dgx-backup --list

# Restore from specific backup
sudo dgx-backup --restore [timestamp]
```

### Are backups encrypted?

Yes, using the device's encryption keys.

## Advanced Topics

### Can I write custom modules?

Yes! See the [Development Guide](../development/setup.md) and use the templates in `docs/templates/`.

### How do I debug issues?

```bash
# Enable debug mode
sudo dgx-config --set log_level DEBUG
sudo systemctl restart dgx-spark-agent

# View debug logs
sudo dgx-logs --level debug
```

### Can I run in offline mode?

Limited functionality available. Some features require management server connectivity:

```bash
sudo dgx-config --set offline_mode true
```

### How do I customize alerts?

Edit `/etc/dgx_spark/alerts.conf`:

```bash
# Email alerts
ALERT_EMAIL=admin@example.com

# SNMP traps
ALERT_SNMP_ENABLED=true
ALERT_SNMP_HOST=snmp.example.com
```

## Getting More Help

### Where can I find more documentation?

- User Guides: `/opt/dgx_spark_management/docs/user_guides/`
- Online: [Documentation Portal]
- Built-in help: `dgx-help`

### How do I report a bug?

1. Collect diagnostic information:
```bash
sudo dgx-collect-diagnostics
```

2. Contact your administrator or submit a ticket with the diagnostic bundle.

### How do I request a feature?

Contact your IT department or product management team with feature requests.

### Is there a community forum?

Check with your organization for internal forums or channels.

### How do I get training?

Contact your training department for available courses and resources.

## Common Error Messages

### "Permission denied"
- Solution: Use `sudo` or check file permissions

### "Connection refused"
- Solution: Check network configuration and firewall rules

### "Configuration invalid"
- Solution: Run `sudo dgx-config --validate` to identify issues

### "Certificate expired"
- Solution: Renew certificate with `sudo dgx-renew-cert`

### "Service timeout"
- Solution: Check system resources and logs

### "Module not found"
- Solution: Install module with `sudo dgx-install-module [name]`

## Quick Command Reference

```bash
# Status and Health
sudo dgx-status                    # System status
sudo dgx-health-check              # Health check
sudo dgx-logs                      # View logs

# Configuration
sudo dgx-config --show             # Show configuration
sudo dgx-config --edit             # Edit configuration
sudo dgx-config --validate         # Validate configuration

# Updates
sudo dgx-check-updates             # Check for updates
sudo dgx-apply-updates             # Apply updates
sudo dgx-update-history            # View update history

# Troubleshooting
sudo dgx-test-connection           # Test connectivity
sudo dgx-collect-diagnostics       # Collect diagnostics
sudo dgx-verify-installation       # Verify installation

# Backup
sudo dgx-backup --create           # Create backup
sudo dgx-backup --list             # List backups
sudo dgx-backup --restore          # Restore backup
```

---

**Last Updated**: January 2026  
**Have a question not answered here?** Contact your system administrator.
