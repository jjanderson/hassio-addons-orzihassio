import asyncio
import aiohttp
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from collections import deque
from aiohttp import web
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
ORZI_API_URL = 'https://api.orzi.app/api/SMS/Send'
CONFIG_FILE = '/data/config.json'
QUEUE_FILE = '/data/queue.json'

class RateLimiter:
    """Rate limiter to prevent API abuse"""
    
    def __init__(self, max_per_minute=10, max_per_hour=60):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.minute_requests = deque()
        self.hour_requests = deque()
        
    def can_send(self) -> bool:
        """Check if we can send based on rate limits"""
        now = time.time()
        
        # Clean old entries
        minute_ago = now - 60
        hour_ago = now - 3600
        
        while self.minute_requests and self.minute_requests[0] < minute_ago:
            self.minute_requests.popleft()
            
        while self.hour_requests and self.hour_requests[0] < hour_ago:
            self.hour_requests.popleft()
            
        # Check limits
        if len(self.minute_requests) >= self.max_per_minute:
            return False
        if len(self.hour_requests) >= self.max_per_hour:
            return False
            
        return True
        
    def record_request(self):
        """Record a request"""
        now = time.time()
        self.minute_requests.append(now)
        self.hour_requests.append(now)
        
    def get_wait_time(self) -> int:
        """Get seconds to wait before next request"""
        if not self.minute_requests and not self.hour_requests:
            return 0
            
        now = time.time()
        wait_time = 0
        
        if len(self.minute_requests) >= self.max_per_minute:
            wait_time = max(wait_time, 60 - (now - self.minute_requests[0]))
            
        if len(self.hour_requests) >= self.max_per_hour:
            wait_time = max(wait_time, 3600 - (now - self.hour_requests[0]))
            
        return int(wait_time) + 1

class MessageQueue:
    """Queue for SMS messages with retry logic"""
    
    def __init__(self, max_size=100, retry_attempts=3):
        self.max_size = max_size
        self.retry_attempts = retry_attempts
        self.queue = deque()
        self.processing = False
        self.load_queue()
        
    def load_queue(self):
        """Load queue from disk"""
        try:
            with open(QUEUE_FILE, 'r') as f:
                data = json.load(f)
                self.queue = deque(data)
                logger.info(f"Loaded {len(self.queue)} messages from queue")
        except FileNotFoundError:
            logger.info("No existing queue file found")
        except Exception as e:
            logger.error(f"Error loading queue: {str(e)}")
            
    def save_queue(self):
        """Save queue to disk"""
        try:
            with open(QUEUE_FILE, 'w') as f:
                json.dump(list(self.queue), f)
        except Exception as e:
            logger.error(f"Error saving queue: {str(e)}")
            
    def add(self, recipients: List[str], message: str, priority: int = 0) -> bool:
        """Add message to queue"""
        if len(self.queue) >= self.max_size:
            logger.warning("Queue is full, cannot add message")
            return False
            
        item = {
            'recipients': recipients,
            'message': message,
            'priority': priority,
            'attempts': 0,
            'added_at': datetime.now().isoformat()
        }
        
        self.queue.append(item)
        self.save_queue()
        logger.info(f"Added message to queue. Queue size: {len(self.queue)}")
        return True
        
    def get_next(self) -> Optional[Dict]:
        """Get next message from queue"""
        if not self.queue:
            return None
            
        # Sort by priority (higher first)
        sorted_queue = sorted(self.queue, key=lambda x: x['priority'], reverse=True)
        item = sorted_queue[0]
        self.queue.remove(item)
        return item
        
    def requeue(self, item: Dict):
        """Requeue failed message"""
        item['attempts'] += 1
        if item['attempts'] < self.retry_attempts:
            self.queue.append(item)
            self.save_queue()
            logger.info(f"Requeued message. Attempt {item['attempts']}/{self.retry_attempts}")
        else:
            logger.error(f"Message failed after {self.retry_attempts} attempts. Discarding.")
            
    def size(self) -> int:
        """Get queue size"""
        return len(self.queue)

class TemplateManager:
    """Manage message templates"""
    
    def __init__(self, templates: Dict[str, str]):
        self.templates = templates
        
    def render(self, template_name: str, **kwargs) -> Optional[str]:
        """Render a template with provided variables"""
        if template_name not in self.templates:
            logger.warning(f"Template '{template_name}' not found")
            return None
            
        template = self.templates[template_name]
        
        try:
            # Replace placeholders
            message = template.format(**kwargs)
            return message
        except KeyError as e:
            logger.error(f"Missing variable in template: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error rendering template: {str(e)}")
            return None
            
    def list_templates(self) -> List[str]:
        """Get list of available templates"""
        return list(self.templates.keys())
        
    def get_template(self, template_name: str) -> Optional[str]:
        """Get raw template"""
        return self.templates.get(template_name)

