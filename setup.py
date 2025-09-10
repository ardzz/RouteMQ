from setuptools import setup, find_packages

setup(
    name="routemq",
    version="0.1.0",
    description="A flexible MQTT routing framework with middleware support",
    author="Naufal Reky Ardhana",
    packages=find_packages(),
    install_requires=[
        "paho-mqtt>=1.5.0",
        "python-dotenv>=0.15.0",
        "sqlalchemy>=1.4.0",
    ],
    extras_require={
        "mysql": ["aiomysql>=0.2.0"],
    },
    python_requires=">=3.7",
    entry_points={
        'console_scripts': [
            'routemq=main:main',
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
