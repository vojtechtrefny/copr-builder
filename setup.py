#!/usr/bin/python3

import setuptools


with open("README.rst", "r", encoding="utf-8") as f:
    long_description = f.read()


setuptools.setup(name='copr-builder',
                 version='1.0',
                 description='Python script for building git projects in Copr',
                 long_description=long_description,
                 long_description_content_type="text/x-rst",
                 author='Vojtech Trefny',
                 author_email='vtrefny@redhat.com',
                 url='https://github.com/vojtechtrefny/copr-builder',
                 packages=['copr_builder'],
                 scripts=['copr-builder'])
