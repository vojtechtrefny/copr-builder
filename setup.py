#!/usr/bin/python3

from distutils.core import setup

setup(name='copr-builder',
      version='0.1',
      description='Python script for building git projects in Copr',
      author='Vojtech Trefny',
      author_email='vtrefny@redhat.com',
      url='https://github.com/vojtechtrefny/copr-builder',
      packages=['copr_builder'],
      scripts=['copr-builder'],
     )