class OrziSMSService:
    """Main SMS service with rate limiting and queuing"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.api_key = config['api_key']
        self.session = None
        
        # Initialize rate limiter
        rate_config = config.get('rate_limit', {})
        if rate_config.get('enabled', True):
            self.rate_limiter = RateLimiter(
                max_per_minute=rate_config.get('max_per_minute', 10),
                max_per_hour=rate_config.get('max_per_hour', 60)
            )
        else:
            self.rate_limiter = None
            
        # Initialize queue
        queue_config = config.get('queue', {})
        if queue_config.get('enabled', True):
            self.queue = MessageQueue(
                max_size=queue_config.get('max_size', 100),
                retry_attempts=queue_config.get('retry_attempts', 3)
            )
        else:
            self.queue = None
            
        # Initialize template manager
        templates = config.get('templates', {})
        self.template_manager = TemplateManager(templates)
        
        # Statistics
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'total_queued': 0,
            'rate_limited': 0
        }
        
    async def start(self):
        """Initialize the service"""
        self.session = aiohttp.ClientSession()
        logger.info("Orzi SMS Service started")
        
        # Start queue processor
        if self.queue:
            asyncio.create_task(self.process_queue())
            
    async def stop(self):
        """Stop the service"""
        if self.session:
            await self.session.close()
        logger.info("Orzi SMS Service stopped")
        
    async def process_queue(self):
        """Process queued messages"""
        logger.info("Queue processor started")
        
        while True:
            try:
                if self.queue and self.queue.size() > 0:
                    # Check rate limit
                    if self.rate_limiter and not self.rate_limiter.can_send():
                        wait_time = self.rate_limiter.get_wait_time()
                        logger.info(f"Rate limit reached. Waiting {wait_time} seconds")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    # Get next message
                    item = self.queue.get_next()
                    if item:
                        logger.info("Processing queued message")
                        result = await self._send_sms_direct(
                            item['recipients'],
                            item['message']
                        )
                        
                        if not result['success']:
                            self.queue.requeue(item)
                        else:
                            self.stats['total_sent'] += 1
                            
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in queue processor: {str(e)}")
                await asyncio.sleep(10)
                
    async def send_sms(self, recipients: List[str], message: str, priority: int = 0, use_queue: bool = True) -> Dict:
        """
        Send SMS with rate limiting and queuing
        
        Args:
            recipients: List of phone numbers
            message: SMS message text
            priority: Priority level (higher = more important)
            use_queue: Whether to use queue if rate limited
            
        Returns:
            dict: Response with success status
        """
        if not self.api_key:
            return {
                'success': False,
                'message': 'API key not configured'
            }
            
        # Ensure recipients is a list
        if isinstance(recipients, str):
            recipients = [recipients]
            
        # Check rate limit
        if self.rate_limiter and not self.rate_limiter.can_send():
            if use_queue and self.queue:
                # Add to queue
                if self.queue.add(recipients, message, priority):
                    self.stats['total_queued'] += 1
                    self.stats['rate_limited'] += 1
                    return {
                        'success': True,
                        'message': 'Message queued due to rate limit',
                        'queued': True,
                        'queue_size': self.queue.size()
                    }
                else:
                    return {
                        'success': False,
                        'message': 'Queue is full'
                    }
            else:
                wait_time = self.rate_limiter.get_wait_time()
                self.stats['rate_limited'] += 1
                return {
                    'success': False,
                    'message': f'Rate limit exceeded. Wait {wait_time} seconds',
                    'wait_time': wait_time
                }
                
        # Send directly
        result = await self._send_sms_direct(recipients, message)
        
        if result['success']:
            self.stats['total_sent'] += 1
        else:
            self.stats['total_failed'] += 1
            
            # Queue on failure if enabled
            if use_queue and self.queue:
                self.queue.add(recipients, message, priority)
                self.stats['total_queued'] += 1
                result['queued'] = True
                
        return result
        
    async def _send_sms_direct(self, recipients: List[str], message: str) -> Dict:
        """Send SMS directly to API"""
        payload = {
            'MobilenumberList': recipients,
            'SMSBody': message
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Key': self.api_key
        }
        
        try:
            logger.info(f"Sending SMS to {len(recipients)} recipient(s)")
            
            async with self.session.post(
                ORZI_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_text = await response.text()
                
                # Record rate limit
                if self.rate_limiter:
                    self.rate_limiter.record_request()
                
                if response.status >= 200 and response.status < 300:
                    logger.info(f"SMS sent successfully: {response.status}")
                    return {
                        'success': True,
                        'message': 'SMS sent successfully',
                        'status_code': response.status,
                        'response': response_text
                    }
                else:
                    logger.error(f"API error: {response.status} - {response_text}")
                    return {
                        'success': False,
                        'message': f'API error: {response.status}',
                        'response': response_text
                    }
                    
        except asyncio.TimeoutError:
            logger.error("Request timeout")
            return {
                'success': False,
                'message': 'Request timeout'
            }
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

# Load configuration
def load_config():
    """Load configuration from file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        return {
            'api_key': '',
            'rate_limit': {'enabled': True, 'max_per_minute': 10, 'max_per_hour': 60},
            'queue': {'enabled': True, 'max_size': 100, 'retry_attempts': 3},
            'templates': {}
        }

