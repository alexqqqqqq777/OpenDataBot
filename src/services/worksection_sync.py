from typing import List, Tuple
from src.clients import WorksectionClient, GistClient
from src.storage import AsyncSessionLocal, WorksectionCaseRepository, SyncStateRepository
from src.utils import extract_case_numbers
from src.config import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def is_gist_mode() -> bool:
    """Check if Gist mode is enabled (secure mode without WS API key)."""
    return bool(settings.WORKSECTION_GIST_ID)


async def sync_from_gist() -> int:
    """
    Sync case numbers from GitHub Gist (secure mode).
    Used when WORKSECTION_GIST_ID is configured.
    
    Returns:
        Number of cases processed
    """
    gist_client = GistClient(settings.WORKSECTION_GIST_ID)
    
    async with AsyncSessionLocal() as session:
        ws_repo = WorksectionCaseRepository(session)
        sync_repo = SyncStateRepository(session)
        
        logger.info("Starting Gist sync (secure mode)...")
        
        case_numbers = await gist_client.get_case_numbers(use_cache=False)
        logger.info(f"Fetched {len(case_numbers)} case numbers from Gist")
        
        processed = 0
        for case_number in case_numbers:
            try:
                await ws_repo.upsert_case(
                    normalized_case_number=case_number,
                    task_id="gist",
                    raw_name=case_number,
                    project_id="gist",
                    project_name="Gist Sync"
                )
                processed += 1
            except Exception as e:
                logger.error(f"Error saving case {case_number}: {e}")
        
        # Update sync timestamp
        await sync_repo.set_state(
            'worksection_last_sync',
            datetime.utcnow().isoformat()
        )
        
        logger.info(f"Gist sync completed: {processed} cases processed")
    
    return processed


async def sync_worksection_cases() -> int:
    """
    Sync court cases from Worksection tasks to local database.
    Uses Gist if configured, otherwise direct API.
    
    Returns:
        Number of cases processed
    """
    # Use Gist mode if configured
    if is_gist_mode():
        return await sync_from_gist()
    
    # Direct API mode
    client = WorksectionClient()
    processed = 0
    
    async with AsyncSessionLocal() as session:
        ws_repo = WorksectionCaseRepository(session)
        sync_repo = SyncStateRepository(session)
        
        logger.info("Starting Worksection sync...")
        
        # Get all tasks
        tasks = await client.get_all_tasks(extra="text")
        logger.info(f"Fetched {len(tasks)} tasks from Worksection")
        
        for task in tasks:
            task_id = str(task.get('id', ''))
            task_name = task.get('name', '')
            project = task.get('project', {})
            project_id = str(project.get('id', ''))
            project_name = project.get('name', '')
            
            # Extract case numbers from task name
            case_numbers = extract_case_numbers(task_name)
            
            for case_number in case_numbers:
                try:
                    await ws_repo.upsert_case(
                        normalized_case_number=case_number,
                        task_id=task_id,
                        raw_name=task_name,
                        project_id=project_id,
                        project_name=project_name
                    )
                    processed += 1
                except Exception as e:
                    logger.error(f"Error saving case {case_number}: {e}")
        
        # Update sync timestamp
        await sync_repo.set_state(
            'worksection_last_sync',
            datetime.utcnow().isoformat()
        )
        
        logger.info(f"Worksection sync completed: {processed} cases processed")
    
    return processed


async def get_worksection_case_numbers() -> List[str]:
    """
    Get all case numbers from Worksection database.
    """
    async with AsyncSessionLocal() as session:
        repo = WorksectionCaseRepository(session)
        return await repo.get_all_case_numbers()
