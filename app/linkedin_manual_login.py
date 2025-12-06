"""Manual LinkedIn login via VNC for session capture."""
import logging
import time
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)


def manual_login_session(wait_time: int = 300, email: str = None, password: str = None):
    """
    Open browser via VNC and wait for manual login.
    
    Args:
        wait_time: How long to wait for manual login (seconds, default 5 minutes)
        email: LinkedIn email for auto-fill
        password: LinkedIn password for auto-fill
    """
    print(f"🌐 Starting browser for manual login...")
    print(f"⏱️  You have {wait_time} seconds to complete login")
    if email and password:
        print(f"🔑 Credentials provided - will auto-fill")
    
    # Session storage
    session_dir = Path("/app/data/linkedin_session")
    session_dir.mkdir(parents=True, exist_ok=True)
    cookies_file = session_dir / "selenium_cookies.json"
    metadata_file = session_dir / "metadata.json"
    
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.binary_location = '/usr/bin/chromium'
    
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)
    
    # Execute CDP commands to hide automation
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        '''
    })
    
    try:
        print("🔗 Navigating to LinkedIn login page...")
        driver.get("https://www.linkedin.com/login")
        time.sleep(3)  # Wait for page load
        
        # AUTO-FILL credentials
        print("🔑 Auto-filling credentials...")
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            if email and password:
                # Wait for email field and fill it
                email_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                email_field.clear()
                
                # Type email character by character to simulate human typing
                for char in email:
                    email_field.send_keys(char)
                    time.sleep(0.05)  # Small delay between keystrokes
                
                print(f"✅ Email filled: {email}")
                
                # Fill password field
                password_field = driver.find_element(By.ID, "password")
                password_field.clear()
                
                # Type password character by character
                for char in password:
                    password_field.send_keys(char)
                    time.sleep(0.05)
                    
                print("✅ Password filled")
                
                # Small delay before clicking
                time.sleep(1)
                
                # Click sign in button
                sign_in_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                sign_in_button.click()
                print("✅ Sign in button clicked")
                
                # Wait a bit for login to process
                time.sleep(5)
                
                # Check if verification is needed
                current_url = driver.current_url
                if "checkpoint" in current_url or "challenge" in current_url:
                    print("\n" + "="*60)
                    print("⚠️  VERIFICATION CHALLENGE DETECTED")
                    print("="*60)
                    print("   Please complete the verification in VNC")
                    print(f"   Waiting {wait_time - 16} more seconds...")
                    print("="*60 + "\n")
                    time.sleep(wait_time - 16)
                elif "feed" in current_url:
                    print("✅ Auto-login successful! Waiting for page to fully load...")
                    time.sleep(10)  # Let the feed load
                    print("✅ Feed loaded, session should be valid")
                else:
                    print(f"⚠️  Unexpected URL after login: {current_url}")
                    print(f"   Waiting {wait_time - 16} seconds for manual intervention...")
                    time.sleep(wait_time - 16)
            else:
                print("⚠️  No credentials found, waiting for manual login...")
                print("\n" + "="*60)
                print("👤 MANUAL LOGIN REQUIRED")
                print("="*60)
                print(f"⏱️  Waiting {wait_time} seconds for you to:")
                print("   1. Login with your LinkedIn credentials")
                print("   2. Complete any verification challenges")
                print("   3. Wait for the feed page to load")
                print("="*60 + "\n")
                time.sleep(wait_time)
                
        except Exception as e:
            print(f"⚠️  Auto-fill failed: {e}")
            print("   Falling back to manual login...")
            time.sleep(max(0, wait_time - 3))
        
        # Save all cookies
        print("💾 Saving session cookies...")
        cookies = driver.get_cookies()
        with open(cookies_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"✅ Cookies saved to {cookies_file}")
        
        # Save metadata
        from datetime import datetime
        metadata = {
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'login_method': 'manual_vnc'
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"✅ Metadata saved to {metadata_file}")
        
        # Check if logged in
        current_url = driver.current_url
        if "feed" in current_url or "in/" in current_url:
            print("✅ Login appears successful!")
            print(f"   Current URL: {current_url}")
        else:
            print(f"⚠️  Warning: Not on feed page. Current URL: {current_url}")
        
        print("\n✅ Session saved! You can now use the scraping endpoints.")
        
    finally:
        print("\n🛑 Closing browser...")
        driver.quit()


if __name__ == "__main__":
    manual_login_session(wait_time=300)  # 5 minutes