config = load_config()
sms_service = OrziSMSService(config)

# Web server handlers
async def handle_send_sms(request):
    """Handle SMS send requests"""
    try:
        data = await request.json()
        
        recipients = data.get('recipients', [])
        message = data.get('message', '')
        priority = data.get('priority', 0)
        use_queue = data.get('use_queue', True)
        
        if not recipients:
            return web.json_response({
                'success': False,
                'message': 'No recipients specified'
            }, status=400)
            
        if not message:
            return web.json_response({
                'success': False,
                'message': 'No message specified'
            }, status=400)
            
        result = await sms_service.send_sms(recipients, message, priority, use_queue)
        
        status_code = 200 if result['success'] else 500
        return web.json_response(result, status=status_code)
            
    except Exception as e:
        logger.error(f"Error handling send request: {str(e)}")
        return web.json_response({
            'success': False,
            'message': str(e)
        }, status=500)

async def handle_send_template(request):
    """Handle template-based SMS requests"""
    try:
        data = await request.json()
        
        recipients = data.get('recipients', [])
        template_name = data.get('template', '')
        variables = data.get('variables', {})
        priority = data.get('priority', 0)
        
        if not recipients:
            return web.json_response({
                'success': False,
                'message': 'No recipients specified'
            }, status=400)
            
        if not template_name:
            return web.json_response({
                'success': False,
                'message': 'No template specified'
            }, status=400)
            
        # Render template
        message = sms_service.template_manager.render(template_name, **variables)
        
        if not message:
            return web.json_response({
                'success': False,
                'message': f'Template "{template_name}" not found or invalid'
            }, status=400)
            
        result = await sms_service.send_sms(recipients, message, priority)
        
        status_code = 200 if result['success'] else 500
        return web.json_response(result, status=status_code)
            
    except Exception as e:
        logger.error(f"Error handling template request: {str(e)}")
        return web.json_response({
            'success': False,
            'message': str(e)
        }, status=500)

async def handle_list_templates(request):
    """List available templates"""
    templates = {}
    for name in sms_service.template_manager.list_templates():
        templates[name] = sms_service.template_manager.get_template(name)
        
    return web.json_response({
        'success': True,
        'templates': templates
    })

async def handle_queue_status(request):
    """Get queue status"""
    if not sms_service.queue:
        return web.json_response({
            'enabled': False,
            'message': 'Queue is disabled'
        })
        
    return web.json_response({
        'enabled': True,
        'size': sms_service.queue.size(),
        'max_size': sms_service.queue.max_size,
        'retry_attempts': sms_service.queue.retry_attempts
    })

async def handle_stats(request):
    """Get service statistics"""
    stats = sms_service.stats.copy()
    
    if sms_service.queue:
        stats['queue_size'] = sms_service.queue.size()
        
    if sms_service.rate_limiter:
        stats['rate_limit_enabled'] = True
        stats['can_send_now'] = sms_service.rate_limiter.can_send()
        stats['wait_time'] = sms_service.rate_limiter.get_wait_time()
    else:
        stats['rate_limit_enabled'] = False
        
    return web.json_response({
        'success': True,
        'stats': stats
    })

async def handle_health(request):
    """Health check endpoint"""
    return web.json_response({
        'status': 'healthy',
        'service': 'Orzi SMS',
        'version': '2.0.0'
    })

async def init_app():
    """Initialize the web application"""
    app = web.Application()
    
    # Routes
    app.router.add_post('/send', handle_send_sms)
    app.router.add_post('/send_template', handle_send_template)
    app.router.add_get('/templates', handle_list_templates)
    app.router.add_get('/queue', handle_queue_status)
    app.router.add_get('/stats', handle_stats)
    app.router.add_get('/health', handle_health)
    
    await sms_service.start()
    
    return app

async def cleanup(app):
    """Cleanup on shutdown"""
    await sms_service.stop()

if __name__ == '__main__':
    if not config.get('api_key'):
        logger.error("API_KEY not configured!")
        sys.exit(1)
        
    logger.info("Starting Orzi SMS addon v2.0.0...")
    
    app = asyncio.run(init_app())
    app.on_cleanup.append(cleanup)
    
    web.run_app(app, host='0.0.0.0', port=8099)