"""
Sandboxed Filesystem Tools for KageBunshin Agent

This module provides secure filesystem operations for KageBunshin agents, allowing
them to read, write, and manipulate files within a strictly sandboxed environment.
The implementation prioritizes security above all else, preventing path traversal
attacks, limiting file sizes, and restricting file types.

Security Architecture:
1. **Sandbox Containment**: All operations are restricted to a base directory
2. **Path Validation**: Rigorous checking to prevent directory traversal
3. **Resource Limits**: File size and operation count restrictions
4. **Extension Filtering**: Whitelist-based file type restrictions
5. **Atomic Operations**: Prevent corruption during concurrent access
6. **Comprehensive Logging**: All operations are tracked for security auditing

The tools follow LangChain's @tool decorator pattern and return structured JSON
responses that the agent can easily parse and act upon. Error conditions are
handled gracefully without raising exceptions that could crash the agent.

Example Usage:
    ```python
    # In agent initialization:
    filesystem_tools = get_filesystem_tools({
        "sandbox_base": "/path/to/sandbox",
        "max_file_size": 1024 * 1024,  # 1MB
        "allowed_extensions": ["txt", "md", "json"],
        "enabled": True
    })
    
    # Tools are automatically available to the agent:
    # - read_file(path)
    # - write_file(path, content)
    # - list_directory(path)
    # - delete_file(path)
    # - create_directory(path)
    # - file_info(path)
    ```

Security Note:
This module handles potentially dangerous user input (file paths) and must be
thoroughly tested against path traversal attacks, encoding issues, symlink
attacks, and other common filesystem security vulnerabilities.
"""

import os
import json
import logging
import hashlib
import tempfile
import shutil
import stat
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool
from dataclasses import dataclass

# Configure logging for security auditing
logger = logging.getLogger(__name__)


@dataclass
class FilesystemConfig:
    """
    Configuration for filesystem sandbox operations.
    
    This dataclass encapsulates all configuration parameters for the filesystem
    sandbox, making it easy to pass around and validate configuration settings.
    
    Attributes:
        sandbox_base (str): Absolute path to the sandbox root directory
        max_file_size (int): Maximum allowed file size in bytes
        allowed_extensions (List[str]): Whitelist of permitted file extensions
        enabled (bool): Whether filesystem operations are enabled
        allow_overwrite (bool): Whether to allow overwriting existing files
        create_sandbox (bool): Whether to create sandbox directory if it doesn't exist
        log_operations (bool): Whether to log all filesystem operations
    """
    sandbox_base: str
    max_file_size: int = 10 * 1024 * 1024  # 10MB default
    allowed_extensions: List[str] = None
    enabled: bool = True
    allow_overwrite: bool = True
    create_sandbox: bool = True
    log_operations: bool = True
    
    def __post_init__(self):
        """Post-initialization validation and setup."""
        if self.allowed_extensions is None:
            # Default safe file extensions
            self.allowed_extensions = [
                "txt", "md", "json", "csv", "xml", "html", "css", "js", 
                "py", "yaml", "yml", "log", "rst", "ini", "cfg", "conf"
            ]
        
        # Convert to lowercase for case-insensitive matching
        self.allowed_extensions = [ext.lower() for ext in self.allowed_extensions]
        
        # Ensure sandbox_base is an absolute path
        self.sandbox_base = os.path.abspath(self.sandbox_base)


class FilesystemSecurityError(Exception):
    """Exception raised when a filesystem operation violates security constraints."""
    
    def __init__(self, message: str, path: str = None, operation: str = None):
        super().__init__(message)
        self.path = path
        self.operation = operation


