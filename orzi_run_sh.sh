#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Orzi SMS service..."

# Get configuration
API_KEY=$(bashio::config 'api_key')
LOG_LEVEL=$(bashio::config 'log_level')

# Export variables
export API_KEY
export LOG_LEVEL

# Create config file from Home Assistant options
python3 - << EOF
import json
import os

config = {
    'api_key': os.getenv('API_KEY', ''),
    'default_recipients': $(bashio::config 'default_recipients'),
    'rate_limit': {
        'enabled': $(bashio::config 'rate_limit.enabled'),
        'max_per_minute': $(bashio::config 'rate_limit.max_per_minute'),
        'max_per_hour': $(bashio::config 'rate_limit.max_per_hour')
    },
    'queue': {
        'enabled': $(bashio::config 'queue.enabled'),
        'max_size': $(bashio::config 'queue.max_size'),
        'retry_attempts': $(bashio::config 'queue.retry_attempts')
    },
    'templates': $(bashio::config 'templates')
}

with open('/data/config.json', 'w') as f:
    json.dump(config, f)
EOF

# Start the Python service
python3 /orzi_sms.py