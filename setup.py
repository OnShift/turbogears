from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

import sys
import os

if sys.version_info < (2, 3):
    raise SystemExit("TurboGears 1.0 requires Python 2.3 or later.")
elif sys.version_info >= (2, 7):
    # The main problem here is RuleDispatch.
    # TurboGears 1.1 uses PEAK-Rules instead.
    import warnings
    warnings.warn("TurboGears 1.0.11.2 does not support Python 2.7 or later."
        "\nYou should upgrade to TurboGears 1.1 or later.")

# import meta data (version, author etc.)
execfile(os.path.join("turbogears", "release.py"))

# setup params
install_requires = [
    "CherryPy >= 2.3.0, < 3.0dev",
    "ConfigObj >= 4.3.2",
    "DecoratorTools >= 1.4",
    "FormEncode >= 0.7.1",
    "newrelic >= 2.32",
    "PasteScript >= 1.6.2",
    #"RuleDispatch >= 0.5a0.dev-r2303",
    "setuptools >= 0.6c2",
    "simplejson >= 1.3",
    "TurboCheetah >= 1.0",
    # TurboJson >= 1.2 uses PEAK-Rules
    "TurboJson >= 1.3.2",
    "TurboKid >= 1.0.5",
    "memory_profiler >= 0.52.0",
    "fluent-logger >= 0.4.4",
    "psutil >= 5.4.3",
    "Pympler >= 0.5"
]

exp = ["TGFastData"]

future = [
    "Elixir >= 0.4.0",
    "Genshi >= 0.4.4",
]

testtools =  [
    "nose >= 0.9.3",
]

tgtesttools = testtools

if sys.version_info < (2, 5):
    # simplejson >= 2.1 does not support Py 2.4
    install_requires[install_requires.index(
        "simplejson >= 1.3")] += ", < 2.1dev"
    # Python < 2.5 does not include SQLite
    tgtesttools.append("pysqlite < 2.6dev")

if sys.version_info < (2, 4):
    # FormEcode >= 1.3 does not support Py 2.3
    install_requires[install_requires.index(
        "FormEncode >= 0.7.1")] += ", < 1.3dev"
    # Genshi >= 0.5 does not support Py 2.3
    future[future.index(
        "Genshi >= 0.4.4")] += ", < 0.5dev"
    sqlobject = [
        # SQLObject >= 0.11 does not support Py 2.3
        "SQLObject >= 0.10.1, < 0.11dev",
        ]
    sqlalchemy = [
        # SQLAlchemy >= 0.5 does not support Py 2.3
        "SQLAlchemy >= 0.3.10, < 0.5dev",
        ]
else:
    sqlobject = [
        "SQLObject >= 0.10.1, < 0.12dev",
    ]
    sqlalchemy = [
        "SQLAlchemy >= 0.3.10, < 0.6dev",
    ]

develop_requires = (install_requires
    + future + tgtesttools + sqlalchemy + sqlobject)

setup(
    name="TurboGears",
    description=description,
    long_description=long_description,
    version=version,
    author=author,
    author_email=email,
    maintainer=maintainer,
    maintainer_email=maintainer_email,
    url=url,
    download_url=download_url,
    dependency_links=[
        'git@github.com:OnShift/RuleDispatch.git@master#egg=RuleDispatch-dev',
    ],
    license=license,
    zip_safe=False,
    install_requires=install_requires,
    packages=find_packages(),
    include_package_data=True,
    exclude_package_data={"thirdparty": ["*"]},
    entry_points="""
    [console_scripts]
    tg-admin = turbogears.command:main

    [distutils.commands]
    docs = turbogears.docgen:GenSite

    [paste.paster_create_template]
    tgbase = turbogears.command.quickstart:BaseTemplate
    turbogears = turbogears.command.quickstart:TurbogearsTemplate
    tgbig = turbogears.command.quickstart:TGBig
    tgwidget = turbogears.command.quickstart:TGWidgetTemplate

    [turbogears.command]
    quickstart = turbogears.command.quickstart:quickstart
    sql = turbogears.command.base:SQL
    shell = turbogears.command.base:Shell
    toolbox = turbogears.command.base:ToolboxCommand
    update = turbogears.command.quickstart:update
    i18n = turbogears.command.i18n:InternationalizationTool
    info = turbogears.command.info:InfoCommand

    [turbogears.identity.provider]
    sqlobject = turbogears.identity.soprovider:SqlObjectIdentityProvider
    sqlalchemy= turbogears.identity.saprovider:SqlAlchemyIdentityProvider

    [turbogears.extensions]
    identity = turbogears.identity.visitor
    visit = turbogears.visit

    [turbogears.visit.manager]
    sqlobject = turbogears.visit.sovisit:SqlObjectVisitManager
    sqlalchemy = turbogears.visit.savisit:SqlAlchemyVisitManager

    [turbogears.toolboxcommand]
    widgets = turbogears.toolbox.base:WidgetBrowser
    shell = turbogears.toolbox.shell:WebConsole
    admi18n = turbogears.toolbox.admi18n:Internationalization
    designer = turbogears.toolbox.designer:Designer
    info = turbogears.toolbox.base:Info
    catwalk = turbogears.toolbox.catwalk:CatWalk

    """,
    extras_require={
        "exp" : exp,
        "sqlobject" : sqlobject,
        "sqlalchemy" : sqlalchemy,
        "future" : future,
        "testtools" : testtools,
        "tgtesttools" : tgtesttools,
        "develop" : develop_requires
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    test_suite='nose.collector',
)
