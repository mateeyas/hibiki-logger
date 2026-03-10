# Contributing to Hibiki Logger

Thank you for your interest in contributing to Hibiki Logger!

## Development Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/mateeyas/hibiki-logger.git
   cd hibiki-logger
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
pytest
```

## Code Style

- Use [Black](https://github.com/psf/black) for formatting
- Follow PEP 8 guidelines
- Add type hints where appropriate

```bash
black .
flake8 .
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Questions?

Open an issue or reach out to the maintainers.
