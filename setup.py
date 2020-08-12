import io
import re

from setuptools import find_packages, setup

with io.open('README.md', 'rt', encoding='utf8') as f:
    readme = f.read()

setup(
  name='findpapers',
  version='1.0.0',
  url='https://gitlab.com/grosmanjs/findpapers',
  license='MIT',
  maintainer='Jonatas Grosman',
  maintainer_email='grosman.jonatas@gmail.com',
  description='Easy way to do your research by finding academic papers using complex queries',
  long_description=readme,
  packages=find_packages(),
  include_package_data=True,
  package_data={
    '': ['*.json']
  },
  python_requires='>=3.6',
  install_requires=[
    'lxml==4.5.*',
    'requests==2.24.*',
    'fake-useragent==0.1.*',
    'colorama==0.4.*',
    'inquirer==2.7.*',
    'numpy==1.19.*',
    'edlib==1.3.*'
  ],
  extras_require={
    'test':[
      'pytest==6.0.*',
      'coverage==5.2.*'
    ],
    'documentation': [
      'Sphinx==3.2.*'
    ]
  }
)
