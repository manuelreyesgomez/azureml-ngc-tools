#!/usr/bin/env python

from os.path import exists
from setuptools import setup, find_packages

import versioneer

setup(
    name="azureml_ngc_tools",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="AzureML integration with NGC",
    url="",
    keywords="azureml,ngc,gpu",
    license="BSD",
    packages=find_packages(),
    include_package_data=True,
    long_description_content_type="text/markdown",
    long_description=(open("README.md").read() if exists("README.md") else ""),
    zip_safe=False,
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    entry_points="""
    [console_scripts]
    azureml-ngc-tools=azureml_ngc_tools.cli.azureml_ngc:go
    """,
    python_requires=">=3.5",
)
