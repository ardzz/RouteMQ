# Troubleshooting

Common issues and solutions for RouteMQ applications.

## Topics

- [Common Issues](common-issues.md) - Frequently encountered problems
- [Connection Problems](connection-problems.md) - MQTT and database connectivity
- [Performance Issues](performance-issues.md) - Optimization and debugging
- [Redis Issues](redis-issues.md) - Redis-specific problems
- [Debug Mode](debug-mode.md) - Enabling detailed logging

## Common Issues

### 1. Routes Not Loading
**Problem**: Routes defined in router files are not being discovered

**Solutions**:
- Check that router files have a `router` variable
- Ensure router files are in the correct directory (`app/routers/`)
- Verify router files have proper Python syntax
- Check logs for import errors

### 2. Worker Processes Not Starting
**Problem**: Shared subscription workers are not starting

**Solutions**:
- Ensure shared routes are properly configured with `shared=True`
- Check worker_count parameter is set correctly
- Verify MQTT broker supports shared subscriptions
- Check for port conflicts or permission issues

### 3. Database Connection Issues
**Problem**: Cannot connect to MySQL database

**Solutions**:
- Verify database credentials in `.env` file
- Check network connectivity to database server
- Ensure database exists and user has proper permissions
- Check database server is running

### 4. MQTT Connection Failed
**Problem**: Cannot connect to MQTT broker

**Solutions**:
- Check broker address, port, and credentials
- Verify MQTT broker is running and accessible
- Check firewall settings
- Test connection with MQTT client tools

### 5. Redis Connection Failed
**Problem**: Cannot connect to Redis server

**Solutions**:
- Verify Redis server is running
- Check Redis credentials and configuration
- Test Redis connection with `redis-cli`
- Verify network connectivity

### 6. Rate Limiting Not Working
**Problem**: Rate limiting middleware not blocking requests

**Solutions**:
- Ensure Redis is enabled or fallback mode is configured
- Check rate limiting configuration parameters
- Verify middleware is properly applied to routes
- Check Redis key expiration settings

## Debug Mode

Enable debug logging for detailed troubleshooting:

```env
LOG_LEVEL=DEBUG
```

This provides detailed information about:
- Route discovery and loading process
- Message processing and middleware execution
- Worker process management
- Redis operations and connection status
- Rate limiting decisions and calculations

## Getting Help

1. Check the logs for error messages
2. Enable debug mode for detailed information
3. Verify configuration settings
4. Test individual components in isolation
5. Check the [FAQ](../faq.md) for common questions

## Next Steps

- [Common Issues](common-issues.md) - Detailed problem solutions
- [Performance Issues](performance-issues.md) - Optimization tips
- [Debug Mode](debug-mode.md) - Advanced debugging techniques
