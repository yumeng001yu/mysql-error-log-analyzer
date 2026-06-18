from setuptools import setup, find_packages

setup(
    name="mysql-error-log-analyzer",
    version="0.1.0",
    description="Automated MySQL error log analysis tool with CLI chat and web visualization",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "langchain>=0.1.0",
        "langgraph>=0.0.30",
        "langchain-openai>=0.0.5",
        "langchain-community>=0.0.10",
        "watchdog>=3.0.0",
        "pyyaml>=6.0",
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
        "websockets>=12.0",
        "rich>=13.7.0",
        "prompt_toolkit>=3.0.43",
        "aiosqlite>=0.19.0",
        "httpx>=0.25.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "psutil>=5.9.0",
        "aiofiles>=23.2.0",
        "turbovec>=0.7.0",
        "numpy>=1.24.0",
        "pymysql>=1.1.0",
        "redis>=5.0.0",
    ],
    entry_points={
        "console_scripts": [
            "mysql-log-analyzer=src.main:main",
        ],
    },
)
