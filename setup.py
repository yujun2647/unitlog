#!/usr/bin/env python
import os

from setuptools import setup
from unitlog import __version__

with open("README.md", "r") as fp:
    README = fp.read()


def _get_requires(filename):
    with open(filename, "r") as fp:
        lines = fp.readlines()
        return [l.replace("\n", "") for l in lines
                if not l.startswith("#") and not l.startswith("-")]


def walk_package(package):
    packages = []
    package_data = {}
    for name, folders, files in os.walk(package):
        folders = [f for f in folders if not f.startswith("__")]
        files = [f for f in files if not f.endswith(".pyc")]
        if "__init__.py" in files:
            packages.append(name)
            for folder in folders:
                sub_name = os.path.join(name, folder)
                _packages, _package_data = walk_package(sub_name)
                packages.extend(_packages)
                for name, values in _package_data.items():
                    if name in package_data:
                        package_data[name].extend(values)
                    else:
                        package_data[name] = values
        else:
            items = name.split("/")
            top_name = items[0]
            rest_header = "/".join(items[1:])
            if folders or files:
                package_data.setdefault(top_name, [])
            for folder in folders:
                data = (f"{rest_header}/{folder}/*" if rest_header
                        else f"{folder}/*")
                package_data[top_name].append(data)
            for file in files:
                data = (f"{rest_header}/{file}" if rest_header
                        else file)
                package_data[top_name].append(data)
    return packages, package_data


all_packages, all_package_data = walk_package("unitlog")

setup(
    name="unitlog",
    version=__version__,
    description="",
    python_requires=">=3.6",
    install_requires=[],
    url="https://github.com/yujun2647/unitlog",
    license='Apache-2.0',
    author="walkerjun",
    author_email="yujun2647@163.com",
    download_url="",
    packages=all_packages,
    package_data=all_package_data,
    long_description=README,
    long_description_content_type='text/markdown'
)
