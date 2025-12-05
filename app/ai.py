"""AI service for generating LinkedIn post variants using GitHub Models."""
import logging
from typing import List, Optional
import httpx
from app.config import get_settings
from app.logging_config import log_operation_start, log_operation_success, log_operation_error, log_api_call

logger = logging.getLogger(__name__)


class AIService:
    """
    Service for generating LinkedIn post variants using GitHub Models API.
    
    Uses the Azure OpenAI-compatible GitHub Models API to generate
    alternative versions of LinkedIn posts while maintaining the
    original message and tone.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the AI service.
        
        Args:
            api_key: GitHub token for API access
            model: Model name to use (default: gpt-4o)
        """
        settings = get_settings()
        self.api_key = api_key or settings.github_token
        self.model = model or settings.ai_model
        self.api_url = "https://models.inference.ai.azure.com/chat/completions"
        
        logger.info("🤖 AI Service initialized")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   API: GitHub Models (Azure OpenAI compatible)")
    
    async def generate_variants(
        self,
        original_content: str,
        author_name: str,
        num_variants: int = 3
    ) -> List[str]:
        """
        Generate alternative versions of a LinkedIn post.
        
        Args:
            original_content: The original post content
            author_name: Name of the original post author
            num_variants: Number of variants to generate (default: 3)
        
        Returns:
            List of generated post variants
        
        Raises:
            Exception: If API call fails or response is invalid
        """
        log_operation_start(
            logger,
            "generate_variants",
            author=author_name,
            variants_count=num_variants,
            content_length=len(original_content)
        )
        
        try:
            prompt = self._create_prompt(original_content, author_name, num_variants)
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
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
                "top_p": 0.9
            }
            
            async with httpx.AsyncClient() as client:
                log_api_call(logger, "POST", self.api_url, "GitHub Models API")
                
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=60.0
                )
                
                logger.info(f"🌐 API POST {self.api_url} → {response.status_code} ")
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
                    "generate_variants",
                    variants_count=len(variants),
                    model=self.model
                )
                
                return variants
                
        except Exception as e:
            log_operation_error(logger, "generate_variants", e)
            raise
    
    def _create_prompt(self, original_content: str, author_name: str, num_variants: int) -> str:
        """
        Create the prompt for generating post variants.
        
        Args:
            original_content: The original post content
            author_name: Name of the original post author
            num_variants: Number of variants to generate
        
        Returns:
            The formatted prompt
        """
        return f"""I need you to create {num_variants} alternative versions of the following LinkedIn post.

ORIGINAL POST by {author_name}:
---
{original_content}
---

REQUIREMENTS:
1. Create {num_variants} distinct variants that maintain the core message
2. Each variant should have a different tone or angle:
   - Variant 1: Professional and formal
   - Variant 2: Enthusiastic and energetic
   - Variant 3: Conversational and approachable
3. Keep the same hashtags or suggest similar relevant ones
4. Maintain similar length to the original
5. Preserve any emojis or use similar appropriate ones
6. Each variant should feel authentic and engaging
7. DO NOT include any meta-commentary, explanations, or labels like "Variant 1:", "Option 1:", etc.
8. Separate each variant with exactly "---VARIANT---" on its own line

OUTPUT FORMAT:
Return exactly {num_variants} variants separated by ---VARIANT--- markers, with no additional text, explanations, or labels.

Example output format:
This is the first variant text here.

#Hashtag1 #Hashtag2
---VARIANT---
This is the second variant text here.

#Hashtag1 #Hashtag2
---VARIANT---
This is the third variant text here.

#Hashtag1 #Hashtag2

Now generate the {num_variants} variants:"""
    
    def _parse_variants(self, content: str, expected_count: int) -> List[str]:
        """
        Parse variants from the AI response.
        
        Args:
            content: The raw AI response content
            expected_count: Expected number of variants
        
        Returns:
            List of parsed variants
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


def get_ai_service() -> AIService:
    """Get a configured AI service instance."""
    return AIService()
