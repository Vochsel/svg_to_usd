import setuptools
from svg_to_usd.version import Version

setuptools.setup(
    name="svg_to_usd",
    version=Version("0.1.19").number,
    description="Convert SVG vectors to Pixar's Universal Scene Description",
    long_description=open("README.md").read().strip(),
    packages=setuptools.find_packages(),
    author="Ben Skinner",
    author_email="ben.vochsel@gmail.com",
    url="https://github.com/Vochsel/svg_to_usd",
    py_modules=["svg_to_usd"],
    install_requires=[
        "svgpath2mpl",
        "matplotlib",
        #   'usd-core',
        "opentypesvg",
    ],
    license="MIT License",
    zip_safe=True,
    keywords="usd, svg",
    classifiers=["SVG", "USD"],
)