# Contributing to BaluHost

Thank you for your interest in contributing to BaluHost! This document provides guidelines and instructions for contributing to the project.

## 🌟 How to Contribute

We welcome contributions of all kinds:
- 🐛 Bug reports and fixes
- ✨ New features
- 📚 Documentation improvements
- 🧪 Tests
- 🎨 UI/UX enhancements
- 🌍 Translations

## 📋 Before You Start

1. **Check existing issues** - Someone might already be working on it
2. **Read the documentation** - Familiarize yourself with the architecture
3. **Ask questions** - Open a discussion if you're unsure

## 🚀 Development Setup

### Prerequisites
- **Python 3.11+** (Backend)
- **Node.js 18+** (Frontend)
- **Git**

### Getting Started

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/BaluHost.git
cd BaluHost

# 2. Start development environment
python start_dev.py

# This will:
# - Set up Python virtual environment
# - Install dependencies
# - Start FastAPI backend (port 3001)
# - Start Vite dev server (port 5173)
# - Initialize 2x5GB RAID1 sandbox storage
```

### Manual Setup (Alternative)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 3001
```

**Frontend:**
```bash
cd client
npm install
npm run dev
```

## 📝 Code Style Guidelines

### Python (Backend)

**Code Standards:**
- Follow **PEP 8** style guide
- Use **type hints** for all functions
- Write **docstrings** for public functions (Google style)
- Keep functions focused and under 50 lines when possible

**Example:**
```python
from typing import List
from app.schemas.files import FileItem

def list_files(path: str, owner_id: int) -> List[FileItem]:
    """
    List all files in a directory owned by the user.
    
    Args:
        path: The directory path to list
        owner_id: The ID of the requesting user
        
    Returns:
        List of FileItem objects
        
    Raises:
        PermissionError: If user doesn't have access
        FileNotFoundError: If path doesn't exist
    """
    # Implementation
    pass
```

**Structure:**
- Services in `app/services/` - Business logic
- Routes in `app/api/routes/` - API endpoints
- Schemas in `app/schemas/` - Pydantic models
- Use async/await for I/O operations

**Linting:**
```bash
cd backend
black app/  # Format code
pylint app/ # Check code quality
mypy app/   # Type checking
```

### TypeScript/React (Frontend)

**Code Standards:**
- Use **TypeScript strict mode**
- Functional components with **hooks**
- **Tailwind CSS** for styling (no inline styles)
- Custom hooks in `src/hooks/`

**Example:**
```typescript
import { useState, useEffect } from 'react';
import { FileItem } from '../types';

interface FileListProps {
  path: string;
  onFileClick: (file: FileItem) => void;
}

export default function FileList({ path, onFileClick }: FileListProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadFiles();
  }, [path]);

  const loadFiles = async () => {
    // Implementation
  };

  return (
    <div className="grid gap-4">
      {/* Component JSX */}
    </div>
  );
}
```

**Linting:**
```bash
cd client
npm run lint      # ESLint
npm run type-check # TypeScript check
```

## 🧪 Testing

### Writing Tests

**Backend (pytest):**
```bash
cd backend
python -m pytest                    # Run all tests
python -m pytest tests/test_*.py    # Run specific test
python -m pytest -v --cov=app       # With coverage
```

**Test Structure:**
```python
import pytest
from app.services.files import list_files

def test_list_files_success():
    """Test successful file listing."""
    files = list_files("/demo", owner_id=1)
    assert len(files) > 0
    assert all(f.owner_id == 1 for f in files)

def test_list_files_permission_denied():
    """Test permission denied for unauthorized access."""
    with pytest.raises(PermissionError):
        list_files("/demo", owner_id=999)
```

**Frontend (Vitest - TODO):**
```bash
cd client
npm run test
```

### Test Requirements
- **All new features must have tests**
- Maintain **80%+ code coverage**
- Tests should be deterministic (no random failures)
- Use dev-mode fixtures for reproducibility

## 🔀 Git Workflow

### Branch Naming
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring
- `test/description` - Test additions

**Examples:**
- `feature/file-sharing`
- `fix/upload-progress-bar`
- `docs/api-endpoints`

### Commit Messages

Follow **Conventional Commits** format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(files): add file sharing with public links

Implemented public link generation with optional password
protection and expiry dates. Users can now share files
with external parties without requiring an account.

Closes #123
```

```
fix(upload): prevent duplicate file uploads

Added duplicate detection before upload to prevent
overwriting files accidentally.

Fixes #456
```

### Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Write clean, documented code
   - Add/update tests
   - Update documentation

3. **Test thoroughly**
   ```bash
   # Backend
   cd backend && python -m pytest
   
   # Frontend
   cd client && npm run build
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): descriptive message"
   ```

5. **Push to your fork**
   ```bash
   git push origin feature/my-feature
   ```

6. **Open a Pull Request**
   - Use a clear, descriptive title
   - Reference related issues
   - Describe what changed and why
   - Include screenshots for UI changes

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Related Issues
Closes #123
Related to #456

## Testing
- [ ] Backend tests pass
- [ ] Frontend builds successfully
- [ ] Manual testing completed

## Screenshots (if applicable)
```

