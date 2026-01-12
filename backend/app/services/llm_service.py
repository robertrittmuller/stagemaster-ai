import litellm
import logging
import asyncio
import base64
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure litellm
litellm.telemetry = False

import io
from PIL import Image

# ... (imports)

async def _fetch_and_encode_image(image_url: str) -> tuple[str, str, int, int]:
    """
    Helper to fetch image from URL (handling internal/MinIO URLs).
    - Resizes image if either dimension > 2160px.
    - Returns (media_type, base64_string, width, height).
    """
    # Fetch image content
    image_content = None
    
    internal_prefix = f"http://{settings.STORAGE_ENDPOINT}/"
    public_prefix = f"http://{settings.STORAGE_PUBLIC_ENDPOINT}/"
    
    target_prefix = None
    if image_url.startswith(internal_prefix):
        target_prefix = internal_prefix
    elif image_url.startswith(public_prefix):
        target_prefix = public_prefix
        
    if target_prefix:
        from app.services.storage import storage_service
        path_parts = image_url.replace(target_prefix, "").split("/", 1)
        if len(path_parts) == 2:
            bucket, object_name = path_parts
            image_content = storage_service.get_object_data(bucket, object_name)
    
    if image_content is None:
        async with httpx.AsyncClient() as client:
            image_response = await client.get(image_url)
            image_response.raise_for_status()
            image_content = image_response.content

    # Process image with Pillow
    try:
        with Image.open(io.BytesIO(image_content)) as img:
            width, height = img.size
            if width > 2160 or height > 2160:
                img.thumbnail((2160, 2160), Image.Resampling.LANCZOS)
                width, height = img.size
                
                # Save resized image to buffer
                buffer = io.BytesIO()
                # Determine format
                fmt = img.format if img.format else 'JPEG'
                img.save(buffer, format=fmt)
                image_content = buffer.getvalue()
                
            media_type = "image/jpeg"
            if img.format == 'PNG':
                media_type = "image/png"
            elif img.format == 'WEBP':
                media_type = "image/webp"

            image_base64 = base64.b64encode(image_content).decode('utf-8')
            return media_type, image_base64, width, height
            
    except Exception as e:
        logger.error(f"Error processing image with Pillow: {e}")
        # Fallback to original content if Pillow fails, assuming jpeg
        image_base64 = base64.b64encode(image_content).decode('utf-8')
        return "image/jpeg", image_base64, 0, 0

async def analyze_room(image_url: str) -> str:
    """
    Analyzes room layout, surfaces, and depth using LiteLLM/OpenRouter.
    Returns a text description of the room analysis.
    """
    prompt = f"""
    Analyze the uploaded interior photo for virtual staging.
    Provide a detailed analysis of:
    1. Room dimensions and layout.
    2. Floor material and visible surfaces (walls, ceiling).
    3. Lighting conditions, window placements, natural light sources, and reflections.
    4. Color temperature and existing white balance (note if it needs correction).
    5. Suggested zones for furniture placement.
    
    Image URL: {image_url}
    """
    
    try:
        media_type, image_base64, _, _ = await _fetch_and_encode_image(image_url)
        
        response = await litellm.acompletion(
            model=settings.LITELLM_ANALYSIS_MODEL,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_base64}"}}
                ]}
            ],
            api_key=settings.OPENROUTER_API_KEY
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling LiteLLM for room analysis: {str(e)}")
        raise

# ... (plan_furniture_placement and generate_staged_image_prompt remain unchanged)

# Duplicate generate_image removed (confirmed)

