from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

setup(
    name='CabochonClient',
    version="",
    #description="",
    author="David Turner",
    author_email="novalis@openplans.org",
    #url="",
    install_requires=["simplejson"],
    packages=find_packages(),
    include_package_data=True,
)
