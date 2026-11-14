from pathlib import Path

from setuptools import find_packages, setup

readme_path = Path(__file__).with_name("README.md")

setup(
    name="ai-clips-maker",
    version="1.0.0",
    description=(
        "AI Clips Maker is an open-source Python library that automatically converts "
        "long videos into concise, speaker-aware clips using face and voice detection."
    ),
    long_description=readme_path.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Alperen Sümeroğlu",
    author_email="alperennsumeroglu@gmail.com",
    url="https://github.com/alperensumeroglu/ai-clips-maker",
    license="MIT",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "av",
        "faster-whisper",
        "flask>=3.0,<4",
        "nltk",
        "numpy",
        "psutil",
        "nvidia-ml-py",
        "sentence-transformers",
        "torch",
        "yt-dlp>=2025.1",
        "whisperx",
        "python-magic-bin; platform_system == 'Windows'",
        "python-magic; platform_system != 'Windows'",
    ],
    zip_safe=False,
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    project_urls={
        "Documentation": "https://github.com/alperensumeroglu/ai-clips-maker#readme",
        "Homepage": "https://github.com/alperensumeroglu/ai-clips-maker",
        "Repository": "https://github.com/alperensumeroglu/ai-clips-maker",
        "Issues": "https://github.com/alperensumeroglu/ai-clips-maker/issues",
    },
    include_package_data=True,
    package_data={
        "ai_clips_maker": [
            "templates/*.html",
            "static/app.css",
            "static/app.js",
            "static/favicon.svg",
            "static/Rubik-Variable.ttf",
            "static/Rubik-OFL.txt",
            "assets/platform/*.png",
        ],
    },
    extras_require={
        "resize": [
            "facenet-pytorch",
            "matplotlib",
            "mediapipe",
            "opencv-python-headless>=4.10,<5",
            "pandas",
            "pyannote.audio",
            "pyannote.core",
            "scenedetect",
            "scikit-learn",
            "scipy",
        ],
        "framing": [
            "opencv-python-headless>=4.10,<5",
        ],
        "dev": [
            "black",
            "black[jupyter]",
            "build",
            "flake8",
            "ipykernel",
            "pytest",
            "twine",
        ],
    },
)
