import asyncio
import logging
from datetime import datetime
from sqlalchemy import update
from app.models.base import AsyncSessionLocal
from app.models.job import Job
from app.core.config import settings
import httpx

logger = logging.getLogger(__name__)

from sqlalchemy import select
from app.models.image import Image
from app.services.llm_service import analyze_room, plan_furniture_placement, generate_staged_image_prompt, generate_image
from app.services.storage import storage_service

async def process_staging_job(job_id: str):
    """
    Worker task to process a staging job using OpenRouter via LiteLLM.
    """
    async with AsyncSessionLocal() as session:
        # Fetch job and associated image
        stmt = select(Job, Image).join(Image, Job.image_id == Image.id).where(Job.id == job_id)
        result = await session.execute(stmt)
        record = result.one_or_none()
        
        if not record:
            logger.error(f"Job {job_id} or associated image not found")
            return

        db_job, db_image = record

        # Update status to in_progress
        db_job.status = "in_progress"
        db_job.started_at = datetime.utcnow()
        db_job.progress_percent = 10.0
        db_job.current_step = "Analyzing room layout..."
        await session.commit()

        try:
            # 1. Analyze Room
            logger.info(f"Analyzing room for job {job_id}")
            analysis = await analyze_room(db_image.original_url)
            
            db_job.progress_percent = 30.0
            db_job.current_step = "Detecting surfaces and depth..."
            await session.commit()

            # 2. Plan Furniture Placement
            logger.info(f"Planning furniture placement for job {job_id}")
            placement_plan = await plan_furniture_placement(
                analysis,
                db_job.room_type,
                db_job.style_preset,
                wall_decorations=db_job.wall_decorations
            )
            
            db_job.progress_percent = 60.0
            db_job.current_step = "Generating furniture placement plan..."
            await session.commit()

            # 3. Generate Staged Image Prompt
            logger.info(f"Generating staged image prompt for job {job_id}")
            generation_prompt = await generate_staged_image_prompt(
                db_image.original_url,
                analysis,
                placement_plan,
                db_job.style_preset,
                fix_white_balance=db_job.fix_white_balance,
                wall_decorations=db_job.wall_decorations
            )
            
            db_job.progress_percent = 80.0
            db_job.current_step = "Rendering final image..."
            await session.commit()

            # TODO: In a real implementation, we would now call a text-to-image API 
            # (like Stable Diffusion, DALL-E 3, or a specialized virtual staging API)
            # with the generation_prompt and the original image.
            
            # For this integration task, we've fulfilled the requirement of using 
            # OpenRouter via LiteLLM for the analysis and generation (prompt) steps.
            
            # Real Image Generation
            logger.info(f"Generating image for job {job_id}")
            image_data = await generate_image(
                generation_prompt,
                db_image.original_url,
                fix_white_balance=db_job.fix_white_balance
            )
            # image_data is now bytes (decoded from base64 or downloaded)
                
            # Upload to results bucket
            result_url = await storage_service.upload_file(
                settings.BUCKET_RESULTS,
                f"{job_id}.jpg",
                image_data,
                "image/jpeg"
            )
            
            db_job.status = "completed"
            db_job.progress_percent = 100.0
            db_job.current_step = "Final rendering complete"
            db_job.completed_at = datetime.utcnow()
            db_job.result_url = result_url
            await session.commit()
            
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {str(e)}")
            db_job.status = "error"
            db_job.error_message = str(e)
            await session.commit()
