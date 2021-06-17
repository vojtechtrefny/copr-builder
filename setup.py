#!/usr/bin/python3

import setuptools  # pylint: disable=unused-import

from distutils.core import setup


with open("README.rst", "r") as f:
    long_description = f.read()


setup(name='copr-builder',
      version='0.1',
      description='Python script for building git projects in Copr',
      long_description=long_description,
      long_description_content_type="text/x-rst",
      author='Vojtech Trefny',
      author_email='vtrefny@redhat.com',
      url='https://github.com/vojtechtrefny/copr-builder',
      packages=['copr_builder'],
      scripts=['copr-builder'])
