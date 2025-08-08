from .cli import run


if __name__ == "__main__":
    # Delegate to CLI argument parser so flags like --chat work with `-m kagebunshin`
    run()

