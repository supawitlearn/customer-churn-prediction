import os
from pathlib import Path
import logging

# -------------------------------
# Logging Configuration
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s]: %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# -------------------------------
# Project Configuration
# -------------------------------
PROJECT_NAME = "datascience"

# List of all project files and directories to initialize
FILES_TO_CREATE = [
    ".github/workflows/.gitkeep",
    f"src/{PROJECT_NAME}/__init__.py",
    f"src/{PROJECT_NAME}/components/__init__.py",
    f"src/{PROJECT_NAME}/utils/__init__.py",
    f"src/{PROJECT_NAME}/utils/common.py",
    f"src/{PROJECT_NAME}/config/__init__.py",
    f"src/{PROJECT_NAME}/config/configuration.py",
    f"src/{PROJECT_NAME}/pipeline/__init__.py",
    f"src/{PROJECT_NAME}/entity/__init__.py",
    f"src/{PROJECT_NAME}/entity/config_entity.py",
    f"src/{PROJECT_NAME}/constants/__init__.py",
    "config/config.yaml",
    "params.yaml",
    "schema.yaml",
    "main.py",
    "Dockerfile",
    "setup.py",
    "research/research.ipynb",
    "templates/index.html",
]

# -------------------------------
# Helper Function
# -------------------------------
def create_project_structure(file_list):
    """
    Create all directories and empty files for the initial project structure.

    Args:
        file_list (list[str]): A list of file paths to be created.

    This function:
      - Creates parent directories if they don’t exist.
      - Creates empty files if they don’t already exist or are empty.
      - Logs every action for transparency.
    """
    for file_path in file_list:
        path = Path(file_path)
        dir_path = path.parent  # Extract directory path

        # Create directory if it doesn't exist
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
            logging.info(f"Directory created (or already exists): {dir_path}")

        # Create empty file if not exists or is empty
        if not path.exists() or path.stat().st_size == 0:
            path.touch()
            logging.info(f"Created empty file: {path}")
        else:
            logging.info(f"File already exists and not empty: {path}")


# -------------------------------
# Main Execution
# -------------------------------
if __name__ == "__main__":
    logging.info("Initializing project structure setup...")
    create_project_structure(FILES_TO_CREATE)
    logging.info("Project structure setup completed successfully!")