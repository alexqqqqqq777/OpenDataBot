from typing import List, Tuple
from src.clients import WorksectionClient
from src.storage import AsyncSessionLocal, WorksectionCaseRepository, SyncStateRepository
from src.utils import extract_case_numbers
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def sync_worksection_cases() -> int:
    """
    Sync court cases from Worksection tasks to local database.
    Extracts case numbers from task names and stores for deduplication.
    
    Returns:
        Number of cases processed
    """
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
