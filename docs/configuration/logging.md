# Logging Configuration

RouteMQ now supports comprehensive file logging with configurable rotation options. This document explains all available logging configuration options.

## Overview

The logging system supports both console and file output with flexible rotation strategies based on file size or time intervals.

## Environment Variables

### Basic Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_TO_FILE` | `true` | Enable/disable file logging (true/false) |
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `LOG_FILE` | `logs/app.log` | Log file path (relative to project root or absolute) |
| `LOG_FORMAT` | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` | Log message format |

### Rotation Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_ROTATION_TYPE` | `size` | Rotation strategy: 'size' or 'time' |

### Size-based Rotation (LOG_ROTATION_TYPE=size)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_MAX_BYTES` | `10485760` | Maximum file size in bytes before rotation (10MB) |
| `LOG_BACKUP_COUNT` | `5` | Number of backup files to keep |

### Time-based Rotation (LOG_ROTATION_TYPE=time)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_ROTATION_WHEN` | `midnight` | When to rotate: 'midnight', 'D' (daily), 'H' (hourly), 'W0-W6' (weekly), 'M' (monthly) |
| `LOG_ROTATION_INTERVAL` | `1` | Rotation interval (e.g., 1 for every day if WHEN=D) |
| `LOG_DATE_FORMAT` | `%Y-%m-%d` | Date format for backup file names |

## Configuration Examples

### Example 1: Size-based Rotation (Default)
```env
LOG_TO_FILE=true
LOG_FILE=logs/app.log
LOG_ROTATION_TYPE=size
LOG_MAX_BYTES=5242880  # 5MB
LOG_BACKUP_COUNT=3
```

This creates:
- `logs/app.log` (current log)
- `logs/app.log.1` (most recent backup)
- `logs/app.log.2`
- `logs/app.log.3` (oldest backup)

### Example 2: Daily Time-based Rotation
```env
LOG_TO_FILE=true
LOG_FILE=logs/app.log
LOG_ROTATION_TYPE=time
LOG_ROTATION_WHEN=midnight
LOG_ROTATION_INTERVAL=1
LOG_BACKUP_COUNT=7
LOG_DATE_FORMAT=%Y-%m-%d
```

This creates:
- `logs/app.log` (current day)
- `logs/app.log.2024-01-15` (previous days)
- `logs/app.log.2024-01-14`
- etc.

### Example 3: Hourly Rotation
```env
LOG_TO_FILE=true
LOG_FILE=logs/hourly.log
LOG_ROTATION_TYPE=time
LOG_ROTATION_WHEN=H
LOG_ROTATION_INTERVAL=1
LOG_BACKUP_COUNT=24
LOG_DATE_FORMAT=%Y-%m-%d_%H
```

### Example 4: Weekly Rotation (Sunday)
```env
LOG_TO_FILE=true
LOG_FILE=logs/weekly.log
LOG_ROTATION_TYPE=time
LOG_ROTATION_WHEN=W6  # Sunday (0=Monday, 6=Sunday)
LOG_ROTATION_INTERVAL=1
LOG_BACKUP_COUNT=4
LOG_DATE_FORMAT=%Y-W%U
```

### Example 5: Console Only (No File Logging)
```env
LOG_TO_FILE=false
LOG_LEVEL=DEBUG
```

## Log Levels

| Level | Description |
|-------|-------------|
| `DEBUG` | Detailed information for debugging |
| `INFO` | General information messages |
| `WARNING` | Warning messages |
| `ERROR` | Error messages |
| `CRITICAL` | Critical error messages |

## Log Format Variables

The `LOG_FORMAT` variable supports Python logging format strings:

| Variable | Description |
|----------|-------------|
| `%(asctime)s` | Timestamp |
| `%(name)s` | Logger name |
| `%(levelname)s` | Log level |
| `%(message)s` | Log message |
| `%(filename)s` | Source filename |
| `%(lineno)d` | Line number |
| `%(funcName)s` | Function name |
| `%(process)d` | Process ID |
| `%(thread)d` | Thread ID |

## File Path Configuration

- **Relative paths**: Relative to the project root directory
  - `logs/app.log` → Creates `logs/` directory in project root
  - `temp/debug.log` → Creates `temp/` directory in project root

- **Absolute paths**: Full system paths
  - `/var/log/routemq/app.log` (Linux/Mac)
  - `C:\logs\routemq\app.log` (Windows)

## Backup File Naming

### Size-based Rotation
- Current: `app.log`
- Backups: `app.log.1`, `app.log.2`, etc.

### Time-based Rotation
- Current: `app.log`
- Backups: `app.log.YYYY-MM-DD`, `app.log.YYYY-MM-DD_HH`, etc.

## Error Handling

If file logging setup fails (e.g., permission issues, invalid path), the system:
1. Prints a warning to console
2. Falls back to console-only logging
3. Continues application startup normally

## Performance Considerations

- **File I/O**: File logging adds minimal overhead
- **Rotation**: Automatic rotation prevents disk space issues
- **Backup Count**: Higher backup counts use more disk space
- **Log Level**: Lower levels (DEBUG) generate more log entries

## Troubleshooting

### Common Issues

1. **Permission Denied**
   - Ensure the application has write permissions to the log directory
   - Try using a different log file path

2. **Directory Not Found**
   - The system automatically creates parent directories
   - Check file path syntax for your operating system

3. **Large Log Files**
   - Reduce `LOG_MAX_BYTES` for more frequent rotation
   - Increase rotation frequency for time-based rotation
   - Lower the log level to reduce log volume

4. **Missing Log Files**
   - Check if `LOG_TO_FILE=true`
   - Verify the log file path is correct
   - Check application startup messages for logging configuration
