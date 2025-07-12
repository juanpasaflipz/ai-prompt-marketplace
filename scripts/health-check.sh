#!/bin/bash

# Health check and alerting script
# Run this as a cron job every 5 minutes

# Configuration
API_URL="https://api.promptmarketplace.com"
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL}"
EMAIL_TO="ops@promptmarketplace.com"
LOG_FILE="/var/log/ai-prompt-marketplace/health-check.log"

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

send_alert() {
    local message=$1
    local severity=$2
    
    # Log the alert
    log "ALERT [$severity]: $message"
    
    # Send to Slack if webhook is configured
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\":warning: *Health Check Alert*\n*Severity:* $severity\n*Message:* $message\"}" \
            "$SLACK_WEBHOOK" 2>/dev/null
    fi
    
    # Send email alert for critical issues
    if [ "$severity" == "CRITICAL" ]; then
        echo "$message" | mail -s "CRITICAL: AI Prompt Marketplace Health Check Failed" "$EMAIL_TO"
    fi
}

# Health checks
check_api_health() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
    if [ "$response" != "200" ]; then
        send_alert "API health check failed. Response code: $response" "CRITICAL"
        return 1
    fi
    log "API health check: OK"
    return 0
}

check_database() {
    # Check if we can connect to the database
    if ! PGPASSWORD=$DB_PASSWORD psql -h localhost -U marketplace_user -d prompt_marketplace -c "SELECT 1" > /dev/null 2>&1; then
        send_alert "Database connection failed" "CRITICAL"
        return 1
    fi
    
    # Check database size
    db_size=$(PGPASSWORD=$DB_PASSWORD psql -h localhost -U marketplace_user -d prompt_marketplace -t -c "SELECT pg_database_size('prompt_marketplace')/1024/1024 as size_mb")
    if [ "$db_size" -gt 5000 ]; then  # Alert if DB > 5GB
        send_alert "Database size is large: ${db_size}MB" "WARNING"
    fi
    
    log "Database check: OK (Size: ${db_size}MB)"
    return 0
}

check_redis() {
    if ! redis-cli ping > /dev/null 2>&1; then
        send_alert "Redis connection failed" "HIGH"
        return 1
    fi
    
    # Check Redis memory usage
    used_memory=$(redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    log "Redis check: OK (Memory: $used_memory)"
    return 0
}

check_disk_space() {
    disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        send_alert "Disk space critical: ${disk_usage}% used" "CRITICAL"
        return 1
    elif [ "$disk_usage" -gt 80 ]; then
        send_alert "Disk space warning: ${disk_usage}% used" "WARNING"
    fi
    
    log "Disk space check: OK (${disk_usage}% used)"
    return 0
}

check_memory() {
    memory_usage=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
    if [ "$memory_usage" -gt 90 ]; then
        send_alert "Memory usage critical: ${memory_usage}%" "HIGH"
        return 1
    elif [ "$memory_usage" -gt 80 ]; then
        send_alert "Memory usage warning: ${memory_usage}%" "WARNING"
    fi
    
    log "Memory check: OK (${memory_usage}% used)"
    return 0
}

check_ssl_certificate() {
    # Check SSL certificate expiration
    cert_expiry=$(echo | openssl s_client -servername api.promptmarketplace.com -connect api.promptmarketplace.com:443 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2)
    cert_expiry_epoch=$(date -d "$cert_expiry" +%s)
    current_epoch=$(date +%s)
    days_until_expiry=$(( ($cert_expiry_epoch - $current_epoch) / 86400 ))
    
    if [ "$days_until_expiry" -lt 7 ]; then
        send_alert "SSL certificate expires in ${days_until_expiry} days!" "CRITICAL"
        return 1
    elif [ "$days_until_expiry" -lt 30 ]; then
        send_alert "SSL certificate expires in ${days_until_expiry} days" "WARNING"
    fi
    
    log "SSL certificate check: OK (expires in ${days_until_expiry} days)"
    return 0
}

check_response_time() {
    # Measure API response time
    response_time=$(curl -o /dev/null -s -w '%{time_total}' "$API_URL/api/v1")
    response_time_ms=$(echo "$response_time * 1000" | bc | cut -d. -f1)
    
    if [ "$response_time_ms" -gt 5000 ]; then
        send_alert "API response time high: ${response_time_ms}ms" "HIGH"
        return 1
    elif [ "$response_time_ms" -gt 2000 ]; then
        send_alert "API response time warning: ${response_time_ms}ms" "WARNING"
    fi
    
    log "Response time check: OK (${response_time_ms}ms)"
    return 0
}

check_error_logs() {
    # Check for recent errors in logs
    error_count=$(grep -c "ERROR" /var/log/ai-prompt-marketplace/api.log 2>/dev/null | tail -100 || echo "0")
    
    if [ "$error_count" -gt 50 ]; then
        send_alert "High error rate in logs: $error_count errors in last 100 lines" "HIGH"
        return 1
    elif [ "$error_count" -gt 20 ]; then
        send_alert "Elevated error rate in logs: $error_count errors in last 100 lines" "WARNING"
    fi
    
    log "Error log check: OK ($error_count errors)"
    return 0
}

# Main execution
main() {
    log "Starting health checks..."
    
    failed_checks=0
    
    # Run all checks
    check_api_health || ((failed_checks++))
    check_database || ((failed_checks++))
    check_redis || ((failed_checks++))
    check_disk_space || ((failed_checks++))
    check_memory || ((failed_checks++))
    check_ssl_certificate || ((failed_checks++))
    check_response_time || ((failed_checks++))
    check_error_logs || ((failed_checks++))
    
    if [ "$failed_checks" -eq 0 ]; then
        log "All health checks passed"
    else
        log "Health checks completed with $failed_checks failures"
    fi
    
    exit "$failed_checks"
}

# Run main function
main