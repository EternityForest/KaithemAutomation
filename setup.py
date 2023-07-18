import os
from setuptools import setup, find_packages


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="kaithem",
    version="0.68.42",
    author="Daniel Dunn",
    author_email="danny@example.com",
    description=("Home/Commercial automation server"),
    license="GPLv3",
    keywords="automation",
    url="https://github.com/EternityForest/KaithemAutomation",
    packages=find_packages(),
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: GPLv3 License",
    ],
    entry_points = {
        'console_scripts': [
            'kaithem = kaithem:start',                  
        ],              
    }
)
