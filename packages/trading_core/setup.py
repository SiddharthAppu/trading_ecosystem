from setuptools import setup, find_packages

setup(
    name="trading_core",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "numpy",
        "scipy",
        "python-dotenv",
        "fyers-apiv3",
        "upstox-python-sdk",
        "py-vollib",
        "blackscholes",
        "pyotp",
        "requests",
        "asyncpg",
        "fastapi",
        "uvicorn",
        "websockets",
    ],
    description="Core shared logic for unified trading platform",
)
