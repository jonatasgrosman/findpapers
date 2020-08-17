from setuptools import find_packages, setup

setup(
  name='findpapers',
  version='1.0.0',
  url='https://gitlab.com/grosmanjs/findpapers',
  license='MIT',
  maintainer='Jonatas Grosman',
  maintainer_email='grosman.jonatas@gmail.com',
  description='Easy way to find academic papers across scientific libraries using a single query',
  long_description=open('README.md').read(),
  packages=find_packages(),
  include_package_data=True,
  package_data={
    '': ['*.json']
  },
  python_requires='>=3.7',
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