class FilesystemSandbox:
    """
    Core filesystem sandbox implementation with security-first design.
    
    This class provides the low-level implementation for all filesystem operations
    within the sandbox. It handles path validation, security checks, and actual
    file operations while maintaining strict security boundaries.
    
    The sandbox uses multiple layers of security:
    1. Path resolution and validation to prevent traversal attacks
    2. Extension whitelisting to prevent dangerous file types
    3. Size limits to prevent resource exhaustion
    4. Atomic operations to prevent corruption
    5. Comprehensive error handling and logging
    """
    
    def __init__(self, config: FilesystemConfig):
        """
        Initialize the filesystem sandbox with the given configuration.
        
        Args:
            config (FilesystemConfig): Sandbox configuration parameters
            
        Raises:
            FilesystemSecurityError: If sandbox cannot be initialized safely
        """
        self.config = config
        self._setup_sandbox()
        
        if config.log_operations:
            logger.info(f"Filesystem sandbox initialized: {config.sandbox_base}")
    
    def _setup_sandbox(self) -> None:
        """
        Set up the sandbox directory with proper permissions and validation.
        
        This method creates the sandbox directory if needed and validates that
        it's safe to use as a sandbox root.
        
        Raises:
            FilesystemSecurityError: If sandbox setup fails or is unsafe
        """
        if not self.config.enabled:
            return
        
        sandbox_path = Path(self.config.sandbox_base)
        
        # Create sandbox directory if it doesn't exist and we're allowed to
        if not sandbox_path.exists():
            if self.config.create_sandbox:
                try:
                    sandbox_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created sandbox directory: {sandbox_path}")
                except OSError as e:
                    raise FilesystemSecurityError(
                        f"Failed to create sandbox directory: {e}",
                        path=str(sandbox_path),
                        operation="setup"
                    )
            else:
                raise FilesystemSecurityError(
                    f"Sandbox directory does not exist: {sandbox_path}",
                    path=str(sandbox_path),
                    operation="setup"
                )
        
        # Validate that the sandbox path is a directory
        if not sandbox_path.is_dir():
            raise FilesystemSecurityError(
                f"Sandbox path is not a directory: {sandbox_path}",
                path=str(sandbox_path),
                operation="setup"
            )
        
        # Check that we have appropriate permissions
        try:
            # Test write permissions by creating a temporary file
            test_file = sandbox_path / f".sandbox_test_{os.getpid()}"
            test_file.write_text("test")
            test_file.unlink()
        except OSError as e:
            raise FilesystemSecurityError(
                f"Insufficient permissions for sandbox directory: {e}",
                path=str(sandbox_path),
                operation="setup"
            )
    
    def _validate_path(self, path: str, operation: str) -> Path:
        """
        Validate and resolve a path within the sandbox.
        
        This is the critical security function that prevents path traversal attacks
        and ensures all operations stay within the sandbox boundaries.
        
        Args:
            path (str): The relative path to validate
            operation (str): The operation being performed (for logging)
            
        Returns:
            Path: The resolved absolute path within the sandbox
            
        Raises:
            FilesystemSecurityError: If the path is invalid or outside sandbox
        """
        if not self.config.enabled:
            raise FilesystemSecurityError(
                "Filesystem operations are disabled",
                path=path,
                operation=operation
            )
        
        if not path or not isinstance(path, str):
            raise FilesystemSecurityError(
                "Path must be a non-empty string",
                path=str(path),
                operation=operation
            )
        
        # Remove any leading slashes to ensure relative path
        path = path.lstrip('/')
        
        # Basic checks for obviously malicious patterns
        if '..' in path or path.startswith('/') or ':' in path:
            raise FilesystemSecurityError(
                f"Path contains forbidden characters: {path}",
                path=path,
                operation=operation
            )
        
        try:
            # Construct the full path within sandbox
            sandbox_root = Path(self.config.sandbox_base).resolve()
            target_path = (sandbox_root / path).resolve()
            
            # Critical security check: ensure resolved path is within sandbox
            try:
                target_path.relative_to(sandbox_root)
            except ValueError:
                raise FilesystemSecurityError(
                    f"Path resolves outside sandbox: {path} -> {target_path}",
                    path=path,
                    operation=operation
                )
            
            return target_path
            
        except (OSError, ValueError) as e:
            raise FilesystemSecurityError(
                f"Invalid path: {path} ({e})",
                path=path,
                operation=operation
            )
    
    def _validate_extension(self, path: Path, operation: str) -> None:
        """
        Validate file extension against whitelist.
        
        Args:
            path (Path): The file path to check
            operation (str): The operation being performed
            
        Raises:
            FilesystemSecurityError: If extension is not allowed
        """
        if not self.config.allowed_extensions:
            return  # No restrictions if list is empty
        
        # Extract extension (handle files without extensions)
        extension = path.suffix.lower().lstrip('.')
        
        # Allow files without extensions if configured
        if not extension:
            return  # For now, allow files without extensions
        
        if extension not in self.config.allowed_extensions:
            raise FilesystemSecurityError(
                f"File extension '{extension}' not allowed. "
                f"Permitted extensions: {', '.join(self.config.allowed_extensions)}",
                path=str(path),
                operation=operation
            )
    
    def _validate_file_size(self, size: int, path: str, operation: str) -> None:
        """
        Validate file size against configured limits.
        
        Args:
            size (int): File size in bytes
            path (str): File path for error reporting
            operation (str): Operation being performed
            
        Raises:
            FilesystemSecurityError: If file is too large
        """
        if size > self.config.max_file_size:
            raise FilesystemSecurityError(
                f"File size {size} bytes exceeds limit of {self.config.max_file_size} bytes",
                path=path,
                operation=operation
            )
    
    def _log_operation(self, operation: str, path: str, success: bool, 
                      error: str = None, metadata: Dict = None) -> None:
        """
        Log filesystem operation for security auditing.
        
        Args:
            operation (str): The operation performed
            path (str): The file path involved
            success (bool): Whether the operation succeeded
            error (str): Error message if operation failed
            metadata (Dict): Additional metadata to log
        """
        if not self.config.log_operations:
            return
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "path": path,
            "success": success,
            "sandbox": self.config.sandbox_base
        }
        
        if error:
            log_entry["error"] = error
        
        if metadata:
            log_entry.update(metadata)
        
        if success:
            logger.info(f"Filesystem operation: {json.dumps(log_entry)}")
        else:
            logger.warning(f"Filesystem operation failed: {json.dumps(log_entry)}")
    
    def read_file(self, path: str) -> Dict[str, Any]:
        """
        Read file content from within the sandbox.
        
        Args:
            path (str): Relative path to the file within sandbox
            
        Returns:
            Dict[str, Any]: Operation result with content or error
        """
        try:
            target_path = self._validate_path(path, "read_file")
            self._validate_extension(target_path, "read_file")
            
            if not target_path.exists():
                result = {
                    "status": "error",
                    "error_type": "file_not_found",
                    "error_message": f"File does not exist: {path}",
                    "file_path": path
                }
                self._log_operation("read_file", path, False, result["error_message"])
                return result
            
            if not target_path.is_file():
                result = {
                    "status": "error",
                    "error_type": "not_a_file",
                    "error_message": f"Path is not a file: {path}",
                    "file_path": path
                }
                self._log_operation("read_file", path, False, result["error_message"])
                return result
            
            # Check file size before reading
            file_size = target_path.stat().st_size
            self._validate_file_size(file_size, path, "read_file")
            
            # Read file content with proper encoding handling
            try:
                content = target_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                result = {
                    "status": "error",
                    "error_type": "encoding_error",
                    "error_message": f"File contains non-UTF-8 content: {path}",
                    "file_path": path
                }
                self._log_operation("read_file", path, False, result["error_message"])
                return result
            
            result = {
                "status": "success",
                "content": content,
                "file_path": path,
                "size": file_size,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self._log_operation("read_file", path, True, metadata={"size": file_size})
            return result
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation",
                "error_message": str(e),
                "file_path": path
            }
            self._log_operation("read_file", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error reading file: {e}",
                "file_path": path
            }
            self._log_operation("read_file", path, False, str(e))
            return result
    
    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write content to a file within the sandbox using atomic operations.
        
        This method uses atomic writes to prevent corruption if the operation
        is interrupted. It writes to a temporary file first, then moves it
        to the target location.
        
        Args:
            path (str): Relative path to the file within sandbox
            content (str): Content to write to the file
            
        Returns:
            Dict[str, Any]: Operation result with status and metadata
        """
        try:
            target_path = self._validate_path(path, "write_file")
            self._validate_extension(target_path, "write_file")
            
            # Validate content size
            if not isinstance(content, str):
                content = str(content)
            
            content_bytes = content.encode('utf-8')
            content_size = len(content_bytes)
            self._validate_file_size(content_size, path, "write_file")
            
            # Check if file exists and we're not allowed to overwrite
            if target_path.exists() and not self.config.allow_overwrite:
                result = {
                    "status": "error",
                    "error_type": "file_exists",
                    "error_message": f"File already exists and overwrite is disabled: {path}",
                    "file_path": path
                }
                self._log_operation("write_file", path, False, result["error_message"])
                return result
            
            # Create parent directories if they don't exist
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use atomic write operation - write to temp file first
            temp_file = None
            try:
                # Create temporary file in the same directory as target
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=target_path.parent,
                    prefix=f".{target_path.name}.tmp",
                    text=True
                )
                temp_file = Path(temp_path)
                
                # Write content to temporary file
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Atomically move temp file to target location
                temp_file.replace(target_path)
                temp_file = None  # Successfully moved, don't cleanup
                
                result = {
                    "status": "success",
                    "file_path": path,
                    "bytes_written": content_size,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": "write" if not target_path.exists() else "overwrite"
                }
                
                self._log_operation("write_file", path, True, 
                                  metadata={"bytes_written": content_size})
                return result
                
            finally:
                # Cleanup temporary file if it still exists (error case)
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass  # Best effort cleanup
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation",
                "error_message": str(e),
                "file_path": path
            }
            self._log_operation("write_file", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error writing file: {e}",
                "file_path": path
            }
            self._log_operation("write_file", path, False, str(e))
            return result
    
    def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """
        List contents of a directory within the sandbox.
        
        Args:
            path (str): Relative path to directory within sandbox
            
        Returns:
            Dict[str, Any]: Directory listing with file metadata
        """
        try:
            target_path = self._validate_path(path, "list_directory")
            
            if not target_path.exists():
                result = {
                    "status": "error",
                    "error_type": "directory_not_found",
                    "error_message": f"Directory does not exist: {path}",
                    "directory_path": path
                }
                self._log_operation("list_directory", path, False, result["error_message"])
                return result
            
            if not target_path.is_dir():
                result = {
                    "status": "error",
                    "error_type": "not_a_directory",
                    "error_message": f"Path is not a directory: {path}",
                    "directory_path": path
                }
                self._log_operation("list_directory", path, False, result["error_message"])
                return result
            
            # Collect directory contents
            files = []
            total_size = 0
            
            try:
                for item in sorted(target_path.iterdir()):
                    try:
                        stat_info = item.stat()
                        is_file = item.is_file()
                        is_dir = item.is_dir()
                        
                        # Skip special files, symlinks, etc.
                        if not (is_file or is_dir):
                            continue
                        
                        item_info = {
                            "name": item.name,
                            "type": "file" if is_file else "directory",
                            "size": stat_info.st_size if is_file else None,
                            "modified_time": datetime.fromtimestamp(
                                stat_info.st_mtime, tz=timezone.utc
                            ).isoformat(),
                            "permissions": stat.filemode(stat_info.st_mode)
                        }
                        
                        if is_file:
                            total_size += stat_info.st_size
                            # Add extension information
                            extension = item.suffix.lower().lstrip('.')
                            item_info["extension"] = extension if extension else None
                        
                        files.append(item_info)
                        
                    except OSError as e:
                        # Skip files we can't stat (permission issues, etc.)
                        logger.warning(f"Could not stat file {item}: {e}")
                        continue
                
            except PermissionError as e:
                result = {
                    "status": "error",
                    "error_type": "permission_denied",
                    "error_message": f"Permission denied accessing directory: {path}",
                    "directory_path": path
                }
                self._log_operation("list_directory", path, False, str(e))
                return result
            
            result = {
                "status": "success",
                "directory_path": path,
                "files": files,
                "total_files": len([f for f in files if f["type"] == "file"]),
                "total_directories": len([f for f in files if f["type"] == "directory"]),
                "total_size": total_size,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self._log_operation("list_directory", path, True, 
                              metadata={"file_count": len(files)})
            return result
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation", 
                "error_message": str(e),
                "directory_path": path
            }
            self._log_operation("list_directory", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error listing directory: {e}",
                "directory_path": path
            }
            self._log_operation("list_directory", path, False, str(e))
            return result
    
    def delete_file(self, path: str) -> Dict[str, Any]:
        """
        Safely delete a file within the sandbox.
        
        Args:
            path (str): Relative path to file within sandbox
            
        Returns:
            Dict[str, Any]: Operation result
        """
        try:
            target_path = self._validate_path(path, "delete_file")
            
            if not target_path.exists():
                result = {
                    "status": "error",
                    "error_type": "file_not_found",
                    "error_message": f"File does not exist: {path}",
                    "file_path": path
                }
                self._log_operation("delete_file", path, False, result["error_message"])
                return result
            
            if not target_path.is_file():
                result = {
                    "status": "error",
                    "error_type": "not_a_file",
                    "error_message": f"Path is not a file: {path}",
                    "file_path": path
                }
                self._log_operation("delete_file", path, False, result["error_message"])
                return result
            
            # Get file size before deletion for logging
            file_size = target_path.stat().st_size
            
            # Delete the file
            target_path.unlink()
            
            result = {
                "status": "success",
                "file_path": path,
                "deleted": True,
                "size_freed": file_size,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self._log_operation("delete_file", path, True, 
                              metadata={"size_freed": file_size})
            return result
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation",
                "error_message": str(e),
                "file_path": path
            }
            self._log_operation("delete_file", path, False, str(e))
            return result
        
        except PermissionError as e:
            result = {
                "status": "error",
                "error_type": "permission_denied",
                "error_message": f"Permission denied deleting file: {path}",
                "file_path": path
            }
            self._log_operation("delete_file", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error deleting file: {e}",
                "file_path": path
            }
            self._log_operation("delete_file", path, False, str(e))
            return result
    
    def create_directory(self, path: str) -> Dict[str, Any]:
        """
        Create a directory (and parent directories) within the sandbox.
        
        Args:
            path (str): Relative path to directory within sandbox
            
        Returns:
            Dict[str, Any]: Operation result
        """
        try:
            target_path = self._validate_path(path, "create_directory")
            
            # Check if directory already exists
            if target_path.exists():
                if target_path.is_dir():
                    result = {
                        "status": "success",
                        "directory_path": path,
                        "created": False,
                        "message": "Directory already exists",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    self._log_operation("create_directory", path, True, 
                                      metadata={"already_exists": True})
                    return result
                else:
                    result = {
                        "status": "error",
                        "error_type": "file_exists",
                        "error_message": f"Path exists but is not a directory: {path}",
                        "directory_path": path
                    }
                    self._log_operation("create_directory", path, False, result["error_message"])
                    return result
            
            # Create directory and parents
            target_path.mkdir(parents=True, exist_ok=True)
            
            result = {
                "status": "success",
                "directory_path": path,
                "created": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self._log_operation("create_directory", path, True, 
                              metadata={"created": True})
            return result
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation",
                "error_message": str(e),
                "directory_path": path
            }
            self._log_operation("create_directory", path, False, str(e))
            return result
        
        except PermissionError as e:
            result = {
                "status": "error",
                "error_type": "permission_denied",
                "error_message": f"Permission denied creating directory: {path}",
                "directory_path": path
            }
            self._log_operation("create_directory", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error creating directory: {e}",
                "directory_path": path
            }
            self._log_operation("create_directory", path, False, str(e))
            return result
    
    def file_info(self, path: str) -> Dict[str, Any]:
        """
        Get detailed information about a file or directory.
        
        Args:
            path (str): Relative path within sandbox
            
        Returns:
            Dict[str, Any]: File metadata and information
        """
        try:
            target_path = self._validate_path(path, "file_info")
            
            if not target_path.exists():
                result = {
                    "status": "success",
                    "file_path": path,
                    "exists": False,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                self._log_operation("file_info", path, True, 
                                  metadata={"exists": False})
                return result
            
            stat_info = target_path.stat()
            is_file = target_path.is_file()
            is_dir = target_path.is_dir()
            
            result = {
                "status": "success",
                "file_path": path,
                "exists": True,
                "type": "file" if is_file else "directory" if is_dir else "other",
                "size": stat_info.st_size,
                "created_time": datetime.fromtimestamp(
                    stat_info.st_ctime, tz=timezone.utc
                ).isoformat(),
                "modified_time": datetime.fromtimestamp(
                    stat_info.st_mtime, tz=timezone.utc
                ).isoformat(),
                "accessed_time": datetime.fromtimestamp(
                    stat_info.st_atime, tz=timezone.utc
                ).isoformat(),
                "permissions": stat.filemode(stat_info.st_mode),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if is_file:
                # Add file-specific information
                extension = target_path.suffix.lower().lstrip('.')
                result["extension"] = extension if extension else None
                
                # Calculate file hash for integrity checking
                try:
                    with open(target_path, 'rb') as f:
                        file_hash = hashlib.sha256()
                        for chunk in iter(lambda: f.read(4096), b""):
                            file_hash.update(chunk)
                        result["sha256"] = file_hash.hexdigest()
                except OSError:
                    result["sha256"] = None
            
            self._log_operation("file_info", path, True, 
                              metadata={"type": result["type"], "size": result["size"]})
            return result
            
        except FilesystemSecurityError as e:
            result = {
                "status": "error",
                "error_type": "security_violation",
                "error_message": str(e),
                "file_path": path
            }
            self._log_operation("file_info", path, False, str(e))
            return result
        
        except Exception as e:
            result = {
                "status": "error",
                "error_type": "unexpected_error",
                "error_message": f"Unexpected error getting file info: {e}",
                "file_path": path
            }
            self._log_operation("file_info", path, False, str(e))
            return result


def get_filesystem_tools(config: Union[Dict[str, Any], FilesystemConfig]) -> List:
    """
    Create filesystem tools for KageBunshin agent with the given configuration.
    
    This function creates and returns a list of LangChain tools that provide
    sandboxed filesystem operations. Each tool is bound to the configuration
    and sandbox instance, ensuring consistent security policies across all
    filesystem operations.
    
    Args:
        config (Union[Dict, FilesystemConfig]): Filesystem configuration
        
    Returns:
        List: List of LangChain tools for filesystem operations
        
    Raises:
        FilesystemSecurityError: If configuration is invalid or unsafe
    """
    # Convert dict config to FilesystemConfig if needed
    if isinstance(config, dict):
        config = FilesystemConfig(**config)
    
    # Create sandbox instance
    sandbox = FilesystemSandbox(config)
    
    # Define tools using the @tool decorator pattern
    @tool
    def read_file(path: str) -> str:
        """Read the contents of a file within the sandbox.
        
        This tool allows the agent to read text files within the sandboxed
        filesystem. The file must exist and be within the allowed size limits
        and have a permitted file extension.
        
        Use this tool to:
        - Read configuration files or data files
        - Load templates or content for processing
        - Access previously saved work or logs
        - Import data from external sources (that have been saved to sandbox)
        
        Security: This tool cannot access files outside the sandbox directory.
        Path traversal attempts (../) are blocked, and only whitelisted file
        types can be read.
        
        Args:
            path (str): Relative path to the file within the sandbox.
                       Examples: "data.txt", "config/settings.json", "logs/today.log"
        
        Returns:
            str: JSON string with operation result. On success, includes:
                 - status: "success"
                 - content: The file content as a string
                 - file_path: The requested path
                 - size: File size in bytes
                 
                 On error, includes:
                 - status: "error"
                 - error_type: Category of error (file_not_found, security_violation, etc.)
                 - error_message: Human-readable error description
        
        Example:
            result = read_file("data/customer_list.csv")
            # Returns: {"status": "success", "content": "name,email\\nJohn,john@example.com", ...}
        """
        return json.dumps(sandbox.read_file(path))
    
    @tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file within the sandbox.
        
        This tool allows the agent to create new files or overwrite existing
        files within the sandboxed filesystem. The operation is atomic - either
        the entire file is written successfully or nothing is changed.
        
        Use this tool to:
        - Save processed data or analysis results
        - Create configuration files or templates
        - Export data in various formats (JSON, CSV, etc.)
        - Store work-in-progress or final outputs
        - Create logs or audit trails
        
        Security: Files are written atomically using temporary files to prevent
        corruption. Only permitted file extensions can be created, and file
        size limits are enforced.
        
        Args:
            path (str): Relative path for the file within the sandbox.
                       Parent directories will be created if needed.
                       Examples: "output.txt", "reports/analysis.json"
            content (str): Content to write to the file. Must be text content
                          that can be encoded as UTF-8.
        
        Returns:
            str: JSON string with operation result. On success, includes:
                 - status: "success"
                 - file_path: The file path that was written
                 - bytes_written: Number of bytes written
                 - operation: "write" or "overwrite"
                 
                 On error, includes:
                 - status: "error"
                 - error_type: Category of error
                 - error_message: Human-readable error description
        
        Example:
            result = write_file("analysis.json", '{"results": [1, 2, 3]}')
            # Returns: {"status": "success", "file_path": "analysis.json", "bytes_written": 20, ...}
        """
        return json.dumps(sandbox.write_file(path, content))
    
    @tool
    def list_directory(path: str = ".") -> str:
        """List the contents of a directory within the sandbox.
        
        This tool provides a detailed listing of files and subdirectories
        within the specified directory, including metadata like file sizes,
        modification times, and file types.
        
        Use this tool to:
        - Explore the current sandbox structure
        - Find specific files or check if files exist
        - Get file metadata (size, modification time)
        - Navigate through directory structures
        - Audit what files have been created
        
        Args:
            path (str, optional): Relative path to directory within sandbox.
                                 Defaults to "." (current directory/sandbox root).
                                 Examples: ".", "data", "reports/monthly"
        
        Returns:
            str: JSON string with directory listing. On success, includes:
                 - status: "success"
                 - directory_path: The directory that was listed
                 - files: Array of file/directory objects with metadata
                 - total_files: Count of files in directory
                 - total_directories: Count of subdirectories
                 - total_size: Total size of all files in bytes
                 
                 Each file object includes:
                 - name: File or directory name
                 - type: "file" or "directory"
                 - size: Size in bytes (files only)
                 - modified_time: ISO timestamp of last modification
                 - permissions: Unix-style permission string
                 - extension: File extension (files only)
        
        Example:
            result = list_directory("data")
            # Returns: {"status": "success", "files": [{"name": "input.csv", "type": "file", ...}], ...}
        """
        return json.dumps(sandbox.list_directory(path))
    
    @tool
    def delete_file(path: str) -> str:
        """Safely delete a file within the sandbox.
        
        This tool permanently removes a file from the sandbox filesystem.
        Use with caution as this operation cannot be undone.
        
        Use this tool to:
        - Clean up temporary files or intermediate results
        - Remove outdated data files
        - Free up space by deleting large files
        - Remove sensitive data that's no longer needed
        
        Security: Only files within the sandbox can be deleted. Directories
        cannot be deleted with this tool (prevents accidental data loss).
        
        Args:
            path (str): Relative path to the file to delete within sandbox.
                       Must be an existing file (not directory).
                       Examples: "temp.txt", "old_data/backup.json"
        
        Returns:
            str: JSON string with operation result. On success, includes:
                 - status: "success"
                 - file_path: The path that was deleted
                 - deleted: True
                 - size_freed: Number of bytes freed
                 
                 On error, includes:
                 - status: "error"
                 - error_type: Category of error (file_not_found, not_a_file, etc.)
                 - error_message: Human-readable error description
        
        Example:
            result = delete_file("temporary_data.csv")
            # Returns: {"status": "success", "file_path": "temporary_data.csv", "size_freed": 1024, ...}
        """
        return json.dumps(sandbox.delete_file(path))
    
    @tool
    def create_directory(path: str) -> str:
        """Create a directory within the sandbox.
        
        This tool creates a new directory (and any necessary parent directories)
        within the sandbox filesystem. Similar to 'mkdir -p' command.
        
        Use this tool to:
        - Organize files into logical directory structures
        - Create directories for different data categories
        - Set up directory hierarchies for complex projects
        - Prepare directory structure before saving files
        
        Args:
            path (str): Relative path for the directory to create within sandbox.
                       Parent directories will be created as needed.
                       Examples: "data", "reports/2024/january", "temp/processing"
        
        Returns:
            str: JSON string with operation result. On success, includes:
                 - status: "success"
                 - directory_path: The directory path that was created
                 - created: True if new directory was created, False if already existed
                 
                 On error, includes:
                 - status: "error"
                 - error_type: Category of error
                 - error_message: Human-readable error description
        
        Example:
            result = create_directory("analysis/results")
            # Returns: {"status": "success", "directory_path": "analysis/results", "created": true, ...}
        """
        return json.dumps(sandbox.create_directory(path))
    
    @tool
    def file_info(path: str) -> str:
        """Get detailed information about a file or directory.
        
        This tool provides comprehensive metadata about a file or directory,
        including size, timestamps, permissions, and integrity information.
        
        Use this tool to:
        - Check if a file exists before reading/writing
        - Get file metadata for analysis or reporting
        - Verify file integrity using checksums
        - Monitor file changes over time
        - Debug file access issues
        
        Args:
            path (str): Relative path to file or directory within sandbox.
                       Examples: "data.csv", "reports", "config/settings.json"
        
        Returns:
            str: JSON string with file information. Always includes:
                 - status: "success" (even if file doesn't exist)
                 - file_path: The requested path
                 - exists: Boolean indicating if path exists
                 
                 If file exists, also includes:
                 - type: "file", "directory", or "other"
                 - size: Size in bytes
                 - created_time: ISO timestamp of creation
                 - modified_time: ISO timestamp of last modification
                 - accessed_time: ISO timestamp of last access
                 - permissions: Unix-style permission string
                 - extension: File extension (files only)
                 - sha256: SHA-256 hash of file content (files only, for integrity)
        
        Example:
            result = file_info("important_data.json")
            # Returns: {"status": "success", "exists": true, "type": "file", "size": 2048, ...}
        """
        return json.dumps(sandbox.file_info(path))
    
    # Return list of tools in the order they're typically used
    tools = [
        read_file,
        write_file, 
        list_directory,
        file_info,
        create_directory,
        delete_file
    ]
    
    logger.info(f"Created {len(tools)} filesystem tools with sandbox: {config.sandbox_base}")
    return tools


