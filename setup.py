from setuptools import setup, find_packages
from typing import List
import os

# ----------------------------------------
# Constants
# ----------------------------------------
REQUIREMENTS_FILE = "requirements.txt"
HYPHEN_E_DOT = "-e ."


# ----------------------------------------
# Helper Function
# ----------------------------------------
def get_requirements(file_path: str) -> List[str]:
    """
    Read dependencies from a requirements file and return them as a list.

    Args:
        file_path (str): Path to the requirements.txt file.

    Returns:
        List[str]: A cleaned list of package requirements.
    """
    requirements: List[str] = []

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ Requirements file not found: {file_path}")

    with open(file_path, "r") as file:
        requirements = [req.strip() for req in file.readlines() if req.strip()]

    # Remove '-e .' if present, since it's used for editable installs
    if HYPHEN_E_DOT in requirements:
        requirements.remove(HYPHEN_E_DOT)

    return requirements


# ----------------------------------------
# Package Setup Configuration
# ----------------------------------------
setup(
    name="customer_churn_prediction_project",
    version="0.0.1",
    author="Supawit",
    author_email="supawit.learn@gmail.com",
    description="A machine learning project for customer churn prediction",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=get_requirements(REQUIREMENTS_FILE),
    python_requires=">=3.12",
    license="GNU GENERAL PUBLIC LICENSE",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU GENERAL PUBLIC LICENSE",
        "Operating System :: OS Independent",
    ],
)
