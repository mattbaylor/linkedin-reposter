# Contributing to LinkedIn Reposter

Thank you for your interest in contributing to LinkedIn Reposter! This document provides guidelines for contributing to the project.

## Code of Conduct

Please be respectful and considerate in your interactions. We're building a welcoming community for everyone.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Your environment (OS, Docker version, etc.)
- Relevant logs or error messages

### Suggesting Features

Feature suggestions are welcome! Please open an issue with:
- A clear description of the feature
- The use case or problem it solves
- Any implementation ideas you have

### Pull Requests

1. **Fork the repository** and create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style
   - Use meaningful variable names
   - Add comments for complex logic
   - Follow existing patterns in the codebase

3. **Test your changes**
   ```bash
   docker compose build
   docker compose up -d
   # Verify functionality works as expected
   ```

4. **Commit your changes** with clear messages
   ```bash
   git commit -m "Add feature: brief description"
   ```

5. **Push to your fork** and open a Pull Request
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Describe your PR** with:
   - What changes you made
   - Why you made them
   - How to test them

## Development Setup

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed setup instructions.

### Quick Start

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/linkedin-reposter.git
cd linkedin-reposter

# Copy environment file
cp .env.example .env
# Edit .env with your Infisical credentials

# Build and run
docker compose build
docker compose up -d

# View logs
docker compose logs -f app
```

## Code Style

- **Python**: Follow PEP 8 guidelines
- **Imports**: Group standard library, third-party, and local imports
- **Docstrings**: Use for functions and classes
- **Type Hints**: Use where appropriate
- **Logging**: Use the logger, not print statements

### Example

```python
"""Module docstring."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def my_function(param: str, optional: Optional[int] = None) -> bool:
    """
    Brief description of function.
    
    Args:
        param: Description of param
        optional: Description of optional param
        
    Returns:
        Description of return value
    """
    logger.info(f"Processing {param}")
    # Implementation
    return True
```

## Areas for Contribution

### Good First Issues
- Documentation improvements
- Adding error handling
- Writing tests
- UI/UX improvements in admin dashboard

### Advanced Contributions
- New AI providers integration
- Enhanced scheduling algorithms
- Performance optimizations
- Analytics/metrics features

## Testing

Before submitting a PR:
1. Test the basic workflow (scrape → AI → approve → post)
2. Check that existing features still work
3. Test error cases
4. Review logs for errors or warnings

## Documentation

If your changes affect:
- **User-facing features**: Update README.md
- **API endpoints**: Update API_ENDPOINTS.md
- **Configuration**: Update relevant docs
- **Deployment**: Update DEPLOYMENT.md

## Questions?

- Open an issue with the "question" label
- Check existing issues and documentation first
- Be specific about what you need help with

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be acknowledged in the project! Significant contributions may be highlighted in release notes.

---

Thank you for helping make LinkedIn Reposter better! 🎉
