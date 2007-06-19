from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

setup(
    name='CabochonClient',
    version="0.1",
    description="A client for the Cabochon event server",
    author="David Turner",
    author_email="novalis@openplans.org",
    url="http://www.openplans.org/projects/cabochon",
    license="GPLv2 or any later version",
    install_requires=["simplejson"],
    packages=find_packages(),
    include_package_data=True,
)
