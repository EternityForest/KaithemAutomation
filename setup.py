import os
from setuptools import setup, find_packages


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


import os

def package_files(directory, ext=''):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            if filename.endswith(ext):
                paths.append(os.path.join('..', path, filename))
    return paths

extra_files = package_files('kaithem/data/')+package_files('kaithem/src/','html')+package_files('kaithem/src/','js')+package_files('kaithem/src/','css')
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
    package_data={'': extra_files+[ '**/*.txt', '**/*.yaml','**/*.html','**/*.md','**/*.json','**/*.js','**/*.css','**/*.vue','**/*.webp','**/*.png','**/*.jpg','**/*.toml','**/*.svg', '**/*.opus','**/*.mp3']},
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: GPLv3 License",
    ],
    entry_points = {
        'console_scripts': [
            'kaithem = kaithem:start',
            'kaithem._jackmanager_server = kaithem.src.thirdparty.scullery.jack_client_subprocess:main',
            'kaithem._iceflow_server = kaithem.src.thirdparty.scullery.iceflow_server:main'                 
        ],              
    },

    install_requires=[
   'numpy',
   'Pillow',
   'tflite-runtime',
   'JACK-Client',
   'netifaces',
   'toml',
   'evdev',
   'psutil',
   'setproctitle',
   'python-rtmidi',
   'pyserial',
   'msgpack',
   'scipy',
   'scikit-image',
   'paho-mqtt',
   'python-pam'
]
)
