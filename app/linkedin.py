"""LinkedIn automation service using Playwright with cookie-based authentication."""
import logging
import asyncio
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout
from playwright_stealth import stealth_async
from app.config import get_settings
from app.logging_config import (
    log_operation_start,
    log_operation_success,
    log_operation_error,
    log_workflow_step,
)

logger = logging.getLogger(__name__)

# Session expiration settings
SESSION_WARNING_DAYS = 25  # Warn when session is 25 days old (LinkedIn cookies typically last ~30 days)
SESSION_MAX_AGE_DAYS = 30  # Consider session expired after 30 days


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


class LinkedInAutomation:
    """
    Service for automating LinkedIn interactions using Playwright.
    
    Uses cookie-based authentication to avoid LinkedIn's anti-bot detection.
    
    Flow:
    1. First time: Run manual_setup() in non-headless mode to login and save cookies
    2. Subsequent runs: Automatically load saved session and skip login
    
    Handles:
    - Browser session management with persistent cookies
    - Scraping posts from monitored handles
    - Publishing posts to LinkedIn
    """
    
    def __init__(self, headless: bool = True):
        """
        Initialize the LinkedIn automation service.
        
        Args:
            headless: Run browser in headless mode (default: True)
        """
        import os
        
        self.settings = get_settings()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_logged_in = False
        
        # Check if DISPLAY is set (VNC mode) - if so, run non-headless
        if os.environ.get('DISPLAY'):
            logger.info("🖥️  DISPLAY detected - running in headed mode for VNC")
            self.headless = False
        else:
            self.headless = headless
            
        self.session_needs_refresh = False
        self.session_expired = False
        
        # Session storage
        self.session_dir = Path("/app/data/linkedin_session")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / "state.json"
        self.cookies_file = self.session_dir / "cookies.json"
        self.session_metadata_file = self.session_dir / "metadata.json"
        
        logger.info("🌐 LinkedIn Automation initialized")
        logger.info(f"   Headless mode: {self.headless}")
        logger.info(f"   Session dir: {self.session_dir}")
        logger.info(f"   Session file exists: {self.session_file.exists()}")
    
    def get_session_age(self) -> Optional[int]:
        """
        Get the age of the current session in days.
        
        Returns:
            Number of days since session was created, or None if no session
        """
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
        """
        Check the health of the current session.
        
        Returns:
            Dictionary with session health information
        """
        age_days = self.get_session_age()
        
        health = {
            'has_session': self.session_file.exists(),
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
    
    async def send_session_alert(self, reason: str) -> bool:
        """
        Send an email alert about session status.
        
        Args:
            reason: Reason for the alert (e.g., 'expired', 'warning')
        
        Returns:
            True if email sent successfully
        """
        try:
            from app.email import get_email_service
            
            email_service = get_email_service()
            age_days = self.get_session_age() or 0
            
            if reason == 'expired':
                subject = "🚨 LinkedIn Session Expired - Action Required"
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #d32f2f;">LinkedIn Session Expired</h2>
                    
                    <p>Your LinkedIn automation session has expired (age: {age_days} days).</p>
                    
                    <p><strong>Action Required:</strong> You need to refresh your LinkedIn session to continue automated posting.</p>
                    
                    <h3>How to Refresh:</h3>
                    <ol>
                        <li>Visit: <a href="{self.settings.app_base_url}/linkedin/setup">{self.settings.app_base_url}/linkedin/setup</a></li>
                        <li>Or use the API endpoint: <code>POST /linkedin/manual-setup</code></li>
                        <li>Login to LinkedIn when prompted</li>
                        <li>Complete any verification challenges</li>
                    </ol>
                    
                    <p style="color: #666; font-size: 12px;">
                        This is an automated alert from your LinkedIn Reposter service.
                    </p>
                </body>
                </html>
                """
            else:  # warning
                subject = "⚠️ LinkedIn Session Expiring Soon"
                days_remaining = SESSION_MAX_AGE_DAYS - age_days
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #f57c00;">LinkedIn Session Expiring Soon</h2>
                    
                    <p>Your LinkedIn automation session is {age_days} days old and will expire in approximately {days_remaining} days.</p>
                    
                    <p><strong>Recommended Action:</strong> Refresh your session soon to avoid interruptions.</p>
                    
                    <h3>How to Refresh:</h3>
                    <ol>
                        <li>Visit: <a href="{self.settings.app_base_url}/linkedin/setup">{self.settings.app_base_url}/linkedin/setup</a></li>
                        <li>Or use the API endpoint: <code>POST /linkedin/manual-setup</code></li>
                        <li>Login to LinkedIn when prompted</li>
                    </ol>
                    
                    <p style="color: #666; font-size: 12px;">
                        This is an automated alert from your LinkedIn Reposter service.
                    </p>
                </body>
                </html>
                """
            
            # Plain text version
            text_content = f"""
            LinkedIn Session {reason.upper()}
            
            Your session is {age_days} days old.
            
            Please refresh at: {self.settings.app_base_url}/linkedin/setup
            """
            
            result = await email_service.send_email(
                to_email=self.settings.approval_email,
                subject=subject,
                html_body=html_content,
                text_body=text_content
            )
            
            logger.info(f"✅ Session alert email sent: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send session alert: {e}")
            return False
    
    async def start(self, check_session: bool = True):
        """
        Start the browser and initialize the session.
        
        Args:
            check_session: If True, verify the session is valid by checking login status
        """
        log_operation_start(logger, "start_browser", headless=self.headless)
        
        try:
            self.playwright = await async_playwright().start()
            
            # Check if we have a saved session
            has_session = self.session_file.exists()
            
            # Only check session health if requested
            if check_session:
                # Check session health first
                health = self.check_session_health()
                logger.info(f"📊 Session health: {health['status']}")
                
                if health['age_days'] is not None:
                    logger.info(f"   Session age: {health['age_days']} days")
                
                # Handle expired session
                if health['expired'] and self.headless:
                    logger.error("❌ Session expired and running in headless mode!")
                    
                    # Send alert email
                    await self.send_session_alert('expired')
                    
                    raise Exception(
                        f"LinkedIn session expired (age: {health['age_days']} days). "
                        "Please check your email for refresh instructions."
                    )
                
                # Handle warning state
                if health['needs_refresh'] and not health['expired']:
                    logger.warning(f"⚠️  Session is {health['age_days']} days old and should be refreshed soon")
                    # Send warning email (but don't block operation)
                    await self.send_session_alert('warning')
                
                if not has_session and self.headless:
                    logger.warning("⚠️  No saved session found and running in headless mode!")
                    
                    # Send alert
                    await self.send_session_alert('expired')
                    
                    raise Exception(
                        "No LinkedIn session found. Check your email for setup instructions."
                    )
            
            # Launch browser with additional evasion flags
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                ],
                chromium_sandbox=False,
            )
            
            # Create browser context with saved session if available
            context_options = {
                'user_agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                'viewport': {'width': 1920, 'height': 1080},
                'locale': 'en-US',
                'timezone_id': 'America/Denver',
            }
            
            if has_session:
                logger.info(f"📂 Loading saved session from {self.session_file}")
                context_options['storage_state'] = str(self.session_file)
            
            self.context = await self.browser.new_context(**context_options)
            
            # Create a new page
            self.page = await self.context.new_page()
            
            # Apply stealth mode to hide automation signals
            await stealth_async(self.page)
            logger.info("🥷 Stealth mode applied to page")
            
            # Additional JavaScript evasion techniques
            await self.page.add_init_script("""
                // Override navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override chrome property
                window.chrome = {
                    runtime: {}
                };
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Override plugins length
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
            logger.info("🎭 Additional evasion scripts applied")
            
            # Set extra HTTP headers to appear more human
            await self.page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            # Verify session is valid if requested
            if check_session and has_session:
                # For cookie-based sessions, skip the validation check
                # LinkedIn blocks the /feed navigation with redirect loop
                # We'll trust the cookie and detect issues during actual scraping
                logger.info("✅ Session loaded from cookie - skipping validation to avoid detection")
                self.is_logged_in = True
            
            log_operation_success(logger, "start_browser", has_session=has_session)
            
        except Exception as e:
            log_operation_error(logger, "start_browser", e)
            raise
    
    async def stop(self):
        """Stop the browser and cleanup."""
        log_operation_start(logger, "stop_browser")
        
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            log_operation_success(logger, "stop_browser")
            
        except Exception as e:
            log_operation_error(logger, "stop_browser", e)
    
    async def manual_setup(self, wait_time: int = 60) -> bool:
        """
        Run manual LinkedIn login setup in non-headless mode.
        
        This opens a browser window where you can:
        1. Login to LinkedIn manually
        2. Complete any verification challenges
        3. Save the session for future automated use
        
        Args:
            wait_time: How long to wait for manual login (seconds)
        
        Returns:
            True if session was saved successfully
        """
        log_operation_start(logger, "manual_setup", wait_time=wait_time)
        
        # Force non-headless mode for manual setup
        original_headless = self.headless
        self.headless = False
        
        try:
            # Start browser in non-headless mode
            await self.start(check_session=False)
            
            logger.info("🖥️  Opening LinkedIn homepage...")
            logger.info(f"   You have {wait_time} seconds to complete login")
            
            # Navigate to LinkedIn homepage (not login page to avoid bot detection)
            await self.page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=60000)
            
            logger.info("✅ Page loaded - you can now manually navigate to login")
            
            # Wait for user to complete login
            logger.info("⏳ Waiting for manual login...")
            logger.info("   1. Click 'Sign in' on the homepage")
            logger.info("   2. Login with your credentials")
            logger.info("   3. Complete any verification challenges")
            logger.info("   4. Wait for the feed page to load")
            
            # Wait for feed or profile page (indicates successful login)
            try:
                await self.page.wait_for_url(
                    "**/linkedin.com/feed/**",
                    timeout=wait_time * 1000
                )
                logger.info("✅ Detected successful login!")
            except PlaywrightTimeout:
                current_url = self.page.url
                if "linkedin.com/feed" in current_url or "linkedin.com/in/" in current_url:
                    logger.info("✅ Login appears successful (alternate URL)")
                else:
                    logger.warning(f"⚠️  Timeout waiting for login. Current URL: {current_url}")
                    logger.warning("   Attempting to save session anyway...")
            
            # Save the session
            await self._save_session()
            
            # Verify session works
            is_valid = await self._check_logged_in()
            
            if is_valid:
                logger.info("✅ Session saved and verified successfully!")
                log_operation_success(logger, "manual_setup", session_valid=True)
                self.is_logged_in = True
                return True
            else:
                logger.error("❌ Session saved but verification failed")
                log_operation_success(logger, "manual_setup", session_valid=False)
                return False
            
        except Exception as e:
            log_operation_error(logger, "manual_setup", e)
            raise
        finally:
            # Restore original headless setting
            self.headless = original_headless
    
    async def login_with_cookies(self, li_at_cookie: str) -> bool:
        """
        Login using the li_at cookie directly.
        
        This is the fastest way to authenticate if you already have the cookie.
        
        Args:
            li_at_cookie: The li_at cookie value from your browser
        
        Returns:
            True if login successful
        """
        log_operation_start(logger, "login_with_cookies")
        
        try:
            # Start browser without existing session
            if self.session_file.exists():
                self.session_file.unlink()
            
            await self.start(check_session=False)
            
            # Set the cookie
            await self.context.add_cookies([{
                'name': 'li_at',
                'value': li_at_cookie,
                'domain': '.linkedin.com',
                'path': '/',
                'httpOnly': True,
                'secure': True,
            }])
            
            logger.info("🍪 Cookie added to browser context")
            
            # Save the session - trust that the user's cookie is valid
            # We'll verify it works during actual scraping, not here
            await self._save_session()
            logger.info("✅ Cookie saved to session file")
            
            # Mark as logged in without validation to avoid redirect loop
            # The cookie from user's browser should be valid
            self.is_logged_in = True
            
            log_operation_success(logger, "login_with_cookies")
            
            return {
                "success": True,
                "message": "Cookie saved successfully. Session will be validated during first use.",
                "session_file": str(self.session_file)
            }
            
        except Exception as e:
            log_operation_error(logger, "login_with_cookies", e)
            raise
    
    async def scrape_user_posts(
        self,
        handle: str,
        max_posts: int = 10,
        days_back: int = 7,
        author_name: Optional[str] = None
    ) -> List[LinkedInPost]:
        """
        Scrape recent posts from a LinkedIn user.
        
        Args:
            handle: LinkedIn handle (e.g., 'timcool' or full URL)
            max_posts: Maximum number of posts to scrape
            days_back: Only scrape posts from the last N days
        
        Returns:
            List of scraped posts
        """
        log_operation_start(
            logger,
            "scrape_user_posts",
            handle=handle,
            max_posts=max_posts,
            days_back=days_back
        )
        
        try:
            if not self.is_logged_in:
                raise Exception("Not logged in. Please authenticate first.")
            
            # Construct profile URL
            if handle.startswith("http"):
                profile_url = handle
            else:
                profile_url = f"https://www.linkedin.com/in/{handle}/recent-activity/all/"
            
            log_workflow_step(logger, f"Navigating to {handle}'s profile")
            await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for posts to load
            await asyncio.sleep(3)
            
            # Scroll to load more posts
            log_workflow_step(logger, "Scrolling to load posts")
            for _ in range(3):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
            
            # Extract posts
            posts = []
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            log_workflow_step(logger, "Extracting post data")
            
            # Try to find post elements - LinkedIn's DOM structure varies
            post_selectors = [
                'div[data-id^="urn:li:activity"]',
                'div.feed-shared-update-v2',
                'article',
            ]
            
            post_elements = None
            for selector in post_selectors:
                post_elements = await self.page.query_selector_all(selector)
                if post_elements:
                    logger.info(f"✅ Found {len(post_elements)} post elements with selector: {selector}")
                    break
            
            if not post_elements:
                logger.warning("⚠️  No post elements found")
                return []
            
            for element in post_elements[:max_posts]:
                try:
                    # Extract post data
                    post_data = await self._extract_post_data(element, handle, author_name)
                    
                    if post_data and post_data.post_date >= cutoff_date:
                        posts.append(post_data)
                        logger.info(f"✅ Scraped post: {post_data.content[:50]}...")
                    
                except Exception as e:
                    logger.warning(f"⚠️  Failed to extract post data: {e}")
                    continue
            
            log_operation_success(
                logger,
                "scrape_user_posts",
                handle=handle,
                posts_count=len(posts)
            )
            
            return posts
            
        except Exception as e:
            log_operation_error(logger, "scrape_user_posts", e)
            raise
    
    async def publish_post(self, content: str) -> bool:
        """
        Publish a post to LinkedIn.
        
        Args:
            content: The post content to publish
        
        Returns:
            True if published successfully
        """
        log_operation_start(logger, "publish_post", content_length=len(content))
        
        try:
            if not self.is_logged_in:
                raise Exception("Not logged in. Please authenticate first.")
            
            log_workflow_step(logger, "Navigating to LinkedIn feed")
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="networkidle")
            
            # Click "Start a post" button
            log_workflow_step(logger, "Opening post composer")
            
            start_post_selectors = [
                'button:has-text("Start a post")',
                'button[aria-label="Start a post"]',
                '.share-box-feed-entry__trigger',
            ]
            
            clicked = False
            for selector in start_post_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    clicked = True
                    break
                except:
                    continue
            
            if not clicked:
                raise Exception("Could not find 'Start a post' button")
            
            await asyncio.sleep(2)
            
            log_workflow_step(logger, "Entering post content")
            
            # Find and fill the post editor
            editor_selectors = [
                'div[role="textbox"][aria-label*="post"]',
                'div.ql-editor',
                'div[contenteditable="true"]',
            ]
            
            filled = False
            for selector in editor_selectors:
                try:
                    await self.page.fill(selector, content, timeout=5000)
                    filled = True
                    break
                except:
                    continue
            
            if not filled:
                raise Exception("Could not find post editor")
            
            await asyncio.sleep(2)
            
            log_workflow_step(logger, "Publishing post")
            
            # Click "Post" button
            post_button_selectors = [
                'button:has-text("Post")',
                'button[aria-label="Post"]',
                '.share-actions__primary-action',
            ]
            
            posted = False
            for selector in post_button_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    posted = True
                    break
                except:
                    continue
            
            if not posted:
                raise Exception("Could not find 'Post' button")
            
            await asyncio.sleep(5)
            
            log_operation_success(logger, "publish_post")
            
            return True
            
        except Exception as e:
            log_operation_error(logger, "publish_post", e)
            raise
    
    async def _check_logged_in(self) -> bool:
        """Check if currently logged in to LinkedIn."""
        try:
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="networkidle", timeout=10000)
            current_url = self.page.url
            
            # If we're redirected to login page, we're not logged in
            if "login" in current_url or "authwall" in current_url:
                return False
            
            # Check for feed elements that only appear when logged in
            try:
                await self.page.wait_for_selector('nav[aria-label="Primary Navigation"]', timeout=5000)
                return True
            except:
                return False
                
        except Exception as e:
            logger.warning(f"⚠️  Error checking login status: {e}")
            return False
    
    async def _save_session(self):
        """Save the current browser session state and cookies."""
        try:
            # Save full storage state (cookies + local storage)
            await self.context.storage_state(path=str(self.session_file))
            logger.info(f"✅ Session saved to {self.session_file}")
            
            # Also save cookies separately for easy inspection
            cookies = await self.context.cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"✅ Cookies saved to {self.cookies_file}")
            
            # Save metadata with creation timestamp
            metadata = {
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            with open(self.session_metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"✅ Session metadata saved to {self.session_metadata_file}")
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to save session: {e}")
    
    async def _extract_post_data(self, element, handle: str, author_name: Optional[str] = None) -> Optional[LinkedInPost]:
        """
        Extract post data from a post element.
        
        Args:
            element: The post element
            handle: The user handle
        
        Returns:
            LinkedInPost object or None
        """
        try:
            # Extract post URL
            post_url = await element.get_attribute("data-id")
            if not post_url:
                link = await element.query_selector('a[href*="/posts/"]')
                if link:
                    post_url = await link.get_attribute("href")
            
            # Extract author name (use provided name or scrape from page)
            if not author_name:
                author_elem = await element.query_selector('.update-components-actor__name, .feed-shared-actor__name')
                author_name = await author_elem.inner_text() if author_elem else "Unknown"
            
            # Extract post content
            content_elem = await element.query_selector('.feed-shared-update-v2__description, .update-components-text')
            content = await content_elem.inner_text() if content_elem else ""
            
            # Extract timestamp
            time_elem = await element.query_selector('time, .update-components-actor__sub-description')
            time_text = await time_elem.inner_text() if time_elem else ""
            
            # Parse relative time
            post_date = self._parse_relative_time(time_text)
            
            if not content:
                return None
            
            return LinkedInPost(
                url=post_url or f"https://www.linkedin.com/in/{handle}/",
                author_handle=handle,
                author_name=author_name.strip(),
                content=content.strip(),
                post_date=post_date,
            )
            
        except Exception as e:
            logger.warning(f"⚠️  Error extracting post data: {e}")
            return None
    
    def _parse_relative_time(self, time_text: str) -> datetime:
        """Parse relative time text to datetime."""
        now = datetime.utcnow()
        time_text = time_text.lower().strip()
        
        try:
            if 'h' in time_text or 'hour' in time_text:
                hours = int(''.join(filter(str.isdigit, time_text)))
                return now - timedelta(hours=hours)
            elif 'd' in time_text or 'day' in time_text:
                days = int(''.join(filter(str.isdigit, time_text)))
                return now - timedelta(days=days)
            elif 'w' in time_text or 'week' in time_text:
                weeks = int(''.join(filter(str.isdigit, time_text)))
                return now - timedelta(weeks=weeks)
            elif 'm' in time_text or 'mo' in time_text:
                months = int(''.join(filter(str.isdigit, time_text)))
                return now - timedelta(days=months * 30)
        except:
            pass
        
        return now


def get_linkedin_service(headless: bool = True) -> LinkedInAutomation:
    """Get a configured LinkedIn automation service instance."""
    return LinkedInAutomation(headless=headless)
