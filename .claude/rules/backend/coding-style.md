---
paths:
  - "backend/**"
---
# Backend Coding Style (Python)

## Standards
- **Async/await** for all I/O operations
- **Type hints** required on all functions
- **Pydantic models** for request/response validation
- **Docstrings** for all services
- **Services pattern**: Business logic in `services/`, not in routes
- **Testing**: Pytest with async support, 80%+ coverage target
- **Formatting**: Follow existing patterns (4 spaces, snake_case)

## Example Service Function
```python
async def get_file_list(
    path: str,
    current_user: User,
    db: Session
) -> List[FileItem]:
    """
    Retrieve file list for a given path.

    Args:
        path: Relative path to list
        current_user: Authenticated user context
        db: Database session

    Returns:
        List of FileItem objects

    Raises:
        PermissionError: If user lacks access
    """
    # Implementation
```

## Testing Strategy (`backend/tests/`)
- **Unit tests**: Test services in isolation with mocks
- **Integration tests**: Test API endpoints with test database
- **Fixtures**: Use pytest fixtures for database, auth tokens
- **Test database**: Separate SQLite database for tests
- **Coverage**: 40+ test files, 364 test functions
- Run with: `python -m pytest -v`
