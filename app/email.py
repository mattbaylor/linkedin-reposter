"""Email service for sending approval requests via Postal."""
import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

from app.config import get_settings
from app.models import LinkedInPost, PostVariant, ApprovalRequest
from app.logging_config import log_api_call, log_operation_error, log_operation_start, log_operation_success

logger = logging.getLogger(__name__)


def generate_approval_token() -> str:
    """
    Generate a cryptographically secure random token for approval links.
    
    Returns:
        64-character hex string
    """
    return secrets.token_hex(32)


class PostalEmailService:
    """Service for sending emails via Postal API."""
    
    def __init__(self):
        """Initialize Postal email service with configuration."""
        settings = get_settings()
        self.api_key = settings.postal_api_key
        self.server_url = settings.postal_server_url
        self.from_email = settings.linkedin_email  # Use LinkedIn email as sender
        self.approval_email = settings.approval_email
        self.app_base_url = settings.app_base_url
        
        # Postal API endpoint
        # Note: Postal server URL should be like https://dlvr.rehosted.us
        # The API endpoint is /api/v1/send/message
        if not self.server_url.endswith('/'):
            self.server_url += '/'
        self.api_endpoint = f"{self.server_url}api/v1/send/message"
        
        logger.info(f"📧 Postal Email Service initialized")
        logger.info(f"   Server: {self.server_url}")
        logger.info(f"   From: {self.from_email}")
        logger.info(f"   To: {self.approval_email}")
    
    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        plain_body: Optional[str] = None
    ) -> dict:
        """
        Send an email via Postal API.
        
        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML email body
            plain_body: Plain text email body (optional)
        
        Returns:
            dict: Postal API response
        
        Raises:
            httpx.HTTPError: If email sending fails
        """
        log_operation_start(logger, "send_email", to=to, subject=subject)
        
        headers = {
            "X-Server-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "to": [to],
            "from": self.from_email,
            "subject": subject,
            "html_body": html_body,
        }
        
        if plain_body:
            payload["plain_body"] = plain_body
        
        logger.debug(f"📤 Postal API endpoint: {self.api_endpoint}")
        logger.debug(f"📤 Email payload: to={to}, from={self.from_email}, subject_length={len(subject)}, html_length={len(html_body)}")
        
        async with httpx.AsyncClient() as client:
            try:
                log_api_call(logger, "POST", self.api_endpoint, url_display="Postal API")
                
                response = await client.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                
                log_api_call(logger, "POST", self.api_endpoint, status_code=response.status_code)
                
                response.raise_for_status()
                
                result = response.json()
                message_id = result.get('data', {}).get('message_id', 'unknown')
                
                log_operation_success(logger, "send_email", message_id=message_id, to=to)
                logger.info(f"✅ Email sent successfully. Message ID: {message_id}")
                
                return result
                
            except httpx.HTTPError as e:
                log_operation_error(logger, "send_email", e, to=to, subject=subject)
                
                if hasattr(e, 'response') and e.response:
                    logger.error(f"   Response status: {e.response.status_code}")
                    logger.error(f"   Response body: {e.response.text[:500]}")  # First 500 chars
                
                raise
    
    def _build_approval_email_html(
        self,
        post: LinkedInPost,
        variants: List[PostVariant],
        approval_token: str
    ) -> str:
        """
        Build HTML email template for approval request.
        
        Args:
            post: Original LinkedIn post
            variants: List of 3 AI-generated variants
            approval_token: Secure token for approval links
        
        Returns:
            str: HTML email body
        """
        # Build approval URLs for each variant
        variant_urls = []
        for variant in variants:
            url = f"{self.app_base_url}/webhook/approve/{approval_token}?variant_id={variant.id}"
            variant_urls.append((variant, url))
        
        reject_url = f"{self.app_base_url}/webhook/reject/{approval_token}"
        
        # Format original post date
        post_date = post.original_post_date.strftime("%B %d, %Y") if post.original_post_date else "Unknown date"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Approve LinkedIn Post</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            border-bottom: 3px solid #0073b1;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #0073b1;
            font-size: 24px;
        }}
        .original-post {{
            background-color: #f8f9fa;
            border-left: 4px solid #0073b1;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .original-post .meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .original-post .content {{
            white-space: pre-wrap;
            font-size: 15px;
        }}
        .variants {{
            margin: 30px 0;
        }}
        .variant {{
            background-color: #fff;
            border: 2px solid #e1e8ed;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }}
        .variant:hover {{
            border-color: #0073b1;
        }}
        .variant-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .variant-number {{
            font-weight: bold;
            color: #0073b1;
            font-size: 18px;
        }}
        .variant-content {{
            white-space: pre-wrap;
            font-size: 15px;
            margin-bottom: 15px;
            line-height: 1.5;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            text-align: center;
            transition: background-color 0.2s;
        }}
        .btn-approve {{
            background-color: #0073b1;
            color: white;
        }}
        .btn-approve:hover {{
            background-color: #005885;
        }}
        .btn-reject {{
            background-color: #dc3545;
            color: white;
        }}
        .btn-reject:hover {{
            background-color: #c82333;
        }}
        .actions {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e1e8ed;
            text-align: center;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e1e8ed;
            color: #666;
            font-size: 13px;
            text-align: center;
        }}
        .ai-badge {{
            display: inline-block;
            background-color: #e1e8ed;
            color: #666;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📝 LinkedIn Post Approval Required</h1>
        </div>
        
        <p>A new LinkedIn post from <strong>{post.author_name}</strong> (@{post.author_handle}) has been processed and is ready for your review.</p>
        
        <div class="original-post">
            <div class="meta">
                <strong>Original Post</strong><br>
                Posted by {post.author_name} on {post_date}<br>
                <a href="{post.original_post_url}" target="_blank">View on LinkedIn</a>
            </div>
            <div class="content">{post.original_content}</div>
        </div>
        
        <h2>Choose a variant to post:</h2>
        <p>Our AI has generated 3 different versions of this post. Select the one you'd like to publish to your LinkedIn profile:</p>
        
        <div class="variants">
"""
        
        # Add each variant
        for i, (variant, approve_url) in enumerate(variant_urls, 1):
            html += f"""
            <div class="variant">
                <div class="variant-header">
                    <span class="variant-number">Option {i}</span>
                    <span class="ai-badge">Generated with {variant.ai_model}</span>
                </div>
                <div class="variant-content">{variant.variant_content}</div>
                <a href="{approve_url}" class="btn btn-approve">✓ Approve Option {i}</a>
            </div>
"""
        
        html += f"""
        </div>
        
        <div class="actions">
            <p><strong>Not interested in this post?</strong></p>
            <a href="{reject_url}" class="btn btn-reject">✗ Reject All Variants</a>
        </div>
        
        <div class="footer">
            <p>This approval link will expire in 7 days.</p>
            <p>You're receiving this email because you configured LinkedIn Reposter to monitor @{post.author_handle}.</p>
            <p style="margin-top: 20px; color: #999; font-size: 11px;">
                LinkedIn Reposter • Automated Post Monitoring & Rephrasing Service
            </p>
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def _build_approval_email_plain(
        self,
        post: LinkedInPost,
        variants: List[PostVariant],
        approval_token: str
    ) -> str:
        """
        Build plain text email template for approval request.
        
        Args:
            post: Original LinkedIn post
            variants: List of 3 AI-generated variants
            approval_token: Secure token for approval links
        
        Returns:
            str: Plain text email body
        """
        reject_url = f"{self.app_base_url}/webhook/reject/{approval_token}"
        
        plain = f"""LinkedIn Post Approval Required

A new LinkedIn post from {post.author_name} (@{post.author_handle}) has been processed and is ready for your review.

ORIGINAL POST:
{post.original_content}

View original: {post.original_post_url}

---

CHOOSE A VARIANT TO POST:

"""
        
        for i, variant in enumerate(variants, 1):
            approve_url = f"{self.app_base_url}/webhook/approve/{approval_token}?variant_id={variant.id}"
            plain += f"""
OPTION {i} (Generated with {variant.ai_model}):
{variant.variant_content}

Approve Option {i}: {approve_url}

---
"""
        
        plain += f"""
NOT INTERESTED?
Reject all variants: {reject_url}

---

This approval link will expire in 7 days.
You're receiving this email because you configured LinkedIn Reposter to monitor @{post.author_handle}.
"""
        
        return plain
    
    async def send_approval_email(
        self,
        post: LinkedInPost,
        variants: List[PostVariant],
        approval_token: str
    ) -> dict:
        """
        Send approval request email for a LinkedIn post.
        
        Args:
            post: Original LinkedIn post
            variants: List of 3 AI-generated variants
            approval_token: Secure token for approval links
        
        Returns:
            dict: Postal API response with message_id
        
        Raises:
            ValueError: If variants list is invalid
            httpx.HTTPError: If email sending fails
        """
        log_operation_start(
            logger, 
            "send_approval_email",
            post_id=post.id,
            author=post.author_handle,
            variants_count=len(variants)
        )
        
        if not variants or len(variants) != 3:
            error_msg = f"Expected 3 variants, got {len(variants)}"
            logger.error(f"❌ Invalid variants count for post {post.id}: {error_msg}")
            raise ValueError(error_msg)
        
        # Sort variants by variant_number to ensure consistent ordering
        variants = sorted(variants, key=lambda v: v.variant_number)
        
        logger.debug(f"📧 Preparing approval email for post {post.id}")
        logger.debug(f"   Author: {post.author_name} (@{post.author_handle})")
        logger.debug(f"   Original URL: {post.original_post_url}")
        logger.debug(f"   Variants: {[v.id for v in variants]}")
        logger.debug(f"   Token: {approval_token[:16]}...")
        
        subject = f"📝 Approve LinkedIn Post from {post.author_name}"
        
        html_body = self._build_approval_email_html(post, variants, approval_token)
        plain_body = self._build_approval_email_plain(post, variants, approval_token)
        
        logger.debug(f"📧 Email template generated: html_length={len(html_body)}, plain_length={len(plain_body)}")
        
        try:
            result = await self.send_email(
                to=self.approval_email,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body
            )
            
            log_operation_success(
                logger,
                "send_approval_email",
                post_id=post.id,
                message_id=result.get('data', {}).get('message_id', 'unknown')
            )
            
            return result
            
        except Exception as e:
            log_operation_error(logger, "send_approval_email", e, post_id=post.id)
            raise


# Global email service instance
_email_service: Optional[PostalEmailService] = None


def get_email_service() -> PostalEmailService:
    """Get the global email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = PostalEmailService()
    return _email_service
