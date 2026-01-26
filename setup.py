#!/usr/bin/env python3
"""Setup script for the reminder system."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="desktop-reminder-system",
    version="1.0.0",
    author="Your Name",
    description="A desktop reminder system with overlay notifications for Linux/KDE Plasma",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "PyQt6>=6.4.0",
        "croniter>=1.3.0",
        "tomli>=2.0.0;python_version<'3.11'",
    ],
    entry_points={
        "console_scripts": [
            "reminder-system=reminder_system.app:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Desktop Environment :: K Desktop Environment (KDE)",
    ],
)