async def plan_furniture_placement(analysis: str, room_type: str, style_preset: str, wall_decorations: bool = True) -> str:
    """
    Generates a furniture placement plan based on room analysis.
    """
    decor_instruction = "Include wall decorations like art, mirrors, or clocks, but ONLY those that do not require drilling into the wall (e.g., leaning mirrors, leaning art, or lightweight items that can be mounted with adhesive strips)." if wall_decorations else "Do NOT include any wall decorations or wall art."
    
    prompt = f"""
    Based on the following room analysis:
    {analysis}
    
    Room Type: {room_type}
    Design Style: {style_preset}
    
    Provide a detailed furniture placement plan. List specific furniture items, their positions, and how they should look in the given design style.
    {decor_instruction}
    Include artistic directions for the image generation step.
    
    IMPORTANT: The furniture arrangement must respect the existing room layout, doors, windows, and traffic flow. 
    Do not suggest removing or altering any architectural features (walls, windows, ceilings, floors).
    The goal is to furnish the room AS IS.
    """
    
    try:
        response = await litellm.acompletion(
            model=settings.LITELLM_ANALYSIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            api_key=settings.OPENROUTER_API_KEY
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling LiteLLM for furniture placement: {str(e)}")
        raise

async def generate_staged_image_prompt(
    original_image_url: str,
    analysis: str,
    placement_plan: str,
    style_preset: str,
    fix_white_balance: bool = True,
    wall_decorations: bool = True
) -> str:
    """
    Generates a highly detailed prompt for the image generation model (e.g., Stable Diffusion or DALL-E)
    to stage the room.
    """
    if fix_white_balance:
        wb_instruction = "CORRECT the white balance if the original image is too warm (yellow) or cool (blue), making it look like high-end neutral architectural photography, BUT ensure the original colors of painted surfaces (walls, etc.) are preserved and not altered by the correction."
    else:
        wb_instruction = "STRICTLY PRESERVE the original white balance, color temperature, and lighting tint of the photo exactly as it is. Do NOT attempt to 'fix' or 'neutralize' the colors. If the original photo is warm/yellow or cool/blue, the final rendered image MUST maintain that exact same warmth or coolness."
    
    decor_instruction = "Add furniture and wall decor, ensuring that any wall-mounted items do not require drilling (e.g., use leaning art, mirrors on the floor, or lightweight decor)." if wall_decorations else "Add furniture only. Keep walls completely bare of any art or decorations."

    prompt = f"""
    You are a professional architectural photographer and interior designer.
    Create a highly detailed, photorealistic prompt for generating a virtually staged version of this room.
    
    CRITICAL INSTRUCTIONS:
    1. The goal is to VIRTUAL STAGE the EXISTING room.
    2. You MUST preserve the EXACT structure of the room (walls, ceiling, floor plan, windows, doors).
    3. You MUST preserve the EXACT camera angle and perspective of the original image.
    4. You MUST preserve the current natural lighting direction, shadows, and reflections from windows/surfaces.
    5. {wb_instruction}
    6. {decor_instruction} DO NOT remove or alter architectural elements.
    
    Original Room Analysis:
    {analysis}
    
    Furniture Plan:
    {placement_plan}
    
    Style: {style_preset}
    
    Produce a single paragraph prompt that includes lighting details, texture descriptions, specific camera settings, and photorealistic keywords.
    The prompt should explicitly consist of instructions to the generation model to "render the following furniture into the provided room image without changing the room's geometry or perspective".
    
    Original Image URL for reference: {original_image_url}
    """
    
    try:
        response = await litellm.acompletion(
            model=settings.LITELLM_ANALYSIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            api_key=settings.OPENROUTER_API_KEY
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling LiteLLM for generation prompt: {str(e)}")
        raise

async def generate_image(prompt: str, original_image_url: str = None, fix_white_balance: bool = True) -> bytes:
    """
    Generates an image using the configured image generation model.
    Returns the raw binary content of the generated image.
    Uses direct HTTP call to OpenRouter to support specific 'modalities' param for Gemini.
    """
    try:
        api_key = settings.OPENROUTER_API_KEY
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://stage-master.app", # Recommended by OpenRouter
            "X-Title": "Stage Master",
        }
        
        # Ensure we use an explicit model name, stripping openrouter/ if present to be safe, 
        # though OpenRouter often accepts both. The user example showed "google/gemini-..."
        model = settings.LITELLM_GENERATION_MODEL
        if model.startswith("openrouter/"):
            model = model.replace("openrouter/", "")

        messages_content = [{"type": "text", "text": prompt}]

        if original_image_url:
             media_type, image_base64, width, height = await _fetch_and_encode_image(original_image_url)
             messages_content.append(
                 {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_base64}"}}
             )
             
             # Add instruction for output resolution if we have valid dimensions
             if width > 0 and height > 0:
                 resolution_instruction = f"\n\nIMPORTANT: Generate the output image with the exact resolution of {width}x{height} pixels."
                 messages_content[0]["text"] += resolution_instruction
             
             if not fix_white_balance:
                 wb_preservation_instruction = "\n\nCRITICAL: You MUST preserve the original white balance and color temperature of the input image. Do NOT auto-correct or neutralize the colors. If the input is warm, the output must be equally warm."
                 messages_content[0]["text"] += wb_preservation_instruction
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": messages_content
                }
            ],
            "modalities": ["image", "text"]
        }

        logger.info(f"Calling OpenRouter Chat API for image generation with model: {model}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0 # Image generation can be slow
            )
            response.raise_for_status()
            result = response.json()
            
        # Parse response
        # Expected format: choices[0].message.images[0].image_url.url
        # The user said: message["images"] list
        
        if not result.get("choices"):
             raise ValueError(f"No choices in response: {result}")
             
        message = result["choices"][0]["message"]
        
        # OpenRouter/Gemini specific format for images in chat
        image_url = None
        if message.get("images"):
             image_url = message["images"][0]["image_url"]["url"]
        
        # Fallback: sometimes purely text models might return a link in content? 
        # But we expect 'images' key based on user snippet.
        
        if not image_url:
             # Debug log entire message to see what happened
             logger.error(f"Full response message: {message}")
             raise ValueError("No image URL found in response")

        # Handle Base64 Data URL
        if image_url.startswith("data:"):
            # Format: data:image/png;base64,.....
            header, encoded = image_url.split(",", 1)
            return base64.b64decode(encoded)
        else:
            # It's a regular URL, download it
            async with httpx.AsyncClient() as client:
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
                return img_resp.content

    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        raise
