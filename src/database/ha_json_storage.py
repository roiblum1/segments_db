import json
import logging
import asyncio
import os
import shutil
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from filelock import FileLock

logger = logging.getLogger(__name__)

class HAJSONStorage:
    """High Availability JSON storage with dual-write to primary and backup locations"""

    def __init__(self, primary_dir: str = "/app/data", backup_dir: str = "/app/backup"):
        self.primary_dir = Path(primary_dir)
        self.backup_dir = Path(backup_dir)

        self.primary_file = self.primary_dir / "segments.json"
        self.backup_file = self.backup_dir / "segments.json"

        self.primary_lock_file = self.primary_dir / "segments.json.lock"
        self.backup_lock_file = self.backup_dir / "segments.json.lock"

        self._primary_lock = FileLock(str(self.primary_lock_file), timeout=10)
        self._backup_lock = FileLock(str(self.backup_lock_file), timeout=10)

        # Create data directories if they don't exist
        self.primary_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize data files
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize primary and backup storage files"""
        initial_data = {"segments": [], "next_id": 1}

        # Initialize primary
        if not self.primary_file.exists():
            self._write_to_file(self.primary_file, initial_data)
            logger.info(f"Initialized new primary data file at {self.primary_file}")

        # Initialize backup or sync from primary
        if not self.backup_file.exists():
            if self.primary_file.exists():
                # Copy primary to backup
                try:
                    shutil.copy2(self.primary_file, self.backup_file)
                    logger.info(f"Initialized backup from primary at {self.backup_file}")
                except Exception as e:
                    logger.warning(f"Could not copy primary to backup: {e}, creating new backup")
                    self._write_to_file(self.backup_file, initial_data)
            else:
                self._write_to_file(self.backup_file, initial_data)
                logger.info(f"Initialized new backup data file at {self.backup_file}")

    def _read_from_file(self, file_path: Path) -> Dict[str, Any]:
        """Read data from a JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Error reading {file_path}: {e}")
            return {"segments": [], "next_id": 1}

    def _write_to_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Write data to a JSON file atomically"""
        try:
            # Write to temporary file first
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            # Atomic rename
            temp_file.replace(file_path)
            return True
        except Exception as e:
            logger.error(f"Error writing to {file_path}: {e}")
            return False

    def _dual_write(self, data: Dict[str, Any]) -> tuple[bool, bool]:
        """Write to both primary and backup with proper locking"""
        primary_success = False
        backup_success = False

        # Write to primary
        try:
            with self._primary_lock:
                primary_success = self._write_to_file(self.primary_file, data)
        except Exception as e:
            logger.error(f"Error writing to primary: {e}")

        # Write to backup (independent of primary success)
        try:
            with self._backup_lock:
                backup_success = self._write_to_file(self.backup_file, data)
        except Exception as e:
            logger.error(f"Error writing to backup: {e}")

        if primary_success and backup_success:
            logger.debug("Dual-write successful to both primary and backup")
        elif primary_success:
            logger.warning("Written to primary only, backup write failed")
        elif backup_success:
            logger.warning("Written to backup only, primary write failed")
        else:
            logger.error("Dual-write failed for both primary and backup")

        return primary_success, backup_success

    def _read_with_fallback(self) -> Dict[str, Any]:
        """Read from primary, fall back to backup if primary fails"""
        # Try primary first
        try:
            with self._primary_lock:
                data = self._read_from_file(self.primary_file)
                if data.get("segments") is not None:  # Valid data
                    return data
        except Exception as e:
            logger.warning(f"Error reading primary: {e}, trying backup")

        # Fallback to backup
        try:
            with self._backup_lock:
                data = self._read_from_file(self.backup_file)
                if data.get("segments") is not None:
                    logger.warning("Using backup data, primary failed")
                    # Try to restore primary from backup
                    try:
                        with self._primary_lock:
                            self._write_to_file(self.primary_file, data)
                            logger.info("Restored primary from backup")
                    except:
                        pass
                    return data
        except Exception as e:
            logger.error(f"Error reading backup: {e}")

        # Both failed, return empty data
        logger.error("Both primary and backup reads failed, returning empty data")
        return {"segments": [], "next_id": 1}

    async def _execute_with_lock(self, func):
        """Execute a function with file locks (runs in thread pool to avoid blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        def _find():
            data = self._read_with_fallback()
            for segment in data["segments"]:
                if self._matches_query(segment, query):
                    return segment.copy()
            return None

        return await self._execute_with_lock(_find)

    async def find(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find all segments matching the query"""
        def _find():
            data = self._read_with_fallback()
            results = []
            for segment in data["segments"]:
                if self._matches_query(segment, query):
                    results.append(segment.copy())
            return results

        return await self._execute_with_lock(_find)

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a segment and update it atomically with dual-write"""
        def _find_and_update():
            # Read with fallback
            data = self._read_with_fallback()

            # Find matching segments
            matches = []
            for i, segment in enumerate(data["segments"]):
                if self._matches_query(segment, query):
                    matches.append((i, segment))

            if not matches:
                return None

            # Sort if specified
            if sort:
                for sort_field, sort_order in reversed(sort):
                    matches.sort(
                        key=lambda x: x[1].get(sort_field, 0),
                        reverse=(sort_order == -1)
                    )

            # Update first match
            idx, segment = matches[0]
            if "$set" in update:
                segment.update(update["$set"])

            data["segments"][idx] = segment

            # Dual write
            primary_ok, backup_ok = self._dual_write(data)

            if not primary_ok and not backup_ok:
                logger.error("Dual-write failed, update may be lost")
                return None

            return segment.copy()

        return await self._execute_with_lock(_find_and_update)

    async def insert_one(self, document: Dict[str, Any]) -> str:
        """Insert a new segment with dual-write"""
        def _insert():
            # Read with fallback
            data = self._read_with_fallback()

            # Generate new ID
            new_id = str(data["next_id"])
            data["next_id"] += 1

            # Add ID to document
            document["_id"] = new_id

            # Add to segments
            data["segments"].append(document)

            # Dual write
            primary_ok, backup_ok = self._dual_write(data)

            if not primary_ok and not backup_ok:
                logger.error("Dual-write failed, insert may be lost")
                raise Exception("Failed to write to both primary and backup")

            return new_id

        return await self._execute_with_lock(_insert)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> int:
        """Update a single segment matching the query with dual-write"""
        def _update():
            # Read with fallback
            data = self._read_with_fallback()
            modified = 0

            for segment in data["segments"]:
                if self._matches_query(segment, query):
                    if "$set" in update:
                        segment.update(update["$set"])
                    modified = 1
                    break

            if modified:
                # Dual write
                primary_ok, backup_ok = self._dual_write(data)
                if not primary_ok and not backup_ok:
                    logger.error("Dual-write failed, update may be lost")
                    return 0

            return modified

        return await self._execute_with_lock(_update)

    async def delete_one(self, query: Dict[str, Any]) -> int:
        """Delete a single segment matching the query with dual-write"""
        def _delete():
            # Read with fallback
            data = self._read_with_fallback()
            deleted = 0

            for i, segment in enumerate(data["segments"]):
                if self._matches_query(segment, query):
                    data["segments"].pop(i)
                    deleted = 1
                    break

            if deleted:
                # Dual write
                primary_ok, backup_ok = self._dual_write(data)
                if not primary_ok and not backup_ok:
                    logger.error("Dual-write failed, deletion may not be persisted")
                    return 0

            return deleted

        return await self._execute_with_lock(_delete)

    async def count_documents(self, query: Dict[str, Any]) -> int:
        """Count segments matching the query"""
        def _count():
            data = self._read_with_fallback()
            count = 0
            for segment in data["segments"]:
                if self._matches_query(segment, query):
                    count += 1
            return count

        return await self._execute_with_lock(_count)

    def _matches_query(self, document: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if document matches query"""
        for key, value in query.items():
            if key == "$or":
                # Handle $or operator
                if not any(self._matches_query(document, condition) for condition in value):
                    return False
            elif isinstance(value, dict):
                # Handle operators
                if "$ne" in value:
                    if document.get(key) == value["$ne"]:
                        return False
                elif "$regex" in value:
                    import re
                    pattern = value["$regex"]
                    options = value.get("$options", "")
                    flags = re.IGNORECASE if "i" in options else 0
                    doc_value = str(document.get(key, ""))
                    if not re.search(pattern, doc_value, flags):
                        return False
                else:
                    # Unknown operator, compare directly
                    if document.get(key) != value:
                        return False
            else:
                # Direct comparison
                if document.get(key) != value:
                    return False
        return True

    @property
    def data_file(self):
        """Return primary data file path for compatibility"""
        return self.primary_file

    def get_health_status(self) -> Dict[str, Any]:
        """Get HA storage health status"""
        status = {
            "primary": {
                "path": str(self.primary_file),
                "exists": self.primary_file.exists(),
                "readable": os.access(self.primary_file, os.R_OK) if self.primary_file.exists() else False,
                "writable": os.access(self.primary_file, os.W_OK) if self.primary_file.exists() else False,
            },
            "backup": {
                "path": str(self.backup_file),
                "exists": self.backup_file.exists(),
                "readable": os.access(self.backup_file, os.R_OK) if self.backup_file.exists() else False,
                "writable": os.access(self.backup_file, os.W_OK) if self.backup_file.exists() else False,
            }
        }

        # Check if files are in sync
        if status["primary"]["exists"] and status["backup"]["exists"]:
            try:
                primary_data = self._read_from_file(self.primary_file)
                backup_data = self._read_from_file(self.backup_file)
                status["in_sync"] = (
                    primary_data.get("next_id") == backup_data.get("next_id") and
                    len(primary_data.get("segments", [])) == len(backup_data.get("segments", []))
                )
            except:
                status["in_sync"] = False
        else:
            status["in_sync"] = False

        return status


# Global storage instance
_storage: Optional[HAJSONStorage] = None


def get_storage() -> HAJSONStorage:
    """Get the global HA storage instance"""
    global _storage
    if _storage is None:
        primary_dir = os.getenv("DATA_DIR", "/app/data")
        backup_dir = os.getenv("BACKUP_DIR", "/app/backup")
        _storage = HAJSONStorage(primary_dir, backup_dir)
        logger.info(f"Initialized HA JSON storage - Primary: {primary_dir}, Backup: {backup_dir}")
    return _storage


async def init_storage():
    """Initialize HA storage"""
    storage = get_storage()
    logger.info("HA JSON storage initialized successfully")


async def close_storage():
    """Close storage connection (no-op for JSON)"""
    logger.info("HA JSON storage closed")
