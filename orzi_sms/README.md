# Orzi SMS Home Assistant Addon v2.0

Send SMS notifications using the Orzi API with advanced features including message templates, rate limiting, and message queuing.

## 🚀 Features

### Message Templates
Create reusable message templates with variables for common notifications.

### Rate Limiting
Prevent API abuse with configurable rate limits (per minute and per hour).

### Message Queuing
Automatic queuing when rate limits are reached, with retry logic for failed messages.

### Priority System
Send critical messages first with priority levels 0-100.

### Statistics & Monitoring
Track sent, failed, and queued messages with built-in endpoints.

## Installation

### Option 1: Local Addon (Recommended)

1. Create the addon directory:
   ```bash
   mkdir -p /addons/orzi_sms
   ```

2. Copy all files to `/addons/orzi_sms/`:
   - config.yaml
   - Dockerfile
   - run.sh
   - orzi_sms.py
   - apparmor.txt
   - README.md

3. In Home Assistant:
   - Go to **Settings → Add-ons**
   - Click **⋮ (menu) → Check for updates**
   - Find "Orzi SMS Notifications"
   - Click **Install**

### Option 2: GitHub Repository

1. Create a GitHub repository with all the files
2. In Home Assistant:
   - Go to **Settings → Add-ons → Add-on Store**
   - Click **⋮ (menu) → Repositories**
   - Add: `https://github.com/yourusername/orzi-sms-addon`
   - Install "Orzi SMS Notifications"

## Configuration

```yaml
api_key: "your-orzi-api-key-here"
default_recipients:
  - "447829999999"
  - "447829999990"
log_level: info
rate_limit:
  enabled: true
  max_per_minute: 10
  max_per_hour: 60
queue:
  enabled: true
  max_size: 100
  retry_attempts: 3
templates:
  security_alert: "ALERT: {sensor} detected at {time}"
  temperature_alert: "Temperature is {temp}°C in {location}"
  door_alert: "{door} was opened at {time}"
  battery_low: "{device} battery is low: {level}%"
```

### Configuration Options

#### api_key (required)
Your Orzi API key from your account.

#### default_recipients (optional)
List of default phone numbers in international format.

#### log_level (optional)
Logging level: `debug`, `info`, `warning`, or `error`

#### rate_limit
- `enabled`: Enable/disable rate limiting (default: true)
- `max_per_minute`: Maximum SMS per minute, 1-100 (default: 10)
- `max_per_hour`: Maximum SMS per hour, 1-1000 (default: 60)

#### queue
- `enabled`: Enable/disable message queuing (default: true)
- `max_size`: Maximum queue size, 10-1000 (default: 100)
- `retry_attempts`: Retry attempts for failed messages, 1-10 (default: 3)

#### templates
Custom message templates with variable placeholders using `{variable}` syntax.

## Usage in Home Assistant

### Setup REST Commands

Add to your `configuration.yaml`:

```yaml
rest_command:
  send_orzi_sms:
    url: http://localhost:8099/send
    method: POST
    content_type: 'application/json'
    payload: >
      {
        "recipients": {{ recipients | tojson }},
        "message": "{{ message }}",
        "priority": {{ priority | default(5) }},
        "use_queue": {{ use_queue | default(true) }}
      }
      
  send_orzi_template:
    url: http://localhost:8099/send_template
    method: POST
    content_type: 'application/json'
    payload: >
      {
        "recipients": {{ recipients | tojson }},
        "template": "{{ template }}",
        "variables": {{ variables | tojson }},
        "priority": {{ priority | default(5) }}
      }
```

### Monitoring Sensors

```yaml
sensor:
  - platform: rest
    name: Orzi SMS Stats
    resource: http://localhost:8099/stats
    value_template: "{{ value_json.stats.total_sent }}"
    json_attributes:
      - stats
    scan_interval: 60
    
  - platform: rest
    name: Orzi SMS Queue
    resource: http://localhost:8099/queue
    value_template: "{{ value_json.size }}"
    json_attributes:
      - enabled
      - size
      - max_size
    scan_interval: 30
```

## Examples

### Basic SMS

```yaml
automation:
  - alias: "Motion Detected"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion_sensor
        to: 'on'
    action:
      - service: rest_command.send_orzi_sms
        data:
          recipients: ["447829999999"]
          message: "Motion detected in {{ trigger.to_state.attributes.friendly_name }}"
          priority: 5
```

### Using Templates

```yaml
automation:
  - alias: "Security Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion_sensor
        to: 'on'
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: ["447829999999", "447829999990"]
          template: "security_alert"
          variables:
            sensor: "Motion Sensor"
            time: "{{ now().strftime('%H:%M:%S') }}"
          priority: 10

  - alias: "Temperature Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_temperature
        above: 30
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: ["447829999999"]
          template: "temperature_alert"
          variables:
            temp: "{{ states('sensor.living_room_temperature') }}"
            location: "Living Room"
          priority: 7

  - alias: "Door Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: 'on'
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: ["447829999999"]
          template: "door_alert"
          variables:
            door: "Front Door"
            time: "{{ now().strftime('%I:%M %p') }}"

  - alias: "Low Battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.phone_battery
        below: 20
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: ["447829999999"]
          template: "battery_low"
          variables:
            device: "Phone"
            level: "{{ states('sensor.phone_battery') }}"
```