# Convenience function for quick setup during development/testing
def create_test_sandbox(base_path: str = None) -> FilesystemSandbox:
    """
    Create a filesystem sandbox for testing purposes.
    
    This is a convenience function for development and testing that creates
    a sandbox with permissive settings suitable for experimentation.
    
    Args:
        base_path (str, optional): Base path for sandbox. If None, uses temp directory.
        
    Returns:
        FilesystemSandbox: Configured sandbox instance
    """
    if base_path is None:
        base_path = os.path.join(tempfile.gettempdir(), "kagebunshin_test_sandbox")
    
    config = FilesystemConfig(
        sandbox_base=base_path,
        max_file_size=10 * 1024 * 1024,  # 10MB
        allowed_extensions=["txt", "md", "json", "csv", "xml", "html", "py", "yaml", "log"],
        enabled=True,
        allow_overwrite=True,
        create_sandbox=True,
        log_operations=True
    )
    
    return FilesystemSandbox(config)


def cleanup_workspace(workspace_base: str, 
                     max_age_days: int = 30,
                     max_size_bytes: int = 100 * 1024 * 1024,
                     log_operations: bool = True) -> Dict[str, Any]:
    """
    Clean up old agent directories from the workspace.
    
    This function performs automatic cleanup of the KageBunshin workspace by:
    1. Removing agent directories older than max_age_days
    2. If workspace still exceeds max_size_bytes, removes oldest directories first
    3. Logs all cleanup operations for transparency
    
    Args:
        workspace_base (str): Path to the workspace root directory
        max_age_days (int): Maximum age in days before cleanup (default: 30)
        max_size_bytes (int): Maximum total workspace size (default: 100MB)
        log_operations (bool): Whether to log cleanup operations (default: True)
        
    Returns:
        Dict[str, Any]: Cleanup results with statistics
    """
    try:
        workspace_path = Path(workspace_base)
        
        if not workspace_path.exists():
            result = {
                "status": "success",
                "workspace_path": workspace_base,
                "message": "Workspace does not exist, no cleanup needed",
                "directories_removed": 0,
                "space_freed": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            if log_operations:
                logger.info(f"Workspace cleanup: {json.dumps(result)}")
            return result
        
        if not workspace_path.is_dir():
            result = {
                "status": "error",
                "error_type": "not_a_directory",
                "error_message": f"Workspace path is not a directory: {workspace_base}",
                "workspace_path": workspace_base
            }
            if log_operations:
                logger.warning(f"Workspace cleanup failed: {json.dumps(result)}")
            return result
        
        # Collect all agent directories with metadata
        agent_dirs = []
        current_time = time.time()
        cutoff_time = current_time - (max_age_days * 24 * 60 * 60)
        
        for item in workspace_path.iterdir():
            if item.is_dir() and item.name.startswith("agent_"):
                try:
                    stat_info = item.stat()
                    dir_size = _get_directory_size(item)
                    
                    agent_dirs.append({
                        "path": item,
                        "name": item.name,
                        "modified_time": stat_info.st_mtime,
                        "size": dir_size,
                        "age_days": (current_time - stat_info.st_mtime) / (24 * 60 * 60)
                    })
                except OSError as e:
                    if log_operations:
                        logger.warning(f"Could not stat agent directory {item}: {e}")
                    continue
        
        # Phase 1: Remove directories older than max_age_days
        dirs_to_remove = []
        for agent_dir in agent_dirs:
            if agent_dir["modified_time"] < cutoff_time:
                dirs_to_remove.append(agent_dir)
        
        # Phase 2: If still over size limit, remove oldest first
        remaining_dirs = [d for d in agent_dirs if d not in dirs_to_remove]
        current_size = sum(d["size"] for d in remaining_dirs)
        
        if current_size > max_size_bytes:
            # Sort remaining directories by age (oldest first)
            remaining_dirs.sort(key=lambda x: x["modified_time"])
            
            for agent_dir in remaining_dirs:
                if current_size <= max_size_bytes:
                    break
                dirs_to_remove.append(agent_dir)
                current_size -= agent_dir["size"]
        
        # Perform cleanup
        directories_removed = 0
        space_freed = 0
        removed_dirs = []
        
        for agent_dir in dirs_to_remove:
            try:
                shutil.rmtree(agent_dir["path"])
                directories_removed += 1
                space_freed += agent_dir["size"]
                removed_dirs.append({
                    "name": agent_dir["name"],
                    "age_days": round(agent_dir["age_days"], 1),
                    "size": agent_dir["size"]
                })
                
                if log_operations:
                    logger.info(f"Removed agent directory: {agent_dir['name']} "
                              f"(age: {agent_dir['age_days']:.1f} days, "
                              f"size: {agent_dir['size']:,} bytes)")
                              
            except OSError as e:
                if log_operations:
                    logger.error(f"Failed to remove agent directory {agent_dir['name']}: {e}")
                continue
        
        result = {
            "status": "success",
            "workspace_path": workspace_base,
            "directories_removed": directories_removed,
            "space_freed": space_freed,
            "removed_directories": removed_dirs,
            "remaining_directories": len(agent_dirs) - directories_removed,
            "max_age_days": max_age_days,
            "max_size_bytes": max_size_bytes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if log_operations:
            logger.info(f"Workspace cleanup completed: {json.dumps(result, default=str)}")
        
        return result
        
    except Exception as e:
        result = {
            "status": "error",
            "error_type": "unexpected_error",
            "error_message": f"Unexpected error during workspace cleanup: {e}",
            "workspace_path": workspace_base
        }
        if log_operations:
            logger.error(f"Workspace cleanup failed: {json.dumps(result)}")
        return result


def _get_directory_size(directory: Path) -> int:
    """
    Calculate total size of a directory and all its contents.
    
    Args:
        directory (Path): Directory to measure
        
    Returns:
        int: Total size in bytes
    """
    total_size = 0
    try:
        for item in directory.rglob('*'):
            if item.is_file():
                try:
                    total_size += item.stat().st_size
                except OSError:
                    # Skip files we can't stat
                    continue
    except OSError:
        # If we can't access the directory, return 0
        pass
    
    return total_size