## 🎯 Feature Development Process

### 1. Planning Phase
- Open an issue or discussion
- Describe the feature and use case
- Get feedback from maintainers

### 2. Implementation Phase
- Create feature branch
- Implement backend (if needed)
  - Add service logic
  - Add API routes
  - Add schemas
- Implement frontend (if needed)
  - Create/update components
  - Add API calls
  - Update UI

### 3. Documentation Phase
- Update `TECHNICAL_DOCUMENTATION.md`
- Add feature-specific docs in `docs/`
- Update API documentation
- Add code comments

### 4. Testing Phase
- Write unit tests
- Write integration tests
- Manual testing in dev mode
- Test edge cases

### 5. Review Phase
- Create pull request
- Address review comments
- Update based on feedback

## 📚 Documentation Standards

### Code Documentation

**Python Docstrings:**
```python
def complex_function(param1: str, param2: int) -> dict:
    """
    Short description of function.
    
    Longer description if needed, explaining behavior,
    edge cases, and important details.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter
        
    Returns:
        Dictionary containing results with keys:
        - 'status': Operation status
        - 'data': Result data
        
    Raises:
        ValueError: If param2 is negative
        PermissionError: If user lacks access
        
    Example:
        >>> result = complex_function("test", 42)
        >>> print(result['status'])
        'success'
    """
    pass
```

**TypeScript Comments:**
```typescript
/**
 * Uploads a file to the server with progress tracking.
 * 
 * @param file - The file to upload
 * @param path - Target directory path
 * @param onProgress - Callback for upload progress (0-100)
 * @returns Promise resolving to uploaded file metadata
 * @throws {Error} If upload fails or quota exceeded
 * 
 * @example
 * ```ts
 * await uploadFile(file, "/documents", (progress) => {
 *   console.log(`Upload: ${progress}%`);
 * });
 * ```
 */
async function uploadFile(
  file: File,
  path: string,
  onProgress?: (progress: number) => void
): Promise<FileItem> {
  // Implementation
}
```

### Feature Documentation

Create a new doc in `docs/` for major features:

**Template:**
```markdown
# Feature Name

## Overview
Brief description of the feature

## Use Cases
- Use case 1
- Use case 2

## Architecture
How it's implemented (diagrams if helpful)

## API Endpoints
List of relevant endpoints

## Configuration
Environment variables and settings

## Examples
Code examples and usage scenarios

## Testing
How to test this feature

## Future Improvements
Ideas for enhancement
```

## 🐛 Bug Reports

### Before Reporting
1. Search existing issues
2. Test in dev mode with latest code
3. Collect error messages and logs

### Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
1. Go to '...'
2. Click on '...'
3. See error

**Expected behavior**
What you expected to happen.

**Screenshots**
If applicable, add screenshots.

**Environment:**
- OS: [e.g. Windows 11, Ubuntu 22.04]
- Python version: [e.g. 3.11.5]
- Node version: [e.g. 18.17.0]
- Browser: [e.g. Chrome 120]

**Additional context**
Any other relevant information.
```

## ⚠️ Important Notes

### Do NOT:
- ❌ Commit sensitive data (passwords, tokens, keys)
- ❌ Change the Express backend in `server/` (legacy code)
- ❌ Submit PRs without tests
- ❌ Use `any` type in TypeScript
- ❌ Add dependencies without discussion

### DO:
- ✅ Write tests for your code
- ✅ Update documentation
- ✅ Follow code style guidelines
- ✅ Keep PRs focused and small
- ✅ Respond to review comments

## 🎓 Learning Resources

### Project-Specific
- [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) - Complete feature docs
- [docs/](docs/) - Feature-specific documentation
- [TODO.md](TODO.md) - Roadmap and planned features

### Technologies
- **FastAPI:** https://fastapi.tiangolo.com/
- **React:** https://react.dev/
- **TypeScript:** https://www.typescriptlang.org/docs/
- **Tailwind CSS:** https://tailwindcss.com/docs
- **Pydantic:** https://docs.pydantic.dev/

## 💬 Communication

### Getting Help
- Open a **Discussion** for questions
- Join our community (TODO: Discord/Matrix link)
- Check existing documentation first

### Reporting Security Issues
**DO NOT** open public issues for security vulnerabilities.
Email security concerns to: [security@baluhost.example] (TODO)

## 📜 Code of Conduct

Be respectful, inclusive, and professional. We're all here to learn and build something great together.

- Be welcoming to newcomers
- Respect differing opinions
- Accept constructive criticism
- Focus on what's best for the project
- Show empathy towards others

## 🎉 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing to BaluHost! 🚀
