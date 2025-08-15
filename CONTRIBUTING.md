# Contributing to Kagebunshin

Thank you for considering contributing to Kagebunshin! This document outlines the process for contributing to the project.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/kagebunshin.git
   cd kagebunshin
   ```

3. Set up the development environment:
   ```bash
   uv python install 3.13
   uv venv -p 3.13
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv sync
   uv run playwright install chromium
   ```

## Development Workflow

1. Create a new branch for your feature/bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes, ensuring they follow the project's coding standards

3. Test your changes:
   ```bash
   # Add tests and run them here when test suite is available
   uv run python -m kagebunshin --help
   ```

4. Commit your changes with a clear, descriptive commit message:
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

5. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

6. Create a pull request on GitHub

## Code Style Guidelines

- Follow PEP 8 for Python code formatting
- Use type hints where appropriate
- Write clear, descriptive docstrings for functions and classes
- Keep functions focused and modular
- Add comments for complex logic

## Reporting Issues

When reporting bugs, please include:

- A clear description of the issue
- Steps to reproduce the problem
- Expected vs. actual behavior
- Your environment details (OS, Python version, etc.)
- Any relevant log output

## Feature Requests

For new features, please:

- Check if a similar feature request already exists
- Provide a clear use case and rationale
- Consider the scope and impact on existing functionality

## Security

If you discover a security vulnerability, please report it privately to the maintainers rather than opening a public issue.

## Code of Conduct

- Be respectful and inclusive in all interactions
- Focus on constructive feedback and collaboration
- Help maintain a welcoming environment for all contributors

## Questions?

Feel free to open an issue for questions about contributing or reach out to the maintainers.