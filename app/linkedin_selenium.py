"""LinkedIn automation service using Selenium with stealth techniques."""
import logging
import asyncio
import json
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from app.config import get_settings
from app.logging_config import (
    log_operation_start,
    log_operation_success,
    log_operation_error,
    log_workflow_step,
)
from app.utils import (
    fuzzy_match,
    fuzzy_match_score,
    random_delay,
    random_short_delay,
    random_medium_delay,
    random_scroll_amount,
    human_scroll_delay,
    type_like_human,
)

logger = logging.getLogger(__name__)

# Session expiration settings
SESSION_WARNING_DAYS = 25
SESSION_MAX_AGE_DAYS = 30


class LinkedInPost:
    """Represents a scraped LinkedIn post."""
    
    def __init__(
        self,
        url: str,
        author_handle: str,
        author_name: str,
        content: str,
        post_date: Optional[datetime] = None,
        likes: int = 0,
        comments: int = 0,
    ):
        self.url = url
        self.author_handle = author_handle
        self.author_name = author_name
        self.content = content
        self.post_date = post_date or datetime.utcnow()
        self.likes = likes
        self.comments = comments


class LinkedInSeleniumAutomation:
    """
    LinkedIn automation using Selenium with undetected-chromedriver.
    
    This bypasses LinkedIn's bot detection better than Playwright.
    """
    
    def __init__(self, headless: bool = True, email: str = None, password: str = None):
        """
        Initialize the LinkedIn Selenium service.
        
        Args:
            headless: Run browser in headless mode
            email: LinkedIn email for login
            password: LinkedIn password for login
        """
        self.headless = headless
        self.email = email
        self.password = password
        self.driver = None
        self.is_logged_in = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Session file paths
        self.session_dir = Path("/app/data/linkedin_session")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = self.session_dir / "selenium_cookies.json"
        self.session_metadata_file = self.session_dir / "metadata.json"
        
        # Thread pool for running sync Selenium in async context
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        logger.info("🌐 LinkedIn Selenium Automation initialized")
        logger.info(f"   Headless mode: {self.headless}")
        logger.info(f"   Session dir: {self.session_dir}")
        logger.info(f"   Cookies file exists: {self.cookies_file.exists()}")
    
    def get_session_age(self) -> Optional[int]:
        """Get the age of the current session in days."""
        if not self.session_metadata_file.exists():
            return None
        
        try:
            with open(self.session_metadata_file, 'r') as f:
                metadata = json.load(f)
                created_at = datetime.fromisoformat(metadata['created_at'])
                age_days = (datetime.utcnow() - created_at).days
                return age_days
        except Exception as e:
            logger.warning(f"⚠️  Could not read session metadata: {e}")
            return None
    
    def check_session_health(self) -> Dict[str, Any]:
        """Check the health of the current session."""
        age_days = self.get_session_age()
        
        health = {
            'has_session': self.cookies_file.exists(),
            'age_days': age_days,
            'needs_refresh': False,
            'expired': False,
            'status': 'unknown'
        }
        
        if not health['has_session']:
            health['status'] = 'no_session'
            health['expired'] = True
            return health
        
        if age_days is None:
            health['status'] = 'unknown_age'
            return health
        
        if age_days >= SESSION_MAX_AGE_DAYS:
            health['status'] = 'expired'
            health['expired'] = True
            health['needs_refresh'] = True
        elif age_days >= SESSION_WARNING_DAYS:
            health['status'] = 'warning'
            health['needs_refresh'] = True
        else:
            health['status'] = 'healthy'
        
        return health
    
    def _start_driver(self):
        """Start the Chrome driver with stealth (sync)."""
        try:
            options = Options()
            
            if self.headless:
                options.add_argument('--headless=new')
            
            # Stealth arguments
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Use system Chromium
            options.binary_location = '/usr/bin/chromium'
            
            # Create service for chromedriver
            service = Service('/usr/bin/chromedriver')
            
            # Create driver
            self.driver = webdriver.Chrome(service=service, options=options)
            
            # Execute CDP commands to hide automation
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    window.chrome = {
                        runtime: {}
                    };
                '''
            })
            
            logger.info("✅ Chrome driver started with stealth")
            
            # Login with email/password
            if self.email and self.password:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                logger.info("🔑 Logging in with email/password...")
                self.driver.get("https://www.linkedin.com/login")
                time.sleep(3)
                
                # Fill email
                email_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                email_field.send_keys(self.email)
                
                # Fill password
                password_field = self.driver.find_element(By.ID, "password")
                password_field.send_keys(self.password)
                
                # Click sign in
                sign_in_button = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                sign_in_button.click()
                
                # Wait for login
                time.sleep(5)
                
                current_url = self.driver.current_url
                if 'feed' in current_url or 'in/' in current_url:
                    logger.info(f"✅ Login successful - on: {current_url}")
                    self.is_logged_in = True
                elif 'checkpoint' in current_url or 'challenge' in current_url:
                    logger.warning("⚠️  Verification challenge detected - may need manual intervention")
                    # Raise exception so the async wrapper can handle it
                    raise Exception("LinkedIn security challenge detected during login")
                else:
                    logger.warning(f"⚠️  Unexpected URL after login: {current_url}")
                    self.is_logged_in = True  # Try anyway
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start driver: {e}")
            raise
    
    async def start(self):
        """Start the driver (async wrapper)."""
        log_operation_start(logger, "start_selenium_driver", headless=self.headless)
        
        try:
            # Run sync driver start in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._start_driver)
            
            log_operation_success(logger, "start_selenium_driver")
            
        except Exception as e:
            # Check if this was a security challenge during login
            error_message = str(e)
            if "security challenge" in error_message.lower():
                logger.warning(f"🚨 Security challenge detected during login")
                
                # Send alert email
                await self._send_security_alert_email(context="login")
                
                # Wait for resolution
                logger.info(f"⏳ Pausing to wait for security challenge resolution...")
                resolved = await self._wait_for_security_challenge_resolution(max_wait_minutes=30)
                
                if resolved:
                    logger.info(f"✅ Challenge resolved! Login should be complete.")
                    self.is_logged_in = True
                else:
                    logger.error(f"❌ Security challenge not resolved, login may have failed")
                    raise
            else:
                log_operation_error(logger, "start_selenium_driver", e)
                raise
    
    def _stop_driver(self):
        """Stop the driver (sync)."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Driver stopped")
            except Exception as e:
                logger.warning(f"⚠️  Error stopping driver: {e}")
    
    async def stop(self):
        """Stop the driver (async wrapper)."""
        log_operation_start(logger, "stop_selenium_driver")
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._stop_driver)
            
            log_operation_success(logger, "stop_selenium_driver")
            
        except Exception as e:
            log_operation_error(logger, "stop_selenium_driver", e)
    
    def _check_for_security_challenge(self) -> bool:
        """
        Check if LinkedIn is showing a security challenge.
        
        Returns:
            True if challenge detected, False otherwise
        """
        try:
            current_url = self.driver.current_url
            page_source = self.driver.page_source.lower()
            
            # Check for various security challenge indicators
            challenge_indicators = [
                'checkpoint' in current_url,
                'challenge' in current_url,
                'security' in current_url and 'check' in page_source,
                "let's do a quick security check" in page_source,
                'verify' in current_url and 'security' in page_source,
                'unusual activity' in page_source,
            ]
            
            if any(challenge_indicators):
                logger.warning("🚨 LinkedIn security challenge detected!")
                logger.warning(f"   Current URL: {current_url}")
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking for security challenge: {e}")
            return False
    
    async def _send_security_alert_email(self, context: str = "scraping"):
        """
        Send an email alert to admin when security challenge is detected.
        
        Args:
            context: What operation was being performed when challenge was detected
        """
        try:
            from app.email import get_email_service
            from app.config import get_settings
            from datetime import datetime
            
            settings = get_settings()
            email_service = get_email_service()
            
            current_url = self.driver.current_url
            
            # Create alert email
            subject = "🚨 LinkedIn Security Check Required"
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .alert-box {{
                        background: #fff3cd;
                        border: 2px solid #ffc107;
                        border-radius: 8px;
                        padding: 20px;
                        margin: 20px 0;
                    }}
                    .alert-icon {{
                        font-size: 48px;
                        text-align: center;
                        margin-bottom: 10px;
                    }}
                    h1 {{
                        color: #856404;
                        margin: 0 0 10px 0;
                        font-size: 24px;
                    }}
                    .info {{
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 4px;
                        margin: 15px 0;
                    }}
                    .info-label {{
                        font-weight: bold;
                        color: #666;
                    }}
                    .action-required {{
                        background: #d1ecf1;
                        border-left: 4px solid #0c5460;
                        padding: 15px;
                        margin: 20px 0;
                    }}
                    .btn {{
                        display: inline-block;
                        background: #0066cc;
                        color: white !important;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                        margin: 10px 0;
                    }}
                    code {{
                        background: #f4f4f4;
                        padding: 2px 6px;
                        border-radius: 3px;
                        font-family: monospace;
                    }}
                </style>
            </head>
            <body>
                <div class="alert-box">
                    <div class="alert-icon">⚠️</div>
                    <h1>LinkedIn Security Check Required</h1>
                    <p>The LinkedIn scraper has encountered a security challenge and needs manual intervention.</p>
                </div>
                
                <div class="info">
                    <p><span class="info-label">Context:</span> {context}</p>
                    <p><span class="info-label">Current URL:</span> <code>{current_url}</code></p>
                    <p><span class="info-label">Time:</span> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                </div>
                
                <div class="action-required">
                    <h3 style="margin-top: 0;">Action Required:</h3>
                    
                    <p><a href="{settings.app_base_url}/admin/vnc" class="btn">
                        🖥️ Click Here to Open VNC in Browser
                    </a></p>
                    
                    <ol style="margin-top: 15px;">
                        <li>Click the button above to open the VNC viewer in your browser</li>
                        <li>You'll see the LinkedIn page with the security challenge</li>
                        <li>Complete the challenge (click captcha, verify identity, etc.)</li>
                        <li>The scraper will automatically continue once you're done</li>
                    </ol>
                    
                    <p style="margin-top: 15px; font-size: 14px; color: #666;">
                        <strong>Alternative:</strong> Connect via VNC client to <code>localhost:5900</code> (if on local machine)
                    </p>
                </div>
                
                <p style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 14px;">
                    This is an automated alert from your LinkedIn Reposter system.
                </p>
            </body>
            </html>
            """
            
            plain_body = f"""
LinkedIn Security Check Required

The scraper encountered a security challenge and needs your help.

Context: {context}
Current URL: {current_url}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

ACTION REQUIRED:
1. Open in browser: {settings.app_base_url}/admin/vnc
2. Complete the security challenge
3. The scraper will automatically continue

Alternative: Connect via VNC client to localhost:5900
            """
            
            # Send via Postal
            response = await email_service.send_email(
                to=settings.approval_email,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body
            )
            
            logger.info(f"📧 Security alert email sent to {settings.approval_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send security alert email: {e}")
            return False
    
    async def _wait_for_security_challenge_resolution(self, max_wait_minutes: int = 30):
        """
        Wait for user to manually resolve security challenge.
        
        Args:
            max_wait_minutes: Maximum time to wait before giving up
            
        Returns:
            True if challenge was resolved, False if timeout
        """
        logger.warning(f"⏳ Waiting up to {max_wait_minutes} minutes for security challenge resolution...")
        logger.warning(f"   Please connect to VNC and complete the challenge")
        
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        check_interval = 10  # Check every 10 seconds
        
        while time.time() - start_time < max_wait_seconds:
            # Run check in thread pool since it's sync
            loop = asyncio.get_event_loop()
            challenge_still_present = await loop.run_in_executor(
                self.executor,
                self._check_for_security_challenge
            )
            
            # Check if we're past the security challenge
            if not challenge_still_present:
                logger.info("✅ Security challenge resolved!")
                return True
            
            # Wait before checking again
            await asyncio.sleep(check_interval)
            
            # Log progress every minute
            elapsed_minutes = int((time.time() - start_time) / 60)
            if elapsed_minutes > 0 and (time.time() - start_time) % 60 < check_interval:
                remaining = max_wait_minutes - elapsed_minutes
                logger.info(f"⏳ Still waiting... {remaining} minutes remaining")
        
        logger.error(f"❌ Timeout: Security challenge not resolved after {max_wait_minutes} minutes")
        return False
    
    def _save_cookies(self):
        """Save cookies to file (sync)."""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"✅ Cookies saved to {self.cookies_file}")
            
            # Save metadata
            metadata = {
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            with open(self.session_metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"✅ Metadata saved to {self.session_metadata_file}")
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to save cookies: {e}")
    
    def _login_with_cookie(self, li_at_cookie: str) -> Dict[str, Any]:
        """Login with li_at cookie (sync)."""
        try:
            # Navigate to LinkedIn first
            self.driver.get("https://www.linkedin.com")
            time.sleep(2)
            
            # Add the li_at cookie
            self.driver.add_cookie({
                'name': 'li_at',
                'value': li_at_cookie,
                'domain': '.linkedin.com',
                'path': '/',
                'secure': True,
                'httpOnly': True
            })
            
            logger.info("🍪 Cookie added to browser")
            
            # Refresh the page to apply cookies
            self.driver.refresh()
            time.sleep(3)
            
            # Check if we're logged in by looking for profile indicator
            try:
                # If we see sign-in button, cookies didn't work
                if "authwall" in self.driver.current_url or "login" in self.driver.current_url:
                    logger.error("❌ Cookie authentication failed - redirected to login")
                    raise Exception("Cookie is invalid or expired. Please get a fresh cookie from your browser.")
                else:
                    logger.info("✅ Cookie authentication successful")
            except:
                pass
            
            # Save cookies
            self._save_cookies()
            
            self.is_logged_in = True
            
            return {
                "success": True,
                "message": "Cookie saved successfully",
                "cookies_file": str(self.cookies_file)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to login with cookie: {e}")
            raise
    
    async def login_with_cookies(self, li_at_cookie: str) -> Dict[str, Any]:
        """Login with li_at cookie (async wrapper)."""
        log_operation_start(logger, "selenium_login_with_cookies")
        
        try:
            # Start driver first
            await self.start()
            
            # Run login in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._login_with_cookie,
                li_at_cookie
            )
            
            log_operation_success(logger, "selenium_login_with_cookies")
            
            return result
            
        except Exception as e:
            log_operation_error(logger, "selenium_login_with_cookies", e)
            raise
        finally:
            await self.stop()
    
    def _scrape_user_posts(
        self,
        handle: str,
        max_posts: int = 10,
        days_back: int = 7
    ) -> List[LinkedInPost]:
        """Scrape posts from a user (sync)."""
        try:
            if not self.is_logged_in:
                raise Exception("Not logged in")
            
            # Construct profile URL - support company pages with company/ prefix
            if handle.startswith("company/"):
                # Company page format: /company/{handle}/posts/
                company_handle = handle.replace("company/", "")
                profile_url = f"https://www.linkedin.com/company/{company_handle}/posts/"
                logger.info(f"🏢 Navigating to company page: {company_handle}...")
            else:
                # Personal profile format: /in/{handle}/recent-activity/all/
                profile_url = f"https://www.linkedin.com/in/{handle}/recent-activity/all/"
                logger.info(f"🔍 Navigating to {handle}'s profile...")
            
            self.driver.get(profile_url)
            
            # Check for security challenge after navigation
            if self._check_for_security_challenge():
                logger.warning(f"🚨 Security challenge detected while accessing {handle}")
                # Since we're in sync code, we can't await here
                # The challenge will need to be handled by the async wrapper
                raise Exception(f"LinkedIn security challenge detected for {handle}")
            
            # Wait for page load
            time.sleep(5)
            
            # Scroll to load posts
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            posts = []
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            # NEW APPROACH: Grab entire page HTML and parse with BeautifulSoup
            logger.info("📦 Extracting page HTML for parsing...")
            page_html = self.driver.page_source
            
            # Save HTML for parsing
            html_file = f"/app/data/linkedin_page_{handle}.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(page_html)
            logger.info(f"💾 Page HTML saved to {html_file}")
            
            # Parse with BeautifulSoup outside the Selenium context
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page_html, 'html.parser')
            
            # STRATEGY 1: Find posts by "Feed post number X" headers
            post_headers = soup.find_all('h2', class_='visually-hidden', string=lambda s: s and 'Feed post number' in s)
            logger.info(f"🔍 Found {len(post_headers)} posts via 'Feed post number' headers")
            
            if not post_headers:
                # FALLBACK: Try fie-impression-container
                post_containers = soup.find_all('div', class_=lambda c: c and 'fie-impression-container' in c)
                logger.info(f"🔍 Fallback: Found {len(post_containers)} post containers with fie-impression-container")
                
                if not post_containers:
                    logger.warning(f"⚠️  No post containers found. Current URL: {self.driver.current_url}")
                    logger.warning(f"⚠️  Page HTML saved to {html_file} for inspection")
                    return []
                
                # Use containers as posts
                posts_to_parse = post_containers
            else:
                # Use the parent elements of the headers
                posts_to_parse = [h.parent for h in post_headers if h.parent]
            
            logger.info(f"✅ Found {len(posts_to_parse)} posts to parse")
            
            # Parse each post
            for idx, post_element in enumerate(posts_to_parse[:max_posts]):
                try:
                    # SKIP REPOSTS - Check if this is a repost/reshare
                    # Look for text like "reposted this", "shared this", etc.
                    post_html = str(post_element)
                    if any(indicator in post_html.lower() for indicator in ['reposted this', 'shared this', 'reshared']):
                        logger.info(f"⏭️  Skipping post {idx+1} - detected as repost/reshare")
                        continue
                    
                    # Extract all text from the post element
                    # Try to find the actual post content container
                    content = ""
                    
                    # Strategy 1: Look for fie-impression-container within this post
                    impression_container = post_element.find('div', class_=lambda c: c and 'fie-impression-container' in c)
                    if impression_container:
                        # Extract all spans and get the longest text
                        text_spans = impression_container.find_all('span')
                        for span in text_spans:
                            text = span.get_text(strip=True)
                            if text and len(text) > len(content):
                                content = text
                    
                    # Strategy 2: If no impression container, get all text from post element
                    if not content:
                        content = post_element.get_text(separator=' ', strip=True)
                        # Remove the "Feed post number X" text if present
                        content = content.replace('Feed post number', '').strip()
                        # Clean up multiple spaces
                        import re
                        content = re.sub(r'\s+', ' ', content)
                    
                    if not content or len(content) < 10:
                        logger.debug(f"⚠️  Skipping post {idx+1} - no substantial content")
                        continue
                    
                    # Extract author name from the profile page or post metadata
                    # Default to formatted handle if we can't find the name
                    author_name = handle.replace('-', ' ').replace('company/', '').title()
                    
                    # Strategy 1: Look for profile name in the page header (h1)
                    name_header = soup.find('h1', class_=lambda c: c and 'text-heading-xlarge' in c)
                    if not name_header:
                        # Alternative: try company name
                        name_header = soup.find('h1', class_=lambda c: c and ('org-top-card' in str(c) or 'org-name' in str(c)))
                    
                    if name_header:
                        extracted_name = name_header.get_text(strip=True)
                        if extracted_name and len(extracted_name) > 3:  # Minimum length check
                            author_name = extracted_name
                            logger.debug(f"   📝 Extracted author name from header: {author_name}")
                    else:
                        # Strategy 2: Look for the author name in the post metadata
                        # Posts usually have the author name in a span or link near the top
                        author_link = soup.find('a', class_=lambda c: c and 'app-aware-link' in c)
                        if author_link:
                            potential_name = author_link.get_text(strip=True)
                            if potential_name and len(potential_name) > 3 and potential_name.lower() != handle.lower():
                                author_name = potential_name
                                logger.debug(f"   📝 Extracted author name from link: {author_name}")
                        else:
                            logger.debug(f"   📝 Using formatted handle as name: {author_name}")
                    
                    # EXTRACT UNIQUE POST URL - Look for activity URN
                    post_url = None
                    
                    # Try to find link with activity ID
                    link = post_element.find('a', href=lambda h: h and ('/posts/' in h or '/activity/' in h or 'urn:li:activity' in h))
                    if link:
                        href = link.get('href', '')
                        if href:
                            # Extract activity ID if present
                            if 'urn:li:activity:' in href or '/activity-' in href or '/posts/' in href:
                                post_url = href if href.startswith('http') else f"https://www.linkedin.com{href}"
                    
                    # Fallback: Try to extract from data attributes
                    if not post_url:
                        # Look for data-urn or similar attributes
                        urn = post_element.get('data-urn') or post_element.get('data-id')
                        if urn and 'activity' in str(urn):
                            post_url = f"https://www.linkedin.com/feed/update/{urn}/"
                    
                    # Last resort: use profile URL + timestamp
                    if not post_url:
                        timestamp = int(datetime.utcnow().timestamp())
                        post_url = f"{profile_url}#post-{timestamp}-{idx}"
                        logger.warning(f"⚠️  Could not find unique activity ID for post {idx+1}, using fallback URL")
                    
                    post = LinkedInPost(
                        url=post_url,
                        author_handle=handle,
                        author_name=author_name,
                        content=content.strip(),
                        post_date=datetime.utcnow()
                    )
                    
                    posts.append(post)
                    logger.info(f"✅ Scraped post {idx+1}: {content[:80]}...")
                    logger.debug(f"   URL: {post_url}")
                    
                except Exception as e:
                    logger.warning(f"⚠️  Failed to extract post {idx+1}: {e}")
                    continue
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Scraping failed: {e}")
            raise
    
    async def scrape_user_posts(
        self,
        handle: str,
        max_posts: int = 10,
        days_back: int = 7
    ) -> List[LinkedInPost]:
        """Scrape posts from a user (async wrapper)."""
        log_operation_start(logger, "selenium_scrape_posts", handle=handle, max_posts=max_posts)
        
        try:
            # Run scraping in thread pool
            loop = asyncio.get_event_loop()
            posts = await loop.run_in_executor(
                self.executor,
                self._scrape_user_posts,
                handle,
                max_posts,
                days_back
            )
            
            log_operation_success(logger, "selenium_scrape_posts", posts_count=len(posts))
            
            return posts
            
        except Exception as e:
            # Check if this was a security challenge
            error_message = str(e)
            if "security challenge" in error_message.lower():
                logger.warning(f"🚨 Security challenge detected for @{handle}")
                
                # Send alert email
                await self._send_security_alert_email(context=f"scraping @{handle}")
                
                # Wait for resolution
                logger.info(f"⏳ Pausing scrape to wait for security challenge resolution...")
                resolved = await self._wait_for_security_challenge_resolution(max_wait_minutes=30)
                
                if resolved:
                    logger.info(f"✅ Challenge resolved! Retrying scrape for @{handle}...")
                    # Retry the scrape
                    posts = await loop.run_in_executor(
                        self.executor,
                        self._scrape_user_posts,
                        handle,
                        max_posts,
                        days_back
                    )
                    log_operation_success(logger, "selenium_scrape_posts", posts_count=len(posts))
                    return posts
                else:
                    logger.error(f"❌ Security challenge not resolved, skipping @{handle}")
                    return []  # Return empty list to continue with other handles
            
            log_operation_error(logger, "selenium_scrape_posts", e)
            raise
    
    def _find_post_by_content(
        self,
        author_handle: str,
        original_content: str,
        fuzzy_threshold: float = 0.80
    ) -> Optional[Any]:
        """
        Find a specific post by searching for matching author and content.
        
        Args:
            author_handle: LinkedIn handle of the post author
            original_content: Original post content to search for
            fuzzy_threshold: Similarity threshold for fuzzy matching (default 0.80)
            
        Returns:
            Selenium WebElement of the post container if found, None otherwise
        """
        logger.info(f"🔍 Searching for post by @{author_handle}...")
        logger.debug(f"   Looking for content: {original_content[:100]}...")
        
        try:
            # Navigate to author's recent activity page
            # Support company pages with company/ prefix
            if author_handle.startswith("company/"):
                company_handle = author_handle.replace("company/", "")
                profile_url = f"https://www.linkedin.com/company/{company_handle}/posts/"
                logger.info(f"🏢 Navigating to company page: {profile_url}")
            else:
                profile_url = f"https://www.linkedin.com/in/{author_handle}/recent-activity/all/"
                logger.info(f"📍 Navigating to {profile_url}")
            
            self.driver.get(profile_url)
            
            # Random delay to appear human
            random_medium_delay()
            
            # Scroll to load posts
            logger.info("📜 Scrolling to load posts...")
            for i in range(5):  # Scroll up to 5 times
                scroll_amount = random_scroll_amount()
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                human_scroll_delay()
            
            # Give page time to fully load
            random_delay(2.0, 4.0)
            
            # Get page HTML and parse with BeautifulSoup
            from bs4 import BeautifulSoup
            page_html = self.driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')
            
            # Find all post containers
            post_headers = soup.find_all('h2', class_='visually-hidden', 
                                        string=lambda s: s and 'Feed post number' in s)
            
            if not post_headers:
                # Fallback to impression containers
                post_containers = soup.find_all('div', class_=lambda c: c and 'fie-impression-container' in c)
                posts_to_check = post_containers
            else:
                posts_to_check = [h.parent for h in post_headers if h.parent]
            
            logger.info(f"🔍 Found {len(posts_to_check)} posts to check")
            
            # Search for matching content
            best_match = None
            best_score = 0.0
            
            for idx, post_element in enumerate(posts_to_check[:20]):  # Check first 20 posts
                try:
                    # Extract text content
                    content = ""
                    
                    # Try to find the main content area
                    content_divs = post_element.find_all('div', class_=lambda c: c and 'fie-impression-container' in c)
                    if content_divs:
                        for div in content_divs:
                            spans = div.find_all('span', class_=lambda c: c and 'break-words' in c)
                            for span in spans:
                                text = span.get_text(separator=' ', strip=True)
                                if text and len(text) > len(content):
                                    content = text
                    
                    if not content:
                        content = post_element.get_text(separator=' ', strip=True)
                    
                    # Skip if no content
                    if not content or len(content) < 10:
                        continue
                    
                    # Calculate fuzzy match score
                    score = fuzzy_match_score(original_content, content)
                    
                    logger.debug(f"   Post {idx+1} similarity: {score:.2%}")
                    
                    if score > best_score:
                        best_score = score
                        best_match = (post_element, content, idx)
                    
                    # If we found an excellent match, stop searching
                    if score >= 0.95:
                        logger.info(f"✅ Found excellent match (score: {score:.2%})")
                        break
                        
                except Exception as e:
                    logger.debug(f"⚠️  Error checking post {idx+1}: {e}")
                    continue
            
            # Check if best match meets threshold
            if best_match and best_score >= fuzzy_threshold:
                post_element, matched_content, post_idx = best_match
                logger.info(f"✅ Found matching post (score: {best_score:.2%})")
                logger.debug(f"   Matched content: {matched_content[:100]}...")
                
                # Now we need to find the actual Selenium element
                # We'll use the post index to locate it in the DOM
                try:
                    # Try to find by the "Feed post number X" header
                    xpath = f"//h2[contains(@class, 'visually-hidden') and contains(text(), 'Feed post number {post_idx + 1}')]/parent::*"
                    selenium_element = self.driver.find_element(By.XPATH, xpath)
                    return selenium_element
                except NoSuchElementException:
                    logger.warning("⚠️  Could not locate Selenium element for matched post")
                    return None
            else:
                logger.warning(f"⚠️  No matching post found (best score: {best_score:.2%}, threshold: {fuzzy_threshold:.2%})")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error searching for post: {e}")
            return None
    
    def _click_repost_button(self, post_element, variant_text: str) -> bool:
        """
        Click the repost button on a post and add commentary.
        
        Args:
            post_element: Selenium WebElement of the post container
            variant_text: AI-generated variant text to add as commentary
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("🔘 Attempting to click repost button...")
        
        try:
            # Find the repost button within the post element
            # LinkedIn uses various button classes, try multiple selectors
            repost_selectors = [
                ".//button[contains(@aria-label, 'Repost')]",
                ".//button[contains(@aria-label, 'repost')]",
                ".//button[contains(., 'Repost')]",
                ".//span[text()='Repost']/ancestor::button",
            ]
            
            repost_button = None
            for selector in repost_selectors:
                try:
                    repost_button = post_element.find_element(By.XPATH, selector)
                    if repost_button:
                        logger.debug(f"✅ Found repost button with selector: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not repost_button:
                logger.error("❌ Could not find repost button")
                return False
            
            # Scroll to button and click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", repost_button)
            random_short_delay()
            
            # Click with JavaScript to avoid interception issues
            self.driver.execute_script("arguments[0].click();", repost_button)
            logger.info("✅ Clicked repost button")
            
            # Wait for repost modal/menu to appear
            random_delay(1.0, 2.0)
            
            # Look for "Repost with your thoughts" or similar option
            try:
                # Try to find the textarea or "with thoughts" button
                thoughts_selectors = [
                    "//button[contains(., 'with your thoughts')]",
                    "//button[contains(., 'Start writing')]",
                    "//span[contains(text(), 'your thoughts')]/ancestor::button",
                ]
                
                thoughts_button = None
                for selector in thoughts_selectors:
                    try:
                        thoughts_button = self.driver.find_element(By.XPATH, selector)
                        if thoughts_button:
                            logger.debug(f"✅ Found 'with thoughts' button")
                            self.driver.execute_script("arguments[0].click();", thoughts_button)
                            random_medium_delay()
                            break
                    except NoSuchElementException:
                        continue
                
                # Find the text input area
                text_area_selectors = [
                    "//div[@role='textbox']",
                    "//textarea[contains(@placeholder, 'thoughts')]",
                    "//div[contains(@class, 'ql-editor')]",
                ]
                
                text_area = None
                for selector in text_area_selectors:
                    try:
                        text_area = self.driver.find_element(By.XPATH, selector)
                        if text_area:
                            logger.debug(f"✅ Found text input area")
                            break
                    except NoSuchElementException:
                        continue
                
                if not text_area:
                    logger.error("❌ Could not find text input area")
                    return False
                
                # Click on text area to focus
                text_area.click()
                random_short_delay()
                
                # Type the variant text with human-like timing
                logger.info(f"⌨️  Typing variant text ({len(variant_text)} chars)...")
                type_like_human(text_area, variant_text)
                logger.info("✅ Typed variant text")
                
                # Wait a moment before posting
                random_delay(2.0, 4.0)
                
                # Find and click the "Post" button
                post_button_selectors = [
                    "//button[contains(., 'Post')]",
                    "//button[@type='submit']",
                    "//span[text()='Post']/ancestor::button",
                ]
                
                post_button = None
                for selector in post_button_selectors:
                    try:
                        post_button = self.driver.find_element(By.XPATH, selector)
                        if post_button and post_button.is_enabled():
                            logger.debug(f"✅ Found Post button")
                            break
                    except NoSuchElementException:
                        continue
                
                if not post_button:
                    logger.error("❌ Could not find Post button")
                    return False
                
                # Click the Post button
                self.driver.execute_script("arguments[0].click();", post_button)
                logger.info("✅ Clicked Post button")
                
                # Wait for post to be submitted
                random_delay(3.0, 5.0)
                
                logger.info("🎉 Successfully reposted!")
                return True
                
            except Exception as e:
                logger.error(f"❌ Error in repost flow: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error clicking repost button: {e}")
            return False
    
    def _repost_with_variant(
        self,
        author_handle: str,
        original_content: str,
        variant_text: str,
        fuzzy_threshold: float = 0.80
    ) -> bool:
        """
        Find a post and repost it with AI-generated variant text.
        
        Args:
            author_handle: LinkedIn handle of the original post author
            original_content: Original post content to search for
            variant_text: AI-generated variant text to add as commentary
            fuzzy_threshold: Similarity threshold for fuzzy matching
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"🔄 Attempting to repost @{author_handle}'s post...")
        
        try:
            # Find the post
            post_element = self._find_post_by_content(
                author_handle=author_handle,
                original_content=original_content,
                fuzzy_threshold=fuzzy_threshold
            )
            
            if not post_element:
                logger.warning("⚠️  Post not found, cannot repost")
                return False
            
            # Click repost and add variant
            success = self._click_repost_button(post_element, variant_text)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error in repost flow: {e}")
            return False
    
    async def repost_with_variant(
        self,
        author_handle: str,
        original_content: str,
        variant_text: str,
        fuzzy_threshold: float = 0.80
    ) -> bool:
        """
        Repost a LinkedIn post with AI-generated variant (async wrapper).
        
        Args:
            author_handle: LinkedIn handle of the original post author
            original_content: Original post content to search for
            variant_text: AI-generated variant text to add as commentary
            fuzzy_threshold: Similarity threshold for fuzzy matching
            
        Returns:
            True if successful, False otherwise
        """
        log_operation_start(logger, "selenium_repost", handle=author_handle)
        
        try:
            # Start driver
            await self.start()
            
            # Run repost in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                self.executor,
                self._repost_with_variant,
                author_handle,
                original_content,
                variant_text,
                fuzzy_threshold
            )
            
            if success:
                log_operation_success(logger, "selenium_repost")
            else:
                log_operation_error(logger, "selenium_repost", Exception("Repost failed"))
            
            return success
            
        except Exception as e:
            log_operation_error(logger, "selenium_repost", e)
            return False
        finally:
            await self.stop()


def get_selenium_linkedin_service(headless: bool = True, email: str = None, password: str = None) -> LinkedInSeleniumAutomation:
    """Get a configured Selenium LinkedIn automation service instance."""
    return LinkedInSeleniumAutomation(headless=headless, email=email, password=password)
