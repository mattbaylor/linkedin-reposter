"""GitHub Copilot AI service for generating LinkedIn post variants."""
import logging
from typing import List, Optional
import httpx
from app.config import get_settings
from app.logging_config import log_operation_start, log_operation_success, log_operation_error, log_api_call

logger = logging.getLogger(__name__)


class GitHubCopilotAIService:
    """
    AI service using GitHub Copilot API for higher rate limits.
    
    Uses GitHub Copilot's chat completions API with token exchange.
    """
    
    def __init__(self, access_token: Optional[str] = None, refresh_token: Optional[str] = None):
        """
        Initialize the GitHub Copilot AI service.
        
        Args:
            access_token: GitHub Copilot access token (session token)
            refresh_token: GitHub Copilot refresh token (ghu_ token)
        """
        settings = get_settings()
        self.session_token = access_token or settings.github_copilot_access_token
        self.refresh_token = refresh_token or settings.github_copilot_refresh_token
        self.api_url = "https://api.githubcopilot.com/chat/completions"
        self.token_url = "https://api.github.com/copilot_internal/v2/token"
        self.model = "gpt-4o"
        self.bearer_token = None
        
        if not self.session_token and not self.refresh_token:
            raise ValueError("GitHub Copilot tokens not configured")
        
        logger.info("🤖 GitHub Copilot AI Service initialized")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   API: GitHub Copilot")
    
    async def _get_bearer_token(self) -> str:
        """
        Exchange the refresh token for a Copilot API bearer token.
        
        The refresh token (ghu_*) can be used to get a time-limited bearer token
        for the Copilot API.
        """
        if self.bearer_token:
            return self.bearer_token
        
        try:
            # Try to get a bearer token using the refresh token (ghu_* token)
            if self.refresh_token and self.refresh_token.startswith('ghu_'):
                logger.info("   Exchanging refresh token for Copilot API bearer token...")
                
                headers = {
                    "Authorization": f"token {self.refresh_token}",
                    "Accept": "application/json",
                    "User-Agent": "GitHubCopilotChat/0.11.1"
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self.token_url,
                        headers=headers,
                        timeout=30.0
                    )
                    
                    logger.info(f"   Token exchange: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'token' in data:
                            self.bearer_token = data['token']
                            logger.info(f"   ✅ Got Copilot API bearer token (expires: {data.get('expires_at', 'unknown')})")
                            return self.bearer_token
                    else:
                        logger.warning(f"   Token exchange failed: {response.text[:200]}")
            
            # Fallback: try using session_token as-is
            logger.info("   Using session token as-is...")
            return self.session_token
            
        except Exception as e:
            logger.warning(f"   Token exchange error: {e}, using session token")
            return self.session_token
    
    async def generate_variants(
        self,
        original_content: str,
        author_name: str,
        num_variants: int = 3,
        relationship: Optional[str] = None,
        custom_context: Optional[str] = None
    ) -> List[str]:
        """
        Generate alternative versions of a LinkedIn post using GitHub Copilot.
        
        Args:
            original_content: The original post content
            author_name: Name of the original post author
            num_variants: Number of variants to generate (default: 3)
            relationship: Type of relationship with the author (e.g., "mentor", "colleague")
            custom_context: Additional context about the author
        
        Returns:
            List of generated post variants
        
        Raises:
            Exception: If API call fails or response is invalid
        """
        log_operation_start(
            logger,
            "generate_variants_copilot",
            author=author_name,
            variants_count=num_variants,
            content_length=len(original_content)
        )
        
        try:
            prompt = self._create_prompt(original_content, author_name, num_variants, relationship, custom_context)
            
            # Get a valid bearer token (exchange refresh token if needed)
            bearer_token = await self._get_bearer_token()
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
                "Editor-Version": "vscode/1.85.0",
                "Editor-Plugin-Version": "copilot-chat/0.11.1",
                "User-Agent": "GitHubCopilotChat/0.11.1",
                "Openai-Organization": "github-copilot",
                "Openai-Intent": "conversation-panel",
                "VScode-SessionId": "session-001",
                "VScode-MachineId": "machine-001"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert LinkedIn content creator who specializes in creating engaging, professional posts."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.8,
                "max_tokens": 2000,
                "top_p": 0.9,
                "n": 1,
                "stream": False
            }
            
            async with httpx.AsyncClient() as client:
                log_api_call(logger, "POST", self.api_url, "GitHub Copilot API")
                
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=60.0
                )
                
                logger.info(f"🌐 API POST {self.api_url} → {response.status_code}")
                response.raise_for_status()
                
                result = response.json()
                
                # Extract the generated content
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("No choices in API response")
                
                content = result["choices"][0]["message"]["content"]
                
                # Parse the variants from the response
                variants = self._parse_variants(content, num_variants)
                
                if len(variants) != num_variants:
                    logger.warning(
                        f"⚠️  Expected {num_variants} variants, got {len(variants)}. "
                        "Using what we have."
                    )
                
                log_operation_success(
                    logger,
                    "generate_variants_copilot",
                    variants_count=len(variants),
                    model=self.model
                )
                
                return variants
                
        except Exception as e:
            log_operation_error(logger, "generate_variants_copilot", e)
            raise
    
    def _create_prompt(self, original_content: str, author_name: str, num_variants: int, relationship: Optional[str] = None, custom_context: Optional[str] = None) -> str:
        """
        Create the prompt for generating post variants.
        
        Uses the same prompt as the GitHub Models service for consistency.
        """
        # Build relationship context for the prompt
        relationship_context = ""
        if relationship or custom_context:
            relationship_context = "\n\nAUTHOR CONTEXT:"
            if relationship:
                relationship_context += f"\n- Your relationship: {relationship}"
            if custom_context:
                relationship_context += f"\n- Additional context: {custom_context}"
            relationship_context += "\n- Use this context to personalize your tone and add credibility when sharing their insights"
        
        return f"""I need you to create {num_variants} alternative versions of the following LinkedIn post.

ORIGINAL POST by {author_name}:
---
{original_content}
---
{relationship_context}

REQUIREMENTS:
1. Create {num_variants} distinct variants that maintain the core message
2. Each variant should have a different tone or angle:
   - Variant 1: Professional and formal
   - Variant 2: Enthusiastic and energetic
   - Variant 3: Conversational and approachable
3. Keep the same hashtags or suggest similar relevant ones
4. **IMPORTANT - SUMMARIZE**: Make the variants more concise than the original
   - Focus on the key insight or takeaway
   - Aim for 30-50% shorter than the original while keeping the main point
   - Remove unnecessary details or repetition
5. Preserve any emojis or use similar appropriate ones
6. Each variant should feel authentic and engaging
7. **IMPORTANT - THIRD PERSON**: Convert first-person perspective to third-person perspective
   - Reference the original poster by their FULL NAME: "{author_name}"
   - Example: "I believe..." → "{author_name} believes..."
   - Example: "In my experience..." → "In {author_name}'s experience..."
   - Example: "I've seen..." → "{author_name} has seen..."
   - Use their actual name (e.g., "Tim Cool", "Elena Dietrich"), NOT their handle (e.g., NOT "timcool" or "@timcool")
8. DO NOT include any meta-commentary, explanations, or labels like "Variant 1:", "Option 1:", etc.
9. Separate each variant with exactly "---VARIANT---" on its own line

OUTPUT FORMAT:
Return exactly {num_variants} variants separated by ---VARIANT--- markers, with no additional text, explanations, or labels.

Example output format:
This is the first concise variant text here referencing {author_name}.

#Hashtag1 #Hashtag2
---VARIANT---
This is the second summarized variant text here with {author_name}'s perspective.

#Hashtag1 #Hashtag2
---VARIANT---
This is the third condensed variant text here about what {author_name} thinks.

#Hashtag1 #Hashtag2

Now generate the {num_variants} variants:"""
    
    def _parse_variants(self, content: str, expected_count: int) -> List[str]:
        """
        Parse variants from the AI response.
        
        Uses the same parsing logic as the GitHub Models service.
        """
        # Split by the variant marker
        variants = content.split("---VARIANT---")
        
        # Clean up each variant
        cleaned_variants = []
        for variant in variants:
            variant = variant.strip()
            if variant:  # Only include non-empty variants
                # Remove any labels like "Variant 1:", "Option 1:", etc.
                lines = variant.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Skip lines that look like labels
                    if line.strip().lower().startswith(('variant', 'option', 'version')):
                        continue
                    cleaned_lines.append(line)
                
                cleaned_variant = '\n'.join(cleaned_lines).strip()
                if cleaned_variant:
                    cleaned_variants.append(cleaned_variant)
        
        return cleaned_variants[:expected_count]  # Ensure we don't return too many


def get_copilot_ai_service() -> Optional[GitHubCopilotAIService]:
    """
    Get a configured GitHub Copilot AI service instance.
    
    Returns None if Copilot tokens are not configured.
    """
    settings = get_settings()
    if settings.github_copilot_access_token:
        try:
            return GitHubCopilotAIService()
        except Exception as e:
            logger.warning(f"⚠️  Could not initialize Copilot AI service: {e}")
            return None
    return None
