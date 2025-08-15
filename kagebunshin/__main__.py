from .cli.runner import run
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the kagebunshin console script."""
    run()


if __name__ == "__main__":
    # Delegate to CLI argument parser so flags like --chat work with `-m kagebunshin`
    main()
