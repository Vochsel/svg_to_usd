import setuptools
from svg_to_usd.version import Version

setuptools.setup(name='svg_to_usd',
                 version=Version('0.1.0').number,
                 description="Convert SVG vectors to Pixar's Universal Scene Description",
                 long_description=open('README.md').read().strip(),
                 author='Ben Skinner',
                 author_email='ben.vochsel@gmail.com',
                 url='https://github.com/Vochsel/svg_to_usd',
                 py_modules=['svg_to_usd'],
                 install_requires=[],
                 license='MIT License',
                 zip_safe=False,
                 keywords='usd, svg',
                 classifiers=['SVG', 'USD'])
