from setuptools import find_packages, setup


setup(
    name="twilight-zone-agent",
    version="0.1.0",
    description="Personal Research Agent / Twilight Zone",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.8",
    entry_points={"console_scripts": ["twilight-zone=twilight_zone.cli:main"]},
)