### High Priority (Critical)

```yaml
automation:
  - alias: "Critical Security Breach"
    trigger:
      - platform: state
        entity_id: alarm_control_panel.home_alarm
        to: 'triggered'
    action:
      - service: rest_command.send_orzi_sms
        data:
          recipients: ["447829999999", "447829999990", "447829999991"]
          message: "CRITICAL: Home alarm triggered!"
          priority: 100
          use_queue: false  # Don't queue critical messages
```

### Conditional Priority

```yaml
automation:
  - alias: "Smart Door Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: 'on'
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: ["447829999999"]
          template: "door_alert"
          variables:
            door: "Front Door"
            time: "{{ now().strftime('%I:%M %p') }}"
          priority: >
            {% if now().hour >= 22 or now().hour <= 6 %}
              10
            {% else %}
              5
            {% endif %}
```

### Multiple Recipients Based on Severity

```yaml
automation:
  - alias: "Temperature Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 30
    action:
      - service: rest_command.send_orzi_template
        data:
          recipients: >
            {% if states('sensor.temperature') | float > 35 %}
              ["447829999999", "447829999990", "447829999991"]
            {% else %}
              ["447829999999"]
            {% endif %}
          template: "temperature_alert"
          variables:
            temp: "{{ states('sensor.temperature') }}"
            location: "Server Room"
          priority: >
            {% if states('sensor.temperature') | float > 35 %}
              20
            {% else %}
              10
            {% endif %}
```

### Escalating Alerts

```yaml
automation:
  - alias: "Water Leak Detection"
    trigger:
      - platform: state
        entity_id: binary_sensor.water_leak
        to: 'on'
    action:
      # First alert
      - service: rest_command.send_orzi_sms
        data:
          recipients: ["447829999999"]
          message: "WATER LEAK DETECTED!"
          priority: 50
      
      # Wait 5 minutes
      - delay: '00:05:00'
      
      # Check if still leaking
      - condition: state
        entity_id: binary_sensor.water_leak
        state: 'on'
        
      # Escalated alert to more people
      - service: rest_command.send_orzi_sms
        data:
          recipients: ["447829999999", "447829999990"]
          message: "URGENT: Water leak still active after 5 minutes!"
          priority: 100
          use_queue: false
```

## API Endpoints

### POST /send
Send a standard SMS message

**Request:**
```json
{
  "recipients": ["447829999999", "447829999990"],
  "message": "Your SMS message",
  "priority": 5,
  "use_queue": true
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "SMS sent successfully",
  "status_code": 200
}
```

**Response (Queued):**
```json
{
  "success": true,
  "message": "Message queued due to rate limit",
  "queued": true,
  "queue_size": 3
}
```

**Response (Error):**
```json
{
  "success": false,
  "message": "API error: 401"
}
```

### POST /send_template
Send SMS using a template

**Request:**
```json
{
  "recipients": ["447829999999"],
  "template": "security_alert",
  "variables": {
    "sensor": "Motion Sensor",
    "time": "14:30:00"
  },
  "priority": 10
}
```

### GET /templates
List all available templates

**Response:**
```json
{
  "success": true,
  "templates": {
    "security_alert": "ALERT: {sensor} detected at {time}",
    "temperature_alert": "Temperature is {temp}°C in {location}",
    "door_alert": "{door} was opened at {time}",
    "battery_low": "{device} battery is low: {level}%"
  }
}
```

### GET /queue
Get queue status

**Response:**
```json
{
  "enabled": true,
  "size": 5,
  "max_size": 100,
  "retry_attempts": 3
}
```

### GET /stats
Get service statistics

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_sent": 150,
    "total_failed": 5,
    "total_queued": 20,
    "rate_limited": 10,
    "queue_size": 3,
    "rate_limit_enabled": true,
    "can_send_now": true,
    "wait_time": 0
  }
}
```

### GET /health
Health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "service": "Orzi SMS",
  "version": "2.0.0"
}
```

## Advanced Features

### Priority System
Messages are processed by priority level:
- **0-3**: Low priority (informational)
- **4-6**: Normal priority (standard alerts)
- **7-9**: High priority (warnings)
- **10-50**: Very high priority (important alerts)
- **50+**: Critical priority (emergencies)

Higher priority messages are sent first from the queue.

### Rate Limiting
- Automatically prevents API abuse
- Configurable per-minute and per-hour limits
- Messages automatically queued when limit reached
- Transparent retry after cooldown

### Message Queue
- Persistent across addon restarts
- Priority-based processing
- Automatic retry on failure
- Configurable retry attempts
- Maximum size protection

### Template System
- Reusable message templates
- Variable substitution with `{variable}` syntax
- Centralized message management
- Easy to update without changing automations

## Dashboard Integration

Create a Lovelace card to monitor the service:

```yaml
type: entities
title: Orzi SMS Service
entities:
  - entity: sensor.orzi_sms_stats
    name: Messages Sent
  - type: attribute
    entity: sensor.orzi_sms_stats
    attribute: stats.total_failed
    name: Failed Messages
  - type: attribute
    entity: sensor.orzi_sms_stats
    attribute: stats.total_queued
    name: Queued Messages
  - type: attribute
    entity: sensor.orzi_sms_stats
    attribute: stats.rate_limited
    name: Rate Limited
  - entity: sensor.orzi_sms_queue
    name: Current Queue Size
  - type: attribute
    entity: sensor.orzi_sms_stats
    attribute: stats.can_send_now
    name: Can Send Now
```

## Monitoring & Alerts

### Queue Full Alert

```yaml
automation:
  - alias: "SMS Queue Nearly Full"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.orzi_sms_queue', 'size') >= 
             state_attr('sensor.orzi_sms_queue', 'max_size') * 0.9 }}
    action:
      - service: persistent_notification.create
        data:
          title: "SMS Queue Alert"
          message: "Queue is {{ state_attr('sensor.orzi_sms_queue', 'size') }}/{{ state_attr('sensor.orzi_sms_queue', 'max_size') }}"
```

### Service Health Check

```yaml
binary_sensor:
  - platform: rest
    name: Orzi SMS Health
    resource: http://localhost:8099/health
    value_template: "{{ value_json.status == 'healthy' }}"
    scan_interval: 60

automation:
  - alias: "SMS Service Down"
    trigger:
      - platform: state
        entity_id: binary_sensor.orzi_sms_health
        to: 'off'
    action:
      - service: persistent_notification.create
        data:
          title: "SMS Service Alert"
          message: "Orzi SMS service is not responding"
```

## Best Practices

### 1. Use Templates for Common Messages
Reduces duplication and makes updates easier.

### 2. Set Appropriate Priorities
- Critical security: 50-100
- Important warnings: 10-49
- Normal alerts: 5-9
- Informational: 0-4

### 3. Use Queue Wisely
- Critical messages: `use_queue: false`
- Normal messages: `use_queue: true`

### 4. Monitor Service Health
Set up sensors and alerts to catch issues early.

### 5. Configure Rate Limits
Adjust based on your usage patterns and API limits.

### 6. Test Before Deploying
Use low-priority test messages to verify configuration.

## Troubleshooting

### Check Addon Logs
1. Go to **Settings → Add-ons → Orzi SMS Notifications**
2. Click the **Log** tab
3. Look for errors or warnings

### Common Issues

**"API key not configured"**
- Verify API key in addon configuration
- Ensure no extra spaces in the key
- Restart addon after changes

**"Rate limit exceeded"**
- Messages are automatically queued
- Check `/queue` endpoint for status
- Messages will send when limit resets
- Consider increasing rate limits if needed

**"Queue is full"**
- Too many failed/pending messages
- Check API key validity
- Check network connectivity
- Restart addon to reset queue
- Increase `max_size` in configuration

**"Template not found"**
- Check template name spelling
- Use `/templates` endpoint to list available templates
- Ensure template is in addon configuration

**Messages not sending**
- Verify addon is running
- Check API key is valid
- Test with `/health` endpoint
- Review addon logs for errors
- Try manual curl test (see below)

### Manual Testing

**Test basic send:**
```bash
curl -X POST http://localhost:8099/send \
  -H "Content-Type: application/json" \
  -d '{"recipients":["447829999999"],"message":"Test message"}'
```

**Test template send:**
```bash
curl -X POST http://localhost:8099/send_template \
  -H "Content-Type: application/json" \
  -d '{"recipients":["447829999999"],"template":"security_alert","variables":{"sensor":"Test","time":"now"}}'
```

**Check health:**
```bash
curl http://localhost:8099/health
```

**Check stats:**
```bash
curl http://localhost:8099/stats
```

**Check queue:**
```bash
curl http://localhost:8099/queue
```

**List templates:**
```bash
curl http://localhost:8099/templates
```

### Reset Queue

If the queue has corrupted data:

1. Stop the addon
2. Delete `/addon_configs/orzi_sms/queue.json`
3. Start the addon

### Enable Debug Logging

In addon configuration:
```yaml
log_level: debug
```

Restart the addon and check logs for detailed information.

## Support

For issues, questions, or feature requests:
- Review this documentation
- Check addon logs
- Test endpoints manually
- Review Home Assistant logs

## Changelog

### v2.0.0 (Current)
- ✨ Added message templates with variable substitution
- ✨ Added rate limiting (per-minute and per-hour)
- ✨ Added message queuing with priority support
- ✨ Added automatic retry logic
- ✨ Added statistics endpoint
- ✨ Persistent queue across restarts
- 🐛 Improved error handling
- 📝 Comprehensive documentation

### v1.0.0
- 🎉 Initial release
- ✅ Basic SMS sending
- ✅ REST API endpoints
- ✅ Health check endpoint

## License

This addon is provided as-is for use with the Orzi SMS API service.

## Credits

Created for Home Assistant integration with Orzi SMS API